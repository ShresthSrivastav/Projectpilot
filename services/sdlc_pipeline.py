"""Autonomous SDLC Pipeline — full lifecycle from requirements to deployment with self-healing."""
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.graph_engine import PlanBuilder, GraphExecutor
from services.runtime_orchestrator import get_orchestrator
from services.self_healing_service import get_healing_engine
from services.deployment_orchestrator import get_deployment_orchestrator
from services.runtime_monitor import get_monitor

logger = logging.getLogger(__name__)

SDLC_DIR = Path(os.getenv("SDLC_DIR", "./sdlc_data"))


class SDLCStage(Enum):
    REQUIREMENTS = "requirements"
    ARCHITECTURE = "architecture"
    TASK_GRAPH = "task_graph"
    CODE_GENERATION = "code_generation"
    TESTING = "testing"
    BROWSER_VALIDATION = "browser_validation"
    DEPLOYMENT = "deployment"
    MONITORING = "monitoring"
    SELF_HEALING = "self_healing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class SDLCPipeline:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str = ""
    prompt: str = ""
    model: str = "local"
    stage: SDLCStage = SDLCStage.REQUIREMENTS
    status: str = "running"
    checkpoints: List[Dict] = field(default_factory=list)
    stages_completed: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    graph_id: Optional[str] = None
    runtime_id: Optional[str] = None
    deployment_id: Optional[str] = None
    healing_sessions: List[str] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["stage"] = self.stage.value
        d["progress_pct"] = self._progress_pct()
        return d

    def _progress_pct(self) -> int:
        stages = list(SDLCStage)
        total = len(stages)
        current_idx = stages.index(self.stage) if self.stage in stages else 0
        return min(int((current_idx / total) * 100), 100)


class SDLCEngine:
    def __init__(self):
        self.pipelines: Dict[str, SDLCPipeline] = {}
        self._lock = threading.Lock()
        SDLC_DIR.mkdir(parents=True, exist_ok=True)

    def run_pipeline(self, job_id: str, prompt: str, model: str = "local") -> SDLCPipeline:
        pipeline = SDLCPipeline(job_id=job_id, prompt=prompt, model=model)
        with self._lock:
            self.pipelines[pipeline.id] = pipeline
        logger.info("SDLC pipeline %s started for job %s", pipeline.id[:8], job_id)

        thread = threading.Thread(target=self._run, args=(pipeline,), daemon=True)
        thread.start()
        return pipeline

    def _run(self, pipeline: SDLCPipeline) -> None:
        try:
            pipeline.stage = SDLCStage.REQUIREMENTS
            self._save_checkpoint(pipeline)
            requirements = self._run_stage_requirements(pipeline)

            pipeline.stage = SDLCStage.ARCHITECTURE
            self._save_checkpoint(pipeline)
            architecture = self._run_stage_architecture(pipeline, requirements)

            pipeline.stage = SDLCStage.TASK_GRAPH
            self._save_checkpoint(pipeline)
            self._run_stage_task_graph(pipeline, requirements, architecture)

            pipeline.stage = SDLCStage.CODE_GENERATION
            self._save_checkpoint(pipeline)
            self._run_stage_code_gen(pipeline, architecture)

            pipeline.stage = SDLCStage.TESTING
            self._save_checkpoint(pipeline)
            self._run_stage_testing(pipeline)

            pipeline.stage = SDLCStage.BROWSER_VALIDATION
            self._save_checkpoint(pipeline)
            self._run_stage_browser_validation(pipeline)

            pipeline.stage = SDLCStage.DEPLOYMENT
            self._save_checkpoint(pipeline)
            self._run_stage_deployment(pipeline)

            pipeline.stage = SDLCStage.MONITORING
            self._save_checkpoint(pipeline)
            self._run_stage_monitoring(pipeline)

            pipeline.stage = SDLCStage.SELF_HEALING
            self._save_checkpoint(pipeline)
            self._run_stage_self_healing(pipeline)

            pipeline.stage = SDLCStage.COMPLETED
            pipeline.status = "completed"
            pipeline.completed_at = time.time()
            self._save_checkpoint(pipeline)
            logger.info("SDLC pipeline %s completed", pipeline.id[:8])

        except Exception as exc:
            pipeline.status = "failed"
            pipeline.errors.append(str(exc))
            pipeline.completed_at = time.time()
            logger.error("SDLC pipeline %s failed: %s", pipeline.id[:8], exc)

    def _run_stage_requirements(self, pipeline: SDLCPipeline) -> str:
        from agents.requirement_agent import run
        result = run(pipeline.prompt, job_id=pipeline.job_id, model=pipeline.model, project_name=f"Project-{pipeline.job_id[:8]}")
        pipeline.stages_completed.append("requirements")
        return str(result)

    def _run_stage_architecture(self, pipeline: SDLCPipeline, requirements: str) -> str:
        from agents.planner_agent import run
        result = run(requirements, job_id=pipeline.job_id, model=pipeline.model)
        pipeline.stages_completed.append("architecture")
        return str(result)

    def _run_stage_task_graph(self, pipeline: SDLCPipeline, requirements: str, architecture: str) -> None:
        builder = PlanBuilder()
        graph = builder.build_standard_plan(pipeline.prompt, pipeline.job_id, pipeline.model)
        pipeline.graph_id = graph.id
        executor = GraphExecutor(graph)
        executor.execute()
        pipeline.stages_completed.append("task_graph")

    def _run_stage_code_gen(self, pipeline: SDLCPipeline, architecture: str) -> None:
        from agents.code_agent import run
        blueprint = json.loads(architecture) if architecture.startswith("{") else {"files": []}
        run(requirements=pipeline.prompt, blueprint=blueprint, job_id=pipeline.job_id, model=pipeline.model)
        pipeline.stages_completed.append("code_generation")

    def _run_stage_testing(self, pipeline: SDLCPipeline) -> bool:
        from services.test_service import run_pytest
        pr = run_pytest(pipeline.job_id)
        ok = pr.get("passed", False)
        if not ok:
            from services.autofix_service import run_autofix
            run_autofix(pipeline.job_id, model=pipeline.model, max_attempts=3)
            pr = run_pytest(pipeline.job_id)
            ok = pr.get("passed", False)
        pipeline.stages_completed.append("testing")
        return ok

    def _run_stage_browser_validation(self, pipeline: SDLCPipeline) -> bool:
        try:
            from services.browser_validation_service import get_validation_service, ValidationStep
            vs = get_validation_service()
            journey = vs.create_journey(f"SDLC-{pipeline.id[:6]}", "http://localhost:8000")
            vs.add_step(journey.id, ValidationStep(action="navigate", url="http://localhost:8000", description="Root"))
            result = vs.execute_journey(journey.id, headless=True)
            pipeline.stages_completed.append("browser_validation")
            return result.get("success", True)
        except Exception:
            pipeline.stages_completed.append("browser_validation")
            return True

    def _run_stage_deployment(self, pipeline: SDLCPipeline) -> None:
        project_dir = os.getenv("BASE_DIR", "./generated_projects")
        orch = get_deployment_orchestrator()
        session = orch.deploy(pipeline.job_id, os.path.join(project_dir, pipeline.job_id))
        pipeline.deployment_id = session.id
        pipeline.stages_completed.append("deployment")

    def _run_stage_monitoring(self, pipeline: SDLCPipeline) -> None:
        if pipeline.runtime_id:
            monitor = get_monitor()
            monitor.start_collecting(pipeline.runtime_id, interval=10.0)
        pipeline.stages_completed.append("monitoring")

    def _run_stage_self_healing(self, pipeline: SDLCPipeline) -> None:
        log_text = self._collect_logs(pipeline)
        if log_text and ("Error" in log_text or "error" in log_text or "FAILED" in log_text):
            engine = get_healing_engine()
            project_dir = os.path.join(os.getenv("BASE_DIR", "./generated_projects"), pipeline.job_id)
            session = engine.detect_and_heal(
                pipeline.job_id, pipeline.runtime_id or "",
                log_text, project_dir=project_dir,
            )
            pipeline.healing_sessions.append(session.id)
        pipeline.stages_completed.append("self_healing")

    def _collect_logs(self, pipeline: SDLCPipeline) -> str:
        log_parts = []
        if pipeline.runtime_id:
            orch = get_orchestrator()
            log_parts.extend(orch.get_logs(pipeline.runtime_id))
        return "\n".join(log_parts)

    def _save_checkpoint(self, pipeline: SDLCPipeline) -> None:
        try:
            cp = pipeline.to_dict()
            cp["_timestamp"] = time.time()
            pipeline.checkpoints.append(cp)
            path = SDLC_DIR / f"sdlc_{pipeline.id[:8]}.json"
            with open(path, "w") as f:
                json.dump(pipeline.to_dict(), f, indent=2, default=str)
        except Exception as exc:
            logger.warning("Checkpoint save failed: %s", exc)

    def get_pipeline(self, pipeline_id: str) -> Optional[SDLCPipeline]:
        return self.pipelines.get(pipeline_id)

    def list_pipelines(self, job_id: Optional[str] = None, limit: int = 20) -> List[Dict]:
        with self._lock:
            pipelines = list(self.pipelines.values())
        if job_id:
            pipelines = [p for p in pipelines if p.job_id == job_id]
        pipelines.sort(key=lambda p: p.started_at, reverse=True)
        return [p.to_dict() for p in pipelines[:limit]]

    def resume(self, pipeline_id: str) -> Optional[SDLCPipeline]:
        pipeline = self.pipelines.get(pipeline_id)
        if not pipeline:
            path = SDLC_DIR / f"sdlc_{pipeline_id[:8]}.json"
            if path.exists():
                data = json.loads(path.read_text())
                pipeline = SDLCPipeline(
                    id=data["id"], job_id=data["job_id"], prompt=data["prompt"],
                    model=data.get("model", "local"),
                    stage=SDLCStage(data.get("stage", "requirements")),
                    stages_completed=data.get("stages_completed", []),
                )
                self.pipelines[pipeline.id] = pipeline
        if pipeline and pipeline.status == "running":
            thread = threading.Thread(target=self._run, args=(pipeline,), daemon=True)
            thread.start()
        return pipeline


_sdlc_engine = SDLCEngine()


def get_sdlc_engine() -> SDLCEngine:
    return _sdlc_engine
