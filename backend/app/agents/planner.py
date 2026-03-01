import traceback
from datetime import datetime

from sqlalchemy.orm import Session

from app.agents.base import Agent
from app.db import SessionLocal
from app.models.workflow import Workflow, WorkflowStatus


class PlannerAgent(Agent):
    """
    Planner Agent

    In later phases, this agent will:
    - Analyse the user query.
    - Decompose it into subtasks.
    - Persist a structured execution plan.

    In Phase 2, it provides a minimal implementation that:
    - Moves the workflow from CREATED to PLANNED.
    """

    def __init__(self) -> None:
        super().__init__(name="planner")

    def run(self, workflow_id: int, db: Session) -> None:
        print(f"[AGENT] Starting PlannerAgent for workflow {workflow_id}")
        
        try:
            workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
            if workflow is None:
                print(f"[AGENT] PlannerAgent: Workflow {workflow_id} not found")
                return

            if workflow.status != WorkflowStatus.CREATED.value:
                print(f"[AGENT] PlannerAgent: Workflow {workflow_id} already in status {workflow.status}, skipping")
                return

            workflow.status = WorkflowStatus.PLANNED.value
            db.add(workflow)
            db.commit()
            
            print(f"[AGENT] Completed PlannerAgent for workflow {workflow_id}")
            
        except Exception as e:
            print(f"[AGENT] ERROR in PlannerAgent for workflow {workflow_id}: {str(e)}")
            print(traceback.format_exc())
            
            # Rollback any partial changes
            db.rollback()
            
            # Mark workflow as failed
            try:
                workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
                if workflow:
                    workflow.status = WorkflowStatus.FAILED.value
                    workflow.completed_at = datetime.utcnow()
                    workflow.error_message = f"PlannerAgent error: {str(e)}"
                    db.add(workflow)
                    db.commit()
            except Exception as commit_error:
                print(f"[AGENT] Failed to mark workflow as FAILED: {commit_error}")
            
            # Re-raise to let RQ know the job failed
            raise


def run_planner_agent(workflow_id: int) -> None:
    """
    RQ job entrypoint for executing the PlannerAgent.

    This function is imported by the worker process and enqueued by the API.
    """
    db = SessionLocal()
    try:
        agent = PlannerAgent()
        agent.run(workflow_id, db)
    finally:
        db.close()

