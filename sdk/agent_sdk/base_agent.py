"""Base Agent SDK — interface for creating custom agents."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentCapability:
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentLifecycleHook:
    on_initialize: str | None = None
    on_plan: str | None = None
    on_execute: str | None = None
    on_validate: str | None = None
    on_cleanup: str | None = None


class BaseAgent(ABC):
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    capabilities: list[AgentCapability] = []
    lifecycle_hooks: AgentLifecycleHook = field(default_factory=AgentLifecycleHook)

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self._state: dict[str, Any] = {}
        self._logger = logging.getLogger(f"agent.{self.name}")

    @abstractmethod
    def initialize(self) -> bool: ...

    @abstractmethod
    def plan(self, context: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def execute(self, plan: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def validate(self, result: dict[str, Any]) -> bool: ...

    @abstractmethod
    def cleanup(self) -> None: ...

    def get_manifest(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": [{"name": c.name, "description": c.description} for c in self.capabilities],
            "hooks": {k: v for k, v in asdict(self.lifecycle_hooks).items() if v},
        }

    def get_state(self) -> dict[str, Any]:
        return dict(self._state)

    def set_state(self, key: str, value: Any) -> None:
        self._state[key] = value


from dataclasses import asdict
