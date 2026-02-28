import asyncio
import traceback

from sqlalchemy.orm import Session

from app.agents.base import Agent
from app.db import SessionLocal
from app.llm import extract_claims_from_text
from app.models import Claim, Response, Workflow
from app.models.workflow import WorkflowStatus


class ClaimExtractionAgent(Agent):
    """
    Claim Extraction Agent (PDF §20).

    Extracts atomic factual claims from the generator's draft response,
    normalizes them, and stores per-claim rows. Moves workflow to CLAIMS_EXTRACTED.
    """

    def __init__(self) -> None:
        super().__init__(name="claim_extractor")

    def run(self, workflow_id: int, db: Session) -> None:
        print(f"[AGENT] Starting ClaimExtractionAgent for workflow {workflow_id}")
        
        try:
            workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
            if workflow is None:
                print(f"[AGENT] ClaimExtractionAgent: Workflow {workflow_id} not found")
                return
                
            if workflow.status != WorkflowStatus.GENERATED.value:
                print(f"[AGENT] ClaimExtractionAgent: Workflow {workflow_id} in status {workflow.status}, expected GENERATED, skipping")
                return

            # Find generator response
            generator_response = (
                db.query(Response)
                .filter(
                    Response.workflow_id == workflow_id,
                    Response.agent_type == "GENERATOR",
                )
                .order_by(Response.timestamp.desc())
                .limit(1)
                .first()
            )
            
            if generator_response is None:
                print(f"[AGENT] ClaimExtractionAgent: No GENERATOR response found for workflow {workflow_id}")
                workflow.status = WorkflowStatus.FAILED.value
                workflow.error_message = "ClaimExtractionAgent: No GENERATOR response found"
                db.add(workflow)
                db.commit()
                return

            text = (generator_response.response_text or "").strip()
            if not text:
                print(f"[AGENT] ClaimExtractionAgent: Empty response text for workflow {workflow_id}, marking as CLAIMS_EXTRACTED with 0 claims")
                workflow.status = WorkflowStatus.CLAIMS_EXTRACTED.value
                db.add(workflow)
                db.commit()
                return

            # Extract claims via LLM
            try:
                raw_claims = asyncio.run(extract_claims_from_text(text))
            except Exception as extraction_error:
                print(f"[AGENT] ClaimExtractionAgent: Claim extraction failed: {extraction_error}")
                raise  # Re-raise to trigger outer exception handler

            # Deduplicate and store claims
            seen: set[str] = set()
            claims_added = 0
            for item in raw_claims:
                claim_text = (item.get("claim_text") or "").strip()
                if not claim_text:
                    continue
                key = claim_text.lower()
                if key in seen:
                    continue
                seen.add(key)
                
                entities = item.get("entities")
                if not isinstance(entities, list):
                    entities = []
                entities = [str(e).strip() for e in entities if e]
                
                confidence = item.get("extraction_confidence")
                if confidence is not None and not isinstance(confidence, (int, float)):
                    confidence = None
                if confidence is not None and (confidence < 0 or confidence > 1):
                    confidence = None
                    
                claim = Claim(
                    response_id=generator_response.id,
                    claim_text=claim_text,
                    entities=entities,
                    extraction_confidence=confidence,
                )
                db.add(claim)
                claims_added += 1

            workflow.status = WorkflowStatus.CLAIMS_EXTRACTED.value
            db.add(workflow)
            db.commit()
            
            print(f"[AGENT] Completed ClaimExtractionAgent for workflow {workflow_id}: extracted {claims_added} claims")
            
        except Exception as e:
            print(f"[AGENT] ERROR in ClaimExtractionAgent for workflow {workflow_id}: {str(e)}")
            print(traceback.format_exc())
            
            db.rollback()
            
            try:
                workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
                if workflow:
                    workflow.status = WorkflowStatus.FAILED.value
                    workflow.error_message = f"ClaimExtractionAgent error: {str(e)}"
                    db.add(workflow)
                    db.commit()
            except Exception as commit_error:
                print(f"[AGENT] Failed to mark workflow as FAILED: {commit_error}")
            
            raise


def run_claim_extractor_agent(workflow_id: int) -> None:
    """RQ job entrypoint for ClaimExtractionAgent."""
    db = SessionLocal()
    try:
        agent = ClaimExtractionAgent()
        agent.run(workflow_id, db)
    finally:
        db.close()
