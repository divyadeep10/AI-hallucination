import asyncio
import traceback

from sqlalchemy.orm import Session

from app.agents.base import Agent
from app.db import SessionLocal
from app.llm import verify_claim_with_evidence
from app.models import Claim, Evidence, Response, Verification, Workflow
from app.models.workflow import WorkflowStatus


class VerificationAgent(Agent):
    """
    Verification Agent (Phase 6, PDF §22).

    For each claim, evaluates available evidence and stores a verification row
    summarizing status and confidence. Transitions workflow to VERIFIED.
    """

    def __init__(self) -> None:
        super().__init__(name="verification")

    def run(self, workflow_id: int, db: Session) -> None:
        print(f"[AGENT] Starting VerificationAgent for workflow {workflow_id}")
        
        try:
            workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
            if workflow is None:
                print(f"[AGENT] VerificationAgent: Workflow {workflow_id} not found")
                return
                
            if workflow.status != WorkflowStatus.EVIDENCE_RETRIEVED.value:
                print(f"[AGENT] VerificationAgent: Workflow {workflow_id} in status {workflow.status}, expected EVIDENCE_RETRIEVED, skipping")
                return

            claims = (
                db.query(Claim)
                .join(Response, Claim.response_id == Response.id)
                .filter(Response.workflow_id == workflow_id)
                .all()
            )
            
            if not claims:
                print(f"[AGENT] VerificationAgent: No claims found for workflow {workflow_id}, marking as VERIFIED")
                workflow.status = WorkflowStatus.VERIFIED.value
                db.add(workflow)
                db.commit()
                return

            verifications_added = 0
            for claim in claims:
                try:
                    evidence_q = (
                        db.query(Evidence)
                        .filter(Evidence.claim_id == claim.id)
                        .order_by(Evidence.retrieval_score.desc().nullslast(), Evidence.id.asc())
                    )
                    evidence = evidence_q.first()
                    
                    if evidence is None:
                        verification = Verification(
                            claim_id=claim.id,
                            status="NO_EVIDENCE",
                            confidence_score=None,
                            evidence_id=None,
                        )
                        db.add(verification)
                        verifications_added += 1
                        continue

                    try:
                        result = asyncio.run(
                            verify_claim_with_evidence(claim.claim_text, evidence.snippet)
                        )
                    except Exception as verify_error:
                        print(f"[AGENT] VerificationAgent: LLM verification failed for claim {claim.id}: {verify_error}")
                        result = {"status": "UNCERTAIN", "confidence": None}

                    status = result.get("status") or "UNCERTAIN"
                    confidence = result.get("confidence")
                    if confidence is not None and not isinstance(confidence, (int, float)):
                        confidence = None

                    verification = Verification(
                        claim_id=claim.id,
                        status=status,
                        confidence_score=confidence,
                        evidence_id=evidence.id,
                    )
                    db.add(verification)
                    verifications_added += 1
                    
                except Exception as claim_error:
                    print(f"[AGENT] VerificationAgent: Error verifying claim {claim.id}: {claim_error}")
                    # Add UNCERTAIN verification and continue with other claims
                    verification = Verification(
                        claim_id=claim.id,
                        status="UNCERTAIN",
                        confidence_score=None,
                        evidence_id=None,
                    )
                    db.add(verification)
                    verifications_added += 1

            workflow.status = WorkflowStatus.VERIFIED.value
            db.add(workflow)
            db.commit()
            
            print(f"[AGENT] Completed VerificationAgent for workflow {workflow_id}: verified {verifications_added} claims")
            
        except Exception as e:
            print(f"[AGENT] ERROR in VerificationAgent for workflow {workflow_id}: {str(e)}")
            print(traceback.format_exc())
            
            db.rollback()
            
            try:
                workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
                if workflow:
                    workflow.status = WorkflowStatus.FAILED.value
                    workflow.error_message = f"VerificationAgent error: {str(e)}"
                    db.add(workflow)
                    db.commit()
            except Exception as commit_error:
                print(f"[AGENT] Failed to mark workflow as FAILED: {commit_error}")
            
            raise


def run_verification_agent(workflow_id: int) -> None:
    """
    RQ job entrypoint for VerificationAgent.
    """
    db = SessionLocal()
    try:
        agent = VerificationAgent()
        agent.run(workflow_id, db)
    finally:
        db.close()

