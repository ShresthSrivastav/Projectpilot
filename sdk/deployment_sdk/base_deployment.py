"""Base Deployment SDK — interface for creating custom deployment targets."""
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class DeploymentConfig:
    target: str = ""
    project_dir: str = ""
    region: str = "us-east-1"
    instance_type: str = "t2.micro"
    replicas: int = 1
    env_vars: Dict[str, str] = field(default_factory=dict)
    timeout: int = 600
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class DeploymentResult:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    success: bool = False
    url: str = ""
    error: str = ""
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BaseDeploymentTarget(ABC):
    def __init__(self, config: Optional[DeploymentConfig] = None):
        self.config = config or DeploymentConfig()
        self._logger = logging.getLogger(f"deploy.{self.__class__.__name__}")

    @abstractmethod
    def deploy(self) -> DeploymentResult:
        ...

    @abstractmethod
    def verify(self, result: DeploymentResult) -> bool:
        ...

    @abstractmethod
    def rollback(self, result: DeploymentResult) -> bool:
        ...

    def get_config(self) -> DeploymentConfig:
        return self.config

    def validate_config(self) -> List[str]:
        errors = []
        if not self.config.project_dir:
            errors.append("project_dir is required")
        return errors
