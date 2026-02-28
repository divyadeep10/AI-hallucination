import traceback

from sqlalchemy.orm import Session

from app.agents.base import Agent
from app.db import SessionLocal
from app.models import Claim, Evidence, Response, Workflow
from app.models.workflow import WorkflowStatus
from app.retrieval import retrieve_evidence_for_claim


class RetrieverAgent(Agent):
    """
    Retriever Agent (Phase 5, PDF §21).

    For each claim associated with a workflow, runs the retrieval module to
    obtain candidate evidence snippets and stores them in the evidence table.
    Transitions workflow to EVIDENCE_RETRIEVED on success.
    """

    def __init__(self) -> None:
        super().__init__(name="retriever")

    def run(self, workflow_id: int, db: Session) -> None:
        print(f"[AGENT] Starting RetrieverAgent for workflow {workflow_id}")
        
        try:
            workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
            if workflow is None:
                print(f"[AGENT] RetrieverAgent: Workflow {workflow_id} not found")
                return
                
            if workflow.status != WorkflowStatus.CLAIMS_EXTRACTED.value:
                print(f"[AGENT] RetrieverAgent: Workflow {workflow_id} in status {workflow.status}, expected CLAIMS_EXTRACTED, skipping")
                return

            # All claims for responses belonging to this workflow
            claims = (
                db.query(Claim)
                .join(Response, Claim.response_id == Response.id)
                .filter(Response.workflow_id == workflow_id)
                .all()
            )
            
            if not claims:
                print(f"[AGENT] RetrieverAgent: No claims found for workflow {workflow_id}, marking as EVIDENCE_RETRIEVED")
                workflow.status = WorkflowStatus.EVIDENCE_RETRIEVED.value
                db.add(workflow)
                db.commit()
                return

            evidence_count = 0
            for claim in claims:
                try:
                    evidence_items = retrieve_evidence_for_claim(claim.claim_text)
                    for item in evidence_items:
                        snippet = (item.get("snippet") or "").strip()
                        if not snippet:
                            continue
                        evidence = Evidence(
                            claim_id=claim.id,
                            source_url=item.get("source_url"),
                            snippet=snippet,
                            retrieval_score=item.get("retrieval_score"),
                        )
                        db.add(evidence)
                        evidence_count += 1
                except Exception as retrieval_error:
                    print(f"[AGENT] RetrieverAgent: Error retrieving evidence for claim {claim.id}: {retrieval_error}")
                    # Continue with other claims instead of failing the entire workflow

            workflow.status = WorkflowStatus.EVIDENCE_RETRIEVED.value
            db.add(workflow)
            db.commit()
            
            print(f"[AGENT] Completed RetrieverAgent for workflow {workflow_id}: retrieved {evidence_count} evidence items for {len(claims)} claims")
            
        except Exception as e:
            print(f"[AGENT] ERROR in RetrieverAgent for workflow {workflow_id}: {str(e)}")
            print(traceback.format_exc())
            
            db.rollback()
            
            try:
                workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
                if workflow:
                    workflow.status = WorkflowStatus.FAILED.value
                    workflow.error_message = f"RetrieverAgent error: {str(e)}"
                    db.add(workflow)
                    db.commit()
            except Exception as commit_error:
                print(f"[AGENT] Failed to mark workflow as FAILED: {commit_error}")
            
            raise


def run_retriever_agent(workflow_id: int) -> None:
    """
    RQ job entrypoint for RetrieverAgent.
    """
    db = SessionLocal()
    try:
        agent = RetrieverAgent()
        agent.run(workflow_id, db)
    finally:
        db.close()

