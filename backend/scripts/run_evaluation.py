#!/usr/bin/env python3
"""
Phase 8: Evaluation script.
Runs baseline and/or full pipeline on a dataset of questions, computes metrics, and persists to DB.

Usage (from backend directory):
  python scripts/run_evaluation.py --dataset data/eval_questions.json --mode both [--name "Run 1"] [--timeout 300]
  python scripts/run_evaluation.py --dataset data/eval_questions.json --mode baseline
  python scripts/run_evaluation.py --dataset data/eval_questions.json --mode full_pipeline

Dataset JSON format: list of objects with "query" (required) and optional "expected_label".
Example: [{"query": "What is TCP?"}, {"query": "Why does TCP perform poorly in wireless?"}]
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure backend/app is importable when running from backend/
_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

# Load .env from project root so DATABASE_URL etc. are set
try:
    from dotenv import load_dotenv
    _root = _backend.parent
    load_dotenv(_root / ".env")
except ImportError:
    pass

import httpx
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.evaluation_metrics import aggregate_run_metrics, compute_claim_metrics_from_claims
from app.models import EvaluationRun, EvaluationSample

DEFAULT_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
POLL_INTERVAL_SEC = 2
DEFAULT_TIMEOUT = 300


def load_dataset(path: str) -> list[dict]:
    """Load dataset from JSON file. Returns list of {query, optional expected_label}."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Dataset file not found: {path}")
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Dataset JSON must be a list of objects.")
    out = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"Dataset item {i} is not an object.")
        q = (item.get("query") or "").strip()
        if not q:
            raise ValueError(f"Dataset item {i} has empty or missing 'query'.")
        out.append({"query": q, "expected_label": item.get("expected_label")})
    return out


def run_baseline(client: httpx.Client, base_url: str, query: str) -> tuple[int | None, str | None, str | None, str | None]:
    """POST /api/query. Returns (workflow_id, answer, status, error_message)."""
    try:
        r = client.post(
            f"{base_url}/api/query",
            json={"query": query},
            timeout=60.0,
        )
        r.raise_for_status()
        data = r.json()
        return (
            data.get("workflow_id"),
            data.get("answer"),
            data.get("status", "COMPLETED"),
            None,
        )
    except Exception as e:
        return None, None, None, str(e)


def run_full_pipeline(
    client: httpx.Client,
    base_url: str,
    query: str,
    poll_timeout_sec: int,
) -> tuple[int | None, str | None, str | None, dict | None, str | None]:
    """
    POST /api/workflows, poll until REFINED/COMPLETED/FAILED, then fetch claims.
    Returns (workflow_id, system_answer, status, metrics_dict, error_message).
    """
    try:
        r = client.post(
            f"{base_url}/api/workflows",
            json={"query": query},
            timeout=30.0,
        )
        r.raise_for_status()
        data = r.json()
        wf_id = data.get("workflow_id")
        if wf_id is None:
            return None, None, None, None, "No workflow_id in response"
        status = data.get("status", "")
        deadline = time.monotonic() + poll_timeout_sec
        while time.monotonic() < deadline:
            if status in ("REFINED", "COMPLETED", "FAILED"):
                break
            time.sleep(POLL_INTERVAL_SEC)
            r = client.get(f"{base_url}/api/workflows/{wf_id}", timeout=10.0)
            r.raise_for_status()
            data = r.json()
            status = data.get("status", "")
        if status not in ("REFINED", "COMPLETED", "FAILED"):
            return wf_id, None, status, None, "Pipeline timed out before REFINED/COMPLETED/FAILED"
        # Fetch responses for refiner answer
        system_answer = None
        r = client.get(f"{base_url}/api/workflows/{wf_id}/responses", timeout=10.0)
        if r.is_success:
            responses = r.json()
            for resp in reversed(responses or []):
                if resp.get("agent_type") == "REFINER":
                    system_answer = resp.get("response_text") or ""
                    break
        # Fetch claims for metrics
        claims = []
        r = client.get(f"{base_url}/api/workflows/{wf_id}/claims", timeout=10.0)
        if r.is_success:
            claims = r.json() or []
        metrics = compute_claim_metrics_from_claims(claims)
        return wf_id, system_answer, status, metrics, None
    except Exception as e:
        return None, None, None, None, str(e)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run evaluation (baseline and/or full pipeline) on a dataset.")
    parser.add_argument("--dataset", required=True, help="Path to JSON dataset file (list of {query[, expected_label]})")
    parser.add_argument("--mode", choices=["baseline", "full_pipeline", "both"], default="both")
    parser.add_argument("--name", default=None, help="Optional run name")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Backend API base URL")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Poll timeout per question for full pipeline (seconds)")
    args = parser.parse_args()
    try:
        dataset = load_dataset(args.dataset)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error loading dataset: {e}", file=sys.stderr)
        return 1
    db: Session = SessionLocal()
    run = EvaluationRun(
        name=args.name,
        mode=args.mode,
        dataset_path=args.dataset,
        status="running",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    run_id = run.id
    print(f"Created evaluation run id={run_id}, mode={args.mode}, questions={len(dataset)}")
    samples_data: list[dict] = []
    try:
        with httpx.Client(base_url=args.base_url, timeout=30.0) as client:
            for i, item in enumerate(dataset):
                query = item["query"]
                print(f"  [{i+1}/{len(dataset)}] {query[:60]}...")
                wf_baseline, wf_system = None, None
                baseline_answer, system_answer = None, None
                baseline_status, system_status = None, None
                metrics = None
                err = None
                if args.mode in ("baseline", "both"):
                    wf_baseline, baseline_answer, baseline_status, err = run_baseline(
                        client, args.base_url, query
                    )
                    if err:
                        print(f"    Baseline error: {err}")
                if args.mode in ("full_pipeline", "both"):
                    wf_system, system_answer, system_status, metrics, pipe_err = run_full_pipeline(
                        client, args.base_url, query, args.timeout
                    )
                    if pipe_err:
                        err = pipe_err if not err else f"{err}; pipeline: {pipe_err}"
                        print(f"    Pipeline error: {pipe_err}")
                sample = EvaluationSample(
                    evaluation_run_id=run_id,
                    question=query,
                    workflow_id_baseline=wf_baseline,
                    workflow_id_system=wf_system,
                    baseline_answer=baseline_answer,
                    system_answer=system_answer,
                    baseline_status=baseline_status,
                    system_status=system_status,
                    metrics=metrics,
                    error_message=err,
                )
                db.add(sample)
                db.flush()
                samples_data.append({
                    "baseline_status": baseline_status,
                    "system_status": system_status,
                    "metrics": metrics or {},
                })
        run.status = "completed"
        run.summary_metrics = aggregate_run_metrics(samples_data)
        run.completed_at = datetime.utcnow()
    except Exception as e:
        run.status = "failed"
        run.error_message = str(e)
        run.completed_at = datetime.utcnow()
        print(f"Run failed: {e}", file=sys.stderr)
    db.add(run)
    db.commit()
    db.close()
    print(f"Run id={run_id} finished with status={run.status}")
    if run.summary_metrics:
        print("Summary metrics:", json.dumps(run.summary_metrics, indent=2))
    return 0 if run.status == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
