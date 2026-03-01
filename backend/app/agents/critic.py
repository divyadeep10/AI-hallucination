import asyncio
import traceback
from datetime import datetime

from sqlalchemy.orm import Session

from app.agents.base import Agent
from app.db import SessionLocal
from app.llm import generate_answer
from app.models import Claim, Response, Verification, Workflow
from app.models.workflow import WorkflowStatus

# Same priority as API: when a claim has multiple verifications (e.g. internal + external), pick the best one
_VERIFICATION_STATUS_PRIORITY = {"SUPPORTED": 0, "CONTRADICTED": 1, "UNCERTAIN": 2, "NO_EVIDENCE": 3}


def _best_verification_for_claim(verifications: list) -> Verification | None:
    """Pick the best verification when multiple exist (e.g. internal NO_EVIDENCE + external SUPPORTED)."""
    if not verifications:
        return None

    def priority(v):
        status = (v.status or "").strip().upper() or "NO_EVIDENCE"
        rank = _VERIFICATION_STATUS_PRIORITY.get(status, 3)
        has_evidence = 0 if (v.evidence_id is not None) else 1
        return (rank, has_evidence)

    return min(verifications, key=priority)


class CriticAgent(Agent):
    """
    Critic Agent (Phase 6, PDF §23).

    Produces structured feedback about weaknesses in the draft answer based on
    verification results. Stores the critique as a Response with
    agent_type='CRITIC' and moves the workflow to CRITIC_REVIEWED.
    """

    def __init__(self) -> None:
        super().__init__(name="critic")

    def run(self, workflow_id: int, db: Session) -> None:
        print(f"[AGENT] Starting CriticAgent for workflow {workflow_id}")
        
        try:
            workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
            if workflow is None:
                print(f"[AGENT] CriticAgent: Workflow {workflow_id} not found")
                return
                
            if workflow.status != WorkflowStatus.VERIFIED.value:
                print(f"[AGENT] CriticAgent: Workflow {workflow_id} in status {workflow.status}, expected VERIFIED, skipping")
                return

            # Find draft response (prefer generator, fallback to baseline)
            draft = (
                db.query(Response)
                .filter(
                    Response.workflow_id == workflow_id,
                    Response.agent_type == "GENERATOR",
                )
                .order_by(Response.timestamp.desc())
                .first()
            )
            if draft is None:
                draft = (
                    db.query(Response)
                    .filter(
                        Response.workflow_id == workflow_id,
                        Response.agent_type == "BASELINE",
                    )
                    .order_by(Response.timestamp.desc())
                    .first()
                )
            if draft is None:
                print(f"[AGENT] CriticAgent: No draft response (GENERATOR or BASELINE) found for workflow {workflow_id}")
                workflow.status = WorkflowStatus.FAILED.value
                workflow.completed_at = datetime.utcnow()
                workflow.error_message = "CriticAgent: No draft response found"
                db.add(workflow)
                db.commit()
                return

            # Get claims and verifications for this workflow
            claim_ids_for_workflow = [
                c.id
                for c in db.query(Claim)
                .join(Response, Claim.response_id == Response.id)
                .filter(Response.workflow_id == workflow_id)
                .all()
            ]
            
            if not claim_ids_for_workflow:
                verifications_by_claim = {}
                claims = {}
            else:
                all_verifications = (
                    db.query(Verification)
                    .filter(Verification.claim_id.in_(claim_ids_for_workflow))
                    .all()
                )
                claims = {
                    c.id: c
                    for c in db.query(Claim).filter(Claim.id.in_(claim_ids_for_workflow)).all()
                }
                # Group by claim_id and pick best verification per claim (so post–external-retrieval state is used)
                by_claim = {}
                for v in all_verifications:
                    by_claim.setdefault(v.claim_id, []).append(v)
                verifications_by_claim = {
                    cid: _best_verification_for_claim(vlist) for cid, vlist in by_claim.items()
                }

            # Build critic prompt: one line per claim using the best verification (internal + external merged)
            prompt_lines = [
                "You are a critic module in a self-correcting multi-agent AI system.",
                "You will receive a draft answer and claim-level verification results (one result per claim).",
                "Highlight unsupported, contradicted, or uncertain areas and suggest improvements.",
                "Draft answer:",
                draft.response_text or "(empty)",
                "",
                "Verification results (one per claim):",
            ]
            for claim_id in sorted(claims.keys()) if claims else []:
                claim = claims[claim_id]
                v = verifications_by_claim.get(claim_id)
                claim_text = claim.claim_text if claim else "(unknown claim)"
                if v is not None:
                    prompt_lines.append(
                        f"status={v.status} confidence={v.confidence_score} claim={claim_text}"
                    )
                else:
                    prompt_lines.append(f"status=NO_EVIDENCE confidence= claim={claim_text}")
            prompt_lines.append(
                "\nProvide a concise critique and numbered list of improvement suggestions."
            )
            critic_prompt = "\n".join(prompt_lines)

            # Generate critique using LLM
            try:
                critique = asyncio.run(generate_answer(critic_prompt))
            except Exception as llm_error:
                print(f"[AGENT] CriticAgent: LLM generation failed: {llm_error}")
                raise  # Re-raise to trigger outer exception handler

            critic_response = Response(
                workflow_id=workflow.id,
                agent_type="CRITIC",
                response_text=critique,
                model_used=None,
            )
            db.add(critic_response)

            workflow.status = WorkflowStatus.CRITIC_REVIEWED.value
            db.add(workflow)
            db.commit()
            
            print(f"[AGENT] Completed CriticAgent for workflow {workflow_id}")
            
        except Exception as e:
            print(f"[AGENT] ERROR in CriticAgent for workflow {workflow_id}: {str(e)}")
            print(traceback.format_exc())
            
            db.rollback()
            
            try:
                workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
                if workflow:
                    workflow.status = WorkflowStatus.FAILED.value
                    workflow.completed_at = datetime.utcnow()
                    workflow.error_message = f"CriticAgent error: {str(e)}"
                    db.add(workflow)
                    db.commit()
            except Exception as commit_error:
                print(f"[AGENT] Failed to mark workflow as FAILED: {commit_error}")
            
            raise


def run_critic_agent(workflow_id: int) -> None:
    """RQ job entrypoint for CriticAgent."""
    db = SessionLocal()
    try:
        agent = CriticAgent()
        agent.run(workflow_id, db)
    finally:
        db.close()

