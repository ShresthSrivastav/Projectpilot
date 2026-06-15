"""Example Custom Agent — Documentation Generator Agent.
Shows how any developer can create a custom agent without modifying platform source code.
"""
from typing import Any, Dict, List, Optional

from sdk.agent_sdk.base_agent import BaseAgent, AgentCapability, AgentLifecycleHook


class DocGenAgent(BaseAgent):
    name = "docgen-agent"
    description = "Generates project documentation from source code"
    version = "1.0.0"
    capabilities = [
        AgentCapability(name="generate-readme", description="Generate README.md from project structure"),
        AgentCapability(name="generate-api-docs", description="Extract and document API endpoints"),
    ]
    lifecycle_hooks = AgentLifecycleHook(
        on_initialize="load_project_config",
        on_execute="generate_documentation",
    )

    def initialize(self) -> bool:
        self._state["ready"] = True
        return True

    def plan(self, context: Dict[str, Any]) -> Dict[str, Any]:
        project_path = context.get("project_path", ".")
        return {
            "steps": [
                {"action": "scan_project", "params": {"path": project_path}},
                {"action": "generate_readme", "params": {}},
                {"action": "generate_api_docs", "params": {}},
            ],
            "estimated_tokens": 5000,
        }

    def execute(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        results = []
        for step in plan.get("steps", []):
            if step["action"] == "scan_project":
                results.append({"action": "scan_project", "status": "completed", "files_found": 42})
            elif step["action"] == "generate_readme":
                results.append({"action": "generate_readme", "status": "completed", "output": "README.md"})
            elif step["action"] == "generate_api_docs":
                results.append({"action": "generate_api_docs", "status": "completed", "output": "docs/api.md"})
        return {"results": results, "status": "completed"}

    def validate(self, result: Dict[str, Any]) -> bool:
        return result.get("status") == "completed"

    def cleanup(self) -> None:
        self._state.clear()
