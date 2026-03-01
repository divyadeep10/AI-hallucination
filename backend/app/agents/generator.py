import asyncio
import traceback
from datetime import datetime

from sqlalchemy.orm import Session

from app.agents.base import Agent
from app.db import SessionLocal
from app.llm import LLMProviderNotConfiguredError, generate_answer
from app.models import Response, Workflow
from app.models.workflow import WorkflowStatus


class GeneratorAgent(Agent):
    """
    Generator Agent

    Produces an initial draft response for a workflow using the configured LLM.

    In this phase, it:
    - Operates on workflows in the PLANNED state.
    - Calls the shared LLM generation function.
    - Stores the result in the responses table with agent_type='GENERATOR'.
    - Transitions the workflow to GENERATED.
    """

    def __init__(self) -> None:
        super().__init__(name="generator")

    def run(self, workflow_id: int, db: Session) -> None:
        print(f"[AGENT] Starting GeneratorAgent for workflow {workflow_id}")
        
        try:
            workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
            if workflow is None:
                print(f"[AGENT] GeneratorAgent: Workflow {workflow_id} not found")
                return

            if workflow.status != WorkflowStatus.PLANNED.value:
                print(f"[AGENT] GeneratorAgent: Workflow {workflow_id} in status {workflow.status}, expected PLANNED, skipping")
                return

            # Generate answer using LLM
            try:
                answer = asyncio.run(generate_answer(workflow.user_query))
            except LLMProviderNotConfiguredError as llm_error:
                print(f"[AGENT] GeneratorAgent: LLM provider not configured: {llm_error}")
                workflow.status = WorkflowStatus.FAILED.value
                workflow.completed_at = datetime.utcnow()
                workflow.error_message = f"GeneratorAgent: LLM provider not configured - {str(llm_error)}"
                db.add(workflow)
                db.commit()
                return
            except Exception as llm_error:
                print(f"[AGENT] GeneratorAgent: LLM generation failed: {llm_error}")
                raise  # Re-raise to trigger outer exception handler

            # Save response and update status
            response = Response(
                workflow_id=workflow.id,
                agent_type="GENERATOR",
                response_text=answer,
                model_used=_infer_model_used(),
            )
            db.add(response)

            workflow.status = WorkflowStatus.GENERATED.value
            db.add(workflow)
            db.commit()
            
            print(f"[AGENT] Completed GeneratorAgent for workflow {workflow_id}")
            
        except Exception as e:
            print(f"[AGENT] ERROR in GeneratorAgent for workflow {workflow_id}: {str(e)}")
            print(traceback.format_exc())
            
            db.rollback()
            
            try:
                workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
                if workflow:
                    workflow.status = WorkflowStatus.FAILED.value
                    workflow.completed_at = datetime.utcnow()
                    workflow.error_message = f"GeneratorAgent error: {str(e)}"
                    db.add(workflow)
                    db.commit()
            except Exception as commit_error:
                print(f"[AGENT] Failed to mark workflow as FAILED: {commit_error}")
            
            raise


def _infer_model_used() -> str:
    """
    Best-effort indication of which provider/model was used.

    This mirrors the provider selection logic in app.llm.
    """
    import os

    if os.getenv("OPENAI_API_KEY"):
        return os.getenv("OPENAI_MODEL", "OPENAI")
    if os.getenv("GEMINI_API_KEY"):
        return os.getenv("GEMINI_MODEL", "GEMINI")
    return "UNCONFIGURED"


def run_generator_agent(workflow_id: int) -> None:
    """
    RQ job entrypoint for executing the GeneratorAgent.
    """
    db = SessionLocal()
    try:
        agent = GeneratorAgent()
        agent.run(workflow_id, db)
    finally:
        db.close()

