"""
Phase 8: Metrics computation for evaluation runs.
Computes claim-level and run-level metrics from verification statuses.
"""

from typing import Any


def compute_claim_metrics_from_claims(claims: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Compute per-sample metrics from a list of claim dicts with optional
    verification_status and verification_confidence.
    Each claim dict may have: verification_status (str | None), verification_confidence (float | None).
    """
    total = len(claims)
    if total == 0:
        return {
            "num_claims": 0,
            "num_supported": 0,
            "num_contradicted": 0,
            "num_uncertain": 0,
            "claim_verification_accuracy": 0.0,
            "supported_rate": 0.0,
            "contradicted_rate": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
        }
    supported = sum(1 for c in claims if _norm_status(c.get("verification_status")) == "SUPPORTED")
    contradicted = sum(1 for c in claims if _norm_status(c.get("verification_status")) == "CONTRADICTED")
    uncertain = sum(
        1
        for c in claims
        if _norm_status(c.get("verification_status")) in ("UNCERTAIN", "NO_EVIDENCE", "")
    )
    verified_total = supported + contradicted
    claim_verification_accuracy = (supported / total) if total else 0.0
    supported_rate = (supported / total) if total else 0.0
    contradicted_rate = (contradicted / total) if total else 0.0
    precision = (supported / verified_total) if verified_total else 0.0
    recall = (supported / total) if total else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "num_claims": total,
        "num_supported": supported,
        "num_contradicted": contradicted,
        "num_uncertain": uncertain,
        "claim_verification_accuracy": round(claim_verification_accuracy, 4),
        "supported_rate": round(supported_rate, 4),
        "contradicted_rate": round(contradicted_rate, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def _norm_status(s: str | None) -> str:
    if s is None:
        return ""
    return (s or "").strip().upper()


def aggregate_run_metrics(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Aggregate per-sample metrics into run-level summary.
    Each sample dict may have: metrics (dict with num_claims, claim_verification_accuracy, etc.),
    baseline_status, system_status (for success counts).
    """
    num_questions = len(samples)
    if num_questions == 0:
        return {
            "num_questions": 0,
            "num_baseline_success": 0,
            "num_system_success": 0,
            "avg_claim_verification_accuracy": 0.0,
            "avg_supported_rate": 0.0,
            "avg_contradicted_rate": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
        }
    num_baseline_success = sum(
        1 for s in samples if (s.get("baseline_status") or "").upper() in ("COMPLETED",)
    )
    num_system_success = sum(
        1
        for s in samples
        if (s.get("system_status") or "").upper() in ("REFINED", "COMPLETED")
    )
    metric_list = [s.get("metrics") or {} for s in samples]
    total_claims = sum(m.get("num_claims", 0) for m in metric_list)
    accuracies = [m.get("claim_verification_accuracy", 0) for m in metric_list if m.get("num_claims", 0) > 0]
    supported_rates = [m.get("supported_rate", 0) for m in metric_list]
    contradicted_rates = [m.get("contradicted_rate", 0) for m in metric_list]
    precisions = [m.get("precision", 0) for m in metric_list if m.get("num_claims", 0) > 0]
    recalls = [m.get("recall", 0) for m in metric_list if m.get("num_claims", 0) > 0]
    f1s = [m.get("f1", 0) for m in metric_list if m.get("num_claims", 0) > 0]
    return {
        "num_questions": num_questions,
        "num_baseline_success": num_baseline_success,
        "num_system_success": num_system_success,
        "total_claims": total_claims,
        "avg_claim_verification_accuracy": round(sum(accuracies) / len(accuracies), 4) if accuracies else 0.0,
        "avg_supported_rate": round(sum(supported_rates) / num_questions, 4) if supported_rates else 0.0,
        "avg_contradicted_rate": round(sum(contradicted_rates) / num_questions, 4) if contradicted_rates else 0.0,
        "precision": round(sum(precisions) / len(precisions), 4) if precisions else 0.0,
        "recall": round(sum(recalls) / len(recalls), 4) if recalls else 0.0,
        "f1": round(sum(f1s) / len(f1s), 4) if f1s else 0.0,
    }
