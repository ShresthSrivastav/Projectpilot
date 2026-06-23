"""AgentContext — explicit per-pipeline context for workspace isolation.

Replaces hidden ContextVar dependency. Every agent and storage
operation receives workspace_id explicitly through this context object.
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentContext:
    """Explicit context propagated through the entire agent pipeline.

    Fields:
        workspace_id: The target ChromaDB/memory store workspace.
        user_id:      The user who initiated this pipeline.
        job_id:       The generation job identifier.
        project_name: Human-readable project name.
        request_id:   Unique id for this request (for log correlation).
        extra:        Additional metadata (model, stack, etc.).
    """
    workspace_id: str = ""
    user_id: str = ""
    job_id: str = ""
    project_name: str = ""
    request_id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_isolated(self) -> bool:
        """True when a non-empty workspace_id is set."""
        return bool(self.workspace_id)
