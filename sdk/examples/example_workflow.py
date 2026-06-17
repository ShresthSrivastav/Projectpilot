"""Example Custom Workflow — CI/CD Pipeline Workflow.
Shows how any developer can create a custom DAG workflow without modifying platform source code.
"""
from typing import Any, Dict

from sdk.workflow_sdk.base_workflow import BaseWorkflow, WorkflowStep, WorkflowStatus


class CICDPipelineWorkflow(BaseWorkflow):
    def __init__(self, workflow_id: str = None):
        super().__init__(workflow_id)
        self.build_graph()

    def build_graph(self) -> Dict[str, WorkflowStep]:
        steps = {
            "lint": WorkflowStep(name="lint", deps=[], retries=1, timeout=120),
            "test": WorkflowStep(name="test", deps=["lint"], retries=2, timeout=300),
            "build": WorkflowStep(name="build", deps=["test"], retries=0, timeout=600),
            "deploy": WorkflowStep(name="deploy", deps=["build"], retries=1, timeout=300),
        }
        for sid, step in steps.items():
            self.add_step(step)
        return steps

    def execute(self) -> Dict[str, Any]:
        graph = self.build_graph()
        results = {}
        for step_id, step in graph.items():
            deps_ok = all(results.get(d, {}).get("status") == "passed" for d in step.deps)
            if not deps_ok:
                results[step_id] = {"status": "skipped", "reason": "dependencies not met"}
                continue
            # Simulate execution
            results[step_id] = {"status": "passed", "duration_s": 10}
            self.save_checkpoint({step_id: results[step_id]})
        self.status = WorkflowStatus.COMPLETED
        return {"status": self.status.value, "results": results}

    def monitor(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.id,
            "status": self.status.value,
            "step_count": len(self.steps),
            "checkpoints": len(self._checkpoints),
        }
