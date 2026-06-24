"""Base Workflow SDK — interface for creating custom DAG workflows."""

import logging
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class WorkflowStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class WorkflowStep:
    id: str = ""
    name: str = ""
    handler: Callable | None = None
    deps: list[str] = field(default_factory=list)
    retries: int = 0
    timeout: int = 300
    status: str = "pending"
    result: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id or self.name.lower().replace(" ", "_"),
            "name": self.name,
            "deps": self.deps,
            "retries": self.retries,
            "timeout": self.timeout,
            "status": self.status,
            "error": self.error,
        }


class BaseWorkflow(ABC):
    def __init__(self, workflow_id: str | None = None):
        self.id = workflow_id or str(uuid.uuid4())
        self.steps: dict[str, WorkflowStep] = {}
        self.status: WorkflowStatus = WorkflowStatus.PENDING
        self._logger = logging.getLogger(f"workflow.{self.__class__.__name__}")
        self._checkpoints: list[dict[str, Any]] = []
        self._created_at: float = time.time()

    @abstractmethod
    def build_graph(self) -> dict[str, WorkflowStep]: ...

    @abstractmethod
    def execute(self) -> dict[str, Any]: ...

    @abstractmethod
    def monitor(self) -> dict[str, Any]: ...

    def add_step(self, step: WorkflowStep) -> None:
        step.id = step.id or step.name.lower().replace(" ", "_")
        self.steps[step.id] = step

    def get_step(self, step_id: str) -> WorkflowStep | None:
        return self.steps.get(step_id)

    def save_checkpoint(self, data: dict[str, Any]) -> str:
        cpid = str(uuid.uuid4())
        self._checkpoints.append(
            {
                "id": cpid,
                "data": data,
                "timestamp": time.time(),
            }
        )
        return cpid

    def load_checkpoint(self, checkpoint_id: str) -> dict[str, Any] | None:
        for cp in self._checkpoints:
            if cp["id"] == checkpoint_id:
                return cp["data"]
        return None

    def list_checkpoints(self) -> list[dict[str, Any]]:
        return list(self._checkpoints)

    def rollback(self) -> bool:
        self.status = WorkflowStatus.ROLLED_BACK
        return True

    def recover(self) -> bool:
        self.status = WorkflowStatus.PENDING
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "steps": [s.to_dict() for s in self.steps.values()],
            "status": self.status.value,
            "checkpoints": len(self._checkpoints),
            "created_at": self._created_at,
        }
