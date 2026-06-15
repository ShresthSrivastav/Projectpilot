"""Base Agent SDK — interface for creating custom agents."""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AgentCapability:
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentLifecycleHook:
    on_initialize: Optional[str] = None
    on_plan: Optional[str] = None
    on_execute: Optional[str] = None
    on_validate: Optional[str] = None
    on_cleanup: Optional[str] = None


class BaseAgent(ABC):
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    capabilities: List[AgentCapability] = []
    lifecycle_hooks: AgentLifecycleHook = field(default_factory=AgentLifecycleHook)

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._state: Dict[str, Any] = {}
        self._logger = logging.getLogger(f"agent.{self.name}")

    @abstractmethod
    def initialize(self) -> bool:
        ...

    @abstractmethod
    def plan(self, context: Dict[str, Any]) -> Dict[str, Any]:
        ...

    @abstractmethod
    def execute(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        ...

    @abstractmethod
    def validate(self, result: Dict[str, Any]) -> bool:
        ...

    @abstractmethod
    def cleanup(self) -> None:
        ...

    def get_manifest(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": [{"name": c.name, "description": c.description} for c in self.capabilities],
            "hooks": {k: v for k, v in asdict(self.lifecycle_hooks).items() if v},
        }

    def get_state(self) -> Dict[str, Any]:
        return dict(self._state)

    def set_state(self, key: str, value: Any) -> None:
        self._state[key] = value


from dataclasses import asdict
