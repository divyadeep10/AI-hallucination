import asyncio
import traceback
from datetime import datetime

from sqlalchemy.orm import Session

from app.agents.base import Agent
from app.db import SessionLocal
from app.llm import generate_answer
from app.models import Claim, Evidence, Response, Verification, Workflow
from app.models.workflow import WorkflowStatus

# Same as Critic/API: pick best verification per claim when multiple exist (internal + external)
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


class RefinementAgent(Agent):
    """
    Refinement Agent (Phase 6, PDF §23).

    Produces an improved final answer using verified claims, selected evidence,
    and critic feedback. Stores the refined answer as a Response with
    agent_type='REFINER' and sets the workflow status to REFINED.
    """

    def __init__(self) -> None:
        super().__init__(name="refiner")

    def run(self, workflow_id: int, db: Session) -> None:
        print(f"[AGENT] Starting RefinementAgent for workflow {workflow_id}")
        
        try:
            workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
            if workflow is None:
                print(f"[AGENT] RefinementAgent: Workflow {workflow_id} not found")
                return
                
            if workflow.status != WorkflowStatus.CRITIC_REVIEWED.value:
                print(f"[AGENT] RefinementAgent: Workflow {workflow_id} in status {workflow.status}, expected CRITIC_REVIEWED, skipping")
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
            
            # Find critic response
            critic = (
                db.query(Response)
                .filter(
                    Response.workflow_id == workflow_id,
                    Response.agent_type == "CRITIC",
                )
                .order_by(Response.timestamp.desc())
                .first()
            )
            
            if draft is None:
                print(f"[AGENT] RefinementAgent: No draft response found for workflow {workflow_id}")
                workflow.status = WorkflowStatus.FAILED.value
                workflow.completed_at = datetime.utcnow()
                workflow.error_message = "RefinementAgent: No draft response found"
                db.add(workflow)
                db.commit()
                return
                
            if critic is None:
                print(f"[AGENT] RefinementAgent: No critic response found for workflow {workflow_id}")
                workflow.status = WorkflowStatus.FAILED.value
                workflow.completed_at = datetime.utcnow()
                workflow.error_message = "RefinementAgent: No critic response found"
                db.add(workflow)
                db.commit()
                return

            # Collect verifications and evidence for this workflow only
            claim_ids_for_workflow = [
                c.id
                for c in db.query(Claim)
                .join(Response, Claim.response_id == Response.id)
                .filter(Response.workflow_id == workflow_id)
                .all()
            ]
            
            if not claim_ids_for_workflow:
                claims = {}
                best_verifications = {}
                evidence_map = {}
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
                by_claim = {}
                for v in all_verifications:
                    by_claim.setdefault(v.claim_id, []).append(v)
                best_verifications = {
                    cid: _best_verification_for_claim(vlist) for cid, vlist in by_claim.items()
                }
                evidence_ids = {v.evidence_id for v in best_verifications.values() if v and v.evidence_id}
                evidence_map = (
                    {e.id: e for e in db.query(Evidence).filter(Evidence.id.in_(evidence_ids)).all()}
                    if evidence_ids else {}
                )

            # Build refinement prompt: one result per claim (best verification after internal + external)
            lines = [
                "You are the refinement agent in a self-correcting multi-agent AI system.",
                "You will see a draft answer, a critique, and verification results (one per claim).",
                "Rewrite the answer so that it:",
                "- Uses only SUPPORTED claims as factual statements.",
                "- Downplays or omits UNCERTAIN and NO_EVIDENCE claims.",
                "- Corrects or clarifies CONTRADICTED claims.",
                "- Incorporates relevant evidence snippets where helpful.",
                "Draft answer:",
                draft.response_text or "(empty)",
                "",
                "Critique:",
                critic.response_text or "(empty)",
                "",
                "Verification results with evidence:",
            ]
            for claim_id in sorted(claims.keys()) if claims else []:
                claim = claims[claim_id]
                v = best_verifications.get(claim_id)
                if not claim:
                    continue
                if v is not None:
                    evidence = evidence_map.get(v.evidence_id) if v.evidence_id else None
                    snippet = evidence.snippet if evidence else ""
                    lines.append(
                        f"STATUS={v.status} CONF={v.confidence_score} CLAIM={claim.claim_text} EVIDENCE={snippet}"
                    )
                else:
                    lines.append(f"STATUS=NO_EVIDENCE CONF= CLAIM={claim.claim_text} EVIDENCE=")
            lines.append(
                "\nProduce a clear, well-structured final answer. Do not show this metadata."
            )
            refine_prompt = "\n".join(lines)

            # Generate refined answer using LLM
            try:
                refined = asyncio.run(generate_answer(refine_prompt))
            except Exception as llm_error:
                print(f"[AGENT] RefinementAgent: LLM generation failed: {llm_error}")
                raise  # Re-raise to trigger outer exception handler

            refined_response = Response(
                workflow_id=workflow.id,
                agent_type="REFINER",
                response_text=refined,
                model_used=None,
            )
            db.add(refined_response)

            workflow.status = WorkflowStatus.REFINED.value
            workflow.completed_at = datetime.utcnow()
            db.add(workflow)
            db.commit()
            
            print(f"[AGENT] Completed RefinementAgent for workflow {workflow_id}")
            
        except Exception as e:
            print(f"[AGENT] ERROR in RefinementAgent for workflow {workflow_id}: {str(e)}")
            print(traceback.format_exc())
            
            db.rollback()
            
            try:
                workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
                if workflow:
                    workflow.status = WorkflowStatus.FAILED.value
                    workflow.completed_at = datetime.utcnow()
                    workflow.error_message = f"RefinementAgent error: {str(e)}"
                    db.add(workflow)
                    db.commit()
            except Exception as commit_error:
                print(f"[AGENT] Failed to mark workflow as FAILED: {commit_error}")
            
            raise


def run_refiner_agent(workflow_id: int) -> None:
    """RQ job entrypoint for RefinementAgent."""
    db = SessionLocal()
    try:
        agent = RefinementAgent()
        agent.run(workflow_id, db)
    finally:
        db.close()

