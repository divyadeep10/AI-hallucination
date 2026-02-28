from abc import ABC, abstractmethod

from sqlalchemy.orm import Session


class Agent(ABC):
    """
    Base class for all agents in the multi-agent pipeline.

    Agents operate on a workflow identified by its integer ID and are
    responsible for updating persistent state in the database.
    """

    name: str

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def run(self, workflow_id: int, db: Session) -> None:
        """
        Execute this agent's logic for the given workflow.
        Implementations should be idempotent where possible and must commit
        any state changes using the provided session.
        """
        raise NotImplementedError

