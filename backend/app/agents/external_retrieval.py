"""
External Retrieval Agent: when no evidence is found from internal retrieval,
run web search (Playwright), scrape top N pages, chunk, re-verify with NLI, store as external evidence.
Controlled by EXTERNAL_RETRIEVAL_ENABLED in .env (enable/disable).
"""
import asyncio
import traceback
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.agents.base import Agent
from app.db import SessionLocal
from app.llm import verify_claim_with_evidence
from app.models import Claim, Evidence, Response, Verification, Workflow
from app.models.workflow import WorkflowStatus
from app.external_retrieval import EXTERNAL_RETRIEVAL_ENABLED, run_external_pipeline


def _chunk_relevant_to_claim(chunk_snippet: str, claim_text: str) -> bool:
    """True if chunk contains at least two words from the claim (simple relevance)."""
    claim_words = set((claim_text or "").lower().split())
    claim_words = {w for w in claim_words if len(w) > 2}
    chunk_lower = (chunk_snippet or "").lower()
    return sum(1 for w in claim_words if w in chunk_lower) >= 2


class ExternalRetrievalAgent(Agent):
    """
    Runs after Verification. When no evidence was found from internal retrieval
    (i.e. no Evidence rows with is_external=False for this workflow's claims),
    runs external web search (Playwright), scrapes top N pages, chunks text,
    re-verifies claims with NLI, and stores Evidence + Verification with is_external=True.
    Set EXTERNAL_RETRIEVAL_ENABLED=false in .env to disable this layer entirely.
    """

    def __init__(self) -> None:
        super().__init__(name="external_retrieval")

    def run(self, workflow_id: int, db: Session) -> None:
        print(f"[AGENT] Starting ExternalRetrievalAgent for workflow {workflow_id}")
        try:
            if not EXTERNAL_RETRIEVAL_ENABLED:
                print(f"[AGENT] ExternalRetrievalAgent: EXTERNAL_RETRIEVAL_ENABLED is false, skipping")
                return

            workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
            if workflow is None:
                print(f"[AGENT] ExternalRetrievalAgent: Workflow {workflow_id} not found")
                return
            if workflow.status != WorkflowStatus.VERIFIED.value:
                print(f"[AGENT] ExternalRetrievalAgent: Workflow {workflow_id} not VERIFIED, skipping")
                return

            claims = (
                db.query(Claim)
                .join(Response, Claim.response_id == Response.id)
                .filter(Response.workflow_id == workflow_id)
                .all()
            )
            if not claims:
                return
            claim_ids = {c.id for c in claims}

            # Run Playwright only when no internal evidence was found
            internal_evidence_count = (
                db.query(Evidence)
                .filter(
                    Evidence.claim_id.in_(claim_ids),
                    or_(Evidence.is_external == False, Evidence.is_external.is_(None)),
                )
                .count()
            )
            if internal_evidence_count > 0:
                print(f"[AGENT] ExternalRetrievalAgent: internal evidence found ({internal_evidence_count} rows), skipping web search")
                return

            print(f"[AGENT] ExternalRetrievalAgent: no internal evidence, running web search (Playwright)")
            external_items = run_external_pipeline(workflow.user_query or "")
            if not external_items:
                print(f"[AGENT] ExternalRetrievalAgent: no external evidence returned")
                return

            for claim in claims:
                relevant = [
                    item for item in external_items
                    if _chunk_relevant_to_claim(item.get("snippet") or "", claim.claim_text or "")
                ]
                if not relevant:
                    relevant = external_items[:3]
                for item in relevant[:3]:
                    snippet = (item.get("snippet") or "").strip()
                    source_url = item.get("source_url")
                    if not snippet:
                        continue
                    try:
                        result = asyncio.run(
                            verify_claim_with_evidence(claim.claim_text or "", snippet)
                        )
                    except Exception:
                        result = {"status": "UNCERTAIN", "confidence": None}
                    status = result.get("status") or "UNCERTAIN"
                    confidence = result.get("confidence")
                    if confidence is not None and not isinstance(confidence, (int, float)):
                        confidence = None

                    evidence = Evidence(
                        claim_id=claim.id,
                        source_url=source_url,
                        snippet=snippet,
                        retrieval_score=item.get("retrieval_score"),
                        is_external=True,
                    )
                    db.add(evidence)
                    db.flush()
                    verification = Verification(
                        claim_id=claim.id,
                        status=status,
                        confidence_score=confidence,
                        evidence_id=evidence.id,
                    )
                    db.add(verification)
            db.commit()
            print(f"[AGENT] Completed ExternalRetrievalAgent for workflow {workflow_id}")
        except Exception as e:
            print(f"[AGENT] ERROR in ExternalRetrievalAgent for workflow {workflow_id}: {str(e)}")
            print(traceback.format_exc())
            db.rollback()


def run_external_retrieval_agent(workflow_id: int) -> None:
    """RQ job entrypoint for ExternalRetrievalAgent."""
    db = SessionLocal()
    try:
        agent = ExternalRetrievalAgent()
        agent.run(workflow_id, db)
    finally:
        db.close()
