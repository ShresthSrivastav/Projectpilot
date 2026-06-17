"""Base Workflow SDK — interface for creating custom DAG workflows."""
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


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
    handler: Optional[Callable] = None
    deps: List[str] = field(default_factory=list)
    retries: int = 0
    timeout: int = 300
    status: str = "pending"
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
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
    def __init__(self, workflow_id: Optional[str] = None):
        self.id = workflow_id or str(uuid.uuid4())
        self.steps: Dict[str, WorkflowStep] = {}
        self.status: WorkflowStatus = WorkflowStatus.PENDING
        self._logger = logging.getLogger(f"workflow.{self.__class__.__name__}")
        self._checkpoints: List[Dict[str, Any]] = []
        self._created_at: float = time.time()

    @abstractmethod
    def build_graph(self) -> Dict[str, WorkflowStep]:
        ...

    @abstractmethod
    def execute(self) -> Dict[str, Any]:
        ...

    @abstractmethod
    def monitor(self) -> Dict[str, Any]:
        ...

    def add_step(self, step: WorkflowStep) -> None:
        step.id = step.id or step.name.lower().replace(" ", "_")
        self.steps[step.id] = step

    def get_step(self, step_id: str) -> Optional[WorkflowStep]:
        return self.steps.get(step_id)

    def save_checkpoint(self, data: Dict[str, Any]) -> str:
        cpid = str(uuid.uuid4())
        self._checkpoints.append({
            "id": cpid,
            "data": data,
            "timestamp": time.time(),
        })
        return cpid

    def load_checkpoint(self, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        for cp in self._checkpoints:
            if cp["id"] == checkpoint_id:
                return cp["data"]
        return None

    def list_checkpoints(self) -> List[Dict[str, Any]]:
        return list(self._checkpoints)

    def rollback(self) -> bool:
        self.status = WorkflowStatus.ROLLED_BACK
        return True

    def recover(self) -> bool:
        self.status = WorkflowStatus.PENDING
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "steps": [s.to_dict() for s in self.steps.values()],
            "status": self.status.value,
            "checkpoints": len(self._checkpoints),
            "created_at": self._created_at,
        }
