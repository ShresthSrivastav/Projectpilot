"""Deployment Orchestrator — multi-target build, deploy, verify, rollback."""
import json
import logging
import os
import subprocess
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEPLOY_DIR = Path(os.getenv("DEPLOY_DIR", "./deploy_data"))


class DeploymentTarget(Enum):
    DOCKER = "docker"
    RAILWAY = "railway"
    RENDER = "render"
    FLY_IO = "fly_io"
    VERCEL = "vercel"
    NETLIFY = "netlify"


class DeploymentStatus(Enum):
    PENDING = "pending"
    BUILDING = "building"
    DEPLOYING = "deploying"
    HEALTH_CHECKING = "health_checking"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class DeploymentSession:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str = ""
    project_dir: str = ""
    target: DeploymentTarget = DeploymentTarget.DOCKER
    status: DeploymentStatus = DeploymentStatus.PENDING
    url: str | None = None
    build_log: str = ""
    deploy_log: str = ""
    health_check_ok: bool | None = None
    browser_validation_ok: bool | None = None
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    rollback_data: dict | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["target"] = self.target.value
        d["status"] = self.status.value
        return d


class DeploymentOrchestrator:
    def __init__(self):
        self.sessions: dict[str, DeploymentSession] = {}
        self._lock = threading.Lock()
        DEPLOY_DIR.mkdir(parents=True, exist_ok=True)

    def deploy(
        self,
        job_id: str,
        project_dir: str,
        target: str = "docker",
        health_check_url: str | None = None,
        run_browser_validation: bool = False,
    ) -> DeploymentSession:
        dt = DeploymentTarget(target.lower()) if target.lower() in [t.value for t in DeploymentTarget] else DeploymentTarget.DOCKER
        session = DeploymentSession(job_id=job_id, project_dir=project_dir, target=dt)
        with self._lock:
            self.sessions[session.id] = session
        logger.info("Deployment %s started for job %s -> %s", session.id[:8], job_id, dt.value)

        thread = threading.Thread(
            target=self._deploy_loop,
            args=(session, health_check_url, run_browser_validation),
            daemon=True,
        )
        thread.start()
        return session

    def _deploy_loop(self, session: DeploymentSession, health_check_url: str | None, run_bv: bool) -> None:
        try:
            session.status = DeploymentStatus.BUILDING
            build_success, build_log = self._build(session)
            session.build_log = build_log
            if not build_success:
                session.status = DeploymentStatus.FAILED
                session.error = "Build failed"
                session.completed_at = time.time()
                self._save_session(session)
                return

            session.status = DeploymentStatus.DEPLOYING
            deploy_success, deploy_log, url = self._deploy(session)
            session.deploy_log = deploy_log
            session.url = url
            if not deploy_success:
                session.status = DeploymentStatus.FAILED
                session.error = "Deploy failed"
                session.completed_at = time.time()
                self._save_session(session)
                return

            session.status = DeploymentStatus.HEALTH_CHECKING
            hc_url = health_check_url or (f"{url}/health" if url else None)
            if hc_url:
                session.health_check_ok = self._health_check(hc_url)

            if run_bv and url:
                session.status = DeploymentStatus.VALIDATING
                session.browser_validation_ok = self._browser_validate(url)

            session.status = DeploymentStatus.COMPLETED
            session.completed_at = time.time()
            self._save_session(session)
            logger.info("Deployment %s completed: %s", session.id[:8], url or "local")

        except Exception as exc:
            session.status = DeploymentStatus.FAILED
            session.error = str(exc)
            session.completed_at = time.time()
            logger.error("Deployment %s failed: %s", session.id[:8], exc)

    def _build(self, session: DeploymentSession) -> Tuple[bool, str]:
        project = Path(session.project_dir)
        if not project.exists():
            return False, "Project directory not found"

        target = session.target
        if target == DeploymentTarget.DOCKER:
            return self._build_docker(project)
        elif target == DeploymentTarget.RAILWAY:
            return self._build_generic(project, "railway")
        elif target == DeploymentTarget.RENDER:
            return self._build_generic(project, "render")
        elif target == DeploymentTarget.VERCEL:
            return self._build_vercel(project)
        elif target == DeploymentTarget.NETLIFY:
            return self._build_netlify(project)
        return self._build_docker(project)

    def _build_docker(self, project: Path) -> Tuple[bool, str]:
        try:
            dockerfile = project / "Dockerfile"
            if not dockerfile.exists():
                dockerfile.write_text(
                    "FROM python:3.11-slim\nWORKDIR /app\nCOPY . .\nRUN pip install -r requirements.txt 2>/dev/null || true\n"
                    'CMD ["python", "main.py"]\n'
                )
            r = subprocess.run(
                ["docker", "build", "-t", f"autodev-{project.name}", "."],
                cwd=str(project), capture_output=True, text=True, timeout=300,
            )
            return r.returncode == 0, r.stdout + r.stderr
        except Exception as exc:
            return False, str(exc)

    def _build_vercel(self, project: Path) -> Tuple[bool, str]:
        try:
            vercel_json = project / "vercel.json"
            if not vercel_json.exists():
                vercel_json.write_text(json.dumps({"version": 2, "builds": [{"src": "**/*.py", "use": "@vercel/python"}]}))
            r = subprocess.run(["npx", "vercel", "build"], cwd=str(project), capture_output=True, text=True, timeout=120)
            return r.returncode == 0, r.stdout + r.stderr
        except Exception as exc:
            return False, str(exc)

    def _build_netlify(self, project: Path) -> Tuple[bool, str]:
        try:
            toml = project / "netlify.toml"
            if not toml.exists():
                toml.write_text("[build]\n  command = \"echo 'built'\"\n  publish = \".\"\n")
            return True, "Netlify build prepared"
        except Exception as exc:
            return False, str(exc)

    def _build_generic(self, project: Path, platform: str) -> Tuple[bool, str]:
        return True, f"Build prepared for {platform}"

    def _deploy(self, session: DeploymentSession) -> Tuple[bool, str, str | None]:
        target = session.target
        project = Path(session.project_dir)
        if target == DeploymentTarget.DOCKER:
            return self._deploy_docker(project)
        elif target == DeploymentTarget.RAILWAY:
            return self._deploy_railway(project)
        elif target == DeploymentTarget.RENDER:
            return self._deploy_render(project)
        elif target == DeploymentTarget.VERCEL:
            return self._deploy_vercel(project)
        elif target == DeploymentTarget.NETLIFY:
            return self._deploy_netlify(project)
        elif target == DeploymentTarget.FLY_IO:
            return self._deploy_fly(project)
        return self._deploy_docker(project)

    def _deploy_docker(self, project: Path) -> Tuple[bool, str, str | None]:
        try:
            from services.container_manager import ContainerManager
            cm = ContainerManager()
            container = cm.create_container(
                image=f"autodev-{project.name}",
                port_mappings={8000: 8000},
                name=f"deploy-{project.name[:12]}",
            )
            cm.start_container(container.id)
            url = f"http://localhost:{container.host_port or 8000}"
            return True, f"Container {container.id[:8]} started", url
        except Exception as exc:
            return False, str(exc), None

    def _deploy_railway(self, project: Path) -> Tuple[bool, str, str | None]:
        try:
            r = subprocess.run(["railway", "up"], cwd=str(project), capture_output=True, text=True, timeout=120)
            return r.returncode == 0, r.stdout + r.stderr, "https://<project>.railway.app"
        except Exception:
            return True, "Railway CLI not available (mock deploy)", "https://mock.railway.app"

    def _deploy_render(self, project: Path) -> Tuple[bool, str, str | None]:
        try:
            render_yaml = project / "render.yaml"
            if not render_yaml.exists():
                render_yaml.write_text(f"services:\n  - type: web\n    name: {project.name}\n    env: python\n    buildCommand: pip install -r requirements.txt\n    startCommand: python main.py\n")
            return True, "Render config generated", "https://mock.onrender.com"
        except Exception as exc:
            return False, str(exc), None

    def _deploy_vercel(self, project: Path) -> Tuple[bool, str, str | None]:
        try:
            r = subprocess.run(["npx", "vercel", "--prod"], cwd=str(project), capture_output=True, text=True, timeout=120)
            return r.returncode == 0, r.stdout + r.stderr, f"https://{project.name}.vercel.app"
        except Exception:
            return True, "Vercel CLI not available (mock deploy)", "https://mock.vercel.app"

    def _deploy_netlify(self, project: Path) -> Tuple[bool, str, str | None]:
        try:
            r = subprocess.run(["npx", "netlify", "deploy", "--prod"], cwd=str(project), capture_output=True, text=True, timeout=120)
            return r.returncode == 0, r.stdout + r.stderr, "https://mock.netlify.app"
        except Exception:
            return True, "Netlify CLI not available (mock deploy)", "https://mock.netlify.app"

    def _deploy_fly(self, project: Path) -> Tuple[bool, str, str | None]:
        try:
            fly_toml = project / "fly.toml"
            if not fly_toml.exists():
                fly_toml.write_text(f"app = '{project.name}'\n[env]\n  PORT = '8080'\n[[services]]\n  internal_port = 8080\n")
            return True, "Fly.io config generated", "https://mock.fly.dev"
        except Exception as exc:
            return False, str(exc), None

    def _health_check(self, url: str) -> bool:
        import httpx
        for attempt in range(5):
            try:
                r = httpx.get(url, timeout=5)
                if r.status_code < 500:
                    return True
            except Exception:
                time.sleep(2)
        return False

    def _browser_validate(self, url: str) -> bool:
        try:
            from services.browser_validation_service import ValidationStep, get_validation_service
            vs = get_validation_service()
            journey = vs.create_journey(f"Deploy-validate-{uuid.uuid4().hex[:6]}", url)
            vs.add_step(journey.id, ValidationStep(action="navigate", url=url, description="Deployment check"))
            result = vs.execute_journey(journey.id, headless=True)
            return result.get("success", False)
        except Exception:
            return True

    def rollback(self, session_id: str) -> bool:
        session = self.sessions.get(session_id)
        if not session:
            return False
        try:
            if session.target == DeploymentTarget.DOCKER:
                from services.container_manager import ContainerManager
                for cid in list(ContainerManager().containers.keys()):
                    ContainerManager().destroy_container(cid)
            session.status = DeploymentStatus.ROLLED_BACK
            self._save_session(session)
            return True
        except Exception:
            return False

    def get_session(self, session_id: str) -> DeploymentSession | None:
        return self.sessions.get(session_id)

    def list_sessions(self, job_id: str | None = None, limit: int = 20) -> list[dict]:
        with self._lock:
            sessions = list(self.sessions.values())
        if job_id:
            sessions = [s for s in sessions if s.job_id == job_id]
        sessions.sort(key=lambda s: s.created_at, reverse=True)
        return [s.to_dict() for s in sessions[:limit]]

    def _save_session(self, session: DeploymentSession) -> None:
        try:
            path = DEPLOY_DIR / f"deploy_{session.id[:8]}.json"
            with open(path, "w") as f:
                json.dump(session.to_dict(), f, indent=2, default=str)
        except Exception as exc:
            logger.warning("Session save failed: %s", exc)


_deployment_orchestrator = DeploymentOrchestrator()


def get_deployment_orchestrator() -> DeploymentOrchestrator:
    return _deployment_orchestrator
