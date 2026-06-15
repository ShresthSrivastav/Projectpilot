"""Base Plugin SDK — interface for creating custom plugins."""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


class PluginType(Enum):
    TOOL = "tool"
    INTEGRATION = "integration"
    PROVIDER = "provider"
    VALIDATOR = "validator"
    WORKFLOW = "workflow"


@dataclass
class PluginManifest:
    name: str = ""
    version: str = "1.0.0"
    author: str = ""
    description: str = ""
    plugin_type: str = "tool"
    dependencies: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    compatibility: str = ">=11.0.0"
    entry_point: str = ""
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_yaml(self) -> str:
        lines = [
            f"name: {self.name}",
            f"version: {self.version}",
            f"author: {self.author}",
            f"description: {self.description}",
            f"plugin_type: {self.plugin_type}",
            f"compatibility: {self.compatibility}",
        ]
        if self.dependencies:
            lines.append(f"dependencies:\n" + "\n".join(f"  - {d}" for d in self.dependencies))
        if self.permissions:
            lines.append(f"permissions:\n" + "\n".join(f"  - {p}" for p in self.permissions))
        if self.tags:
            lines.append(f"tags:\n" + "\n".join(f"  - {t}" for t in self.tags))
        return "\n".join(lines)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PluginManifest":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class BasePlugin(ABC):
    manifest: PluginManifest = field(default_factory=lambda: PluginManifest(name="unnamed"))

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._enabled: bool = False
        self._logger = logging.getLogger(f"plugin.{self.manifest.name}")

    @abstractmethod
    def install(self) -> bool:
        ...

    @abstractmethod
    def uninstall(self) -> bool:
        ...

    @abstractmethod
    def configure(self, config: Dict[str, Any]) -> bool:
        ...

    @abstractmethod
    def validate(self) -> bool:
        ...

    def enable(self) -> bool:
        self._enabled = True
        return True

    def disable(self) -> bool:
        self._enabled = False
        return True

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def get_manifest(self) -> PluginManifest:
        return self.manifest
