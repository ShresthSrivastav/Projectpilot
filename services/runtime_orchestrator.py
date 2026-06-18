"""Runtime Orchestrator — execution environment lifecycle, monitoring, checkpointing, recovery."""
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

RUNTIME_DIR = Path(os.getenv("RUNTIME_DIR", "./runtime_data"))


class RuntimeStatus(Enum):
    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    DESTROYED = "destroyed"


class RuntimeType(Enum):
    DOCKER = "docker"
    SUBPROCESS = "subprocess"


@dataclass
class ExecutionEnvironment:
    runtime_type: RuntimeType = RuntimeType.SUBPROCESS
    image: str = "python:3.11-slim"
    command: list[str] = field(default_factory=list)
    working_dir: str = ""
    env_vars: dict[str, str] = field(default_factory=dict)
    port_mappings: dict[int, int] = field(default_factory=dict)
    memory_limit: str = "256m"
    cpu_limit: float = 0.5
    network_enabled: bool = True
    volumes: list[str] = field(default_factory=list)
    timeout: int = 300


@dataclass
class RuntimeSession:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str = ""
    name: str = ""
    status: RuntimeStatus = RuntimeStatus.CREATED
    runtime_type: RuntimeType = RuntimeType.SUBPROCESS
    environment: ExecutionEnvironment = field(default_factory=ExecutionEnvironment)
    container_id: str | None = None
    pid: int | None = None
    port: int | None = None
    host: str = "localhost"
    started_at: float | None = None
    stopped_at: float | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    checkpoint_path: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["runtime_type"] = self.runtime_type.value
        return d


class RuntimeOrchestrator:
    def __init__(self):
        self.sessions: dict[str, RuntimeSession] = {}
        self._lock = threading.Lock()
        self._monitors: dict[str, threading.Thread] = {}
        self._running = False
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        self._start_health_monitor()

    def _start_health_monitor(self) -> None:
        def _monitor():
            while self._running:
                with self._lock:
                    for sid, session in list(self.sessions.items()):
                        if session.status == RuntimeStatus.RUNNING and session.started_at:
                            elapsed = time.time() - session.started_at
                            timeout = session.environment.timeout
                            if timeout > 0 and elapsed > timeout:
                                session.status = RuntimeStatus.FAILED
                                session.error = f"Runtime timeout after {timeout}s"
                                logger.warning("Runtime %s timed out", sid[:8])
                time.sleep(10)
        self._running = True
        t = threading.Thread(target=_monitor, daemon=True)
        t.start()

    def create_runtime(self, job_id: str, name: str = "", env: ExecutionEnvironment | None = None) -> RuntimeSession:
        env = env or ExecutionEnvironment()
        session = RuntimeSession(
            job_id=job_id,
            name=name or f"Runtime-{job_id[:8]}",
            environment=env,
            runtime_type=env.runtime_type,
        )
        with self._lock:
            self.sessions[session.id] = session
        self._save_checkpoint(session)
        logger.info("Runtime %s created for job %s (type=%s)", session.id[:8], job_id, env.runtime_type.value)
        return session

    def start_runtime(self, session_id: str) -> RuntimeSession:
        session = self._get_session(session_id)
        if session.status not in (RuntimeStatus.CREATED, RuntimeStatus.STOPPED, RuntimeStatus.FAILED):
            raise ValueError(f"Cannot start runtime in status {session.status.value}")

        session.status = RuntimeStatus.STARTING
        self._save_checkpoint(session)

        try:
            if session.runtime_type == RuntimeType.DOCKER:
                self._start_docker(session)
            else:
                self._start_subprocess(session)
            session.status = RuntimeStatus.RUNNING
            session.started_at = time.time()
            self._save_checkpoint(session)
            logger.info("Runtime %s started on port %s", session_id[:8], session.port)
        except Exception as exc:
            session.status = RuntimeStatus.FAILED
            session.error = str(exc)
            self._save_checkpoint(session)
            logger.error("Runtime %s start failed: %s", session_id[:8], exc)
            raise RuntimeError(f"Runtime start failed: {exc}") from exc

        return session

    def _start_docker(self, session: RuntimeSession) -> None:
        from services.container_manager import ContainerManager
        cm = ContainerManager()
        container = cm.create_container(
            image=session.environment.image,
            command=session.environment.command,
            env_vars=session.environment.env_vars,
            port_mappings=session.environment.port_mappings,
            memory_limit=session.environment.memory_limit,
            cpu_limit=session.environment.cpu_limit,
            network_enabled=session.environment.network_enabled,
            volumes=session.environment.volumes,
            working_dir=session.environment.working_dir,
        )
        cm.start_container(container.id)
        session.container_id = container.id
        session.port = container.host_port

    def _start_subprocess(self, session: RuntimeSession) -> None:
        from services.process_manager import ProcessManager
        pm = ProcessManager()
        workdir = session.environment.working_dir or str(RUNTIME_DIR / session.id)
        Path(workdir).mkdir(parents=True, exist_ok=True)
        proc = pm.run_detached(
            command=session.environment.command or ["python", "-m", "http.server", "0"],
            working_dir=workdir,
            env_vars=session.environment.env_vars,
            timeout=session.environment.timeout,
        )
        session.pid = proc.pid
        session.port = proc.port

    def stop_runtime(self, session_id: str) -> RuntimeSession:
        session = self._get_session(session_id)
        session.status = RuntimeStatus.STOPPING
        try:
            if session.runtime_type == RuntimeType.DOCKER and session.container_id:
                from services.container_manager import ContainerManager
                ContainerManager().stop_container(session.container_id)
            elif session.pid:
                from services.process_manager import ProcessManager
                pm = ProcessManager()
                if pm.is_running(session.pid):
                    pm.terminate(session.pid)
            session.status = RuntimeStatus.STOPPED
            session.stopped_at = time.time()
            self._save_checkpoint(session)
            logger.info("Runtime %s stopped", session_id[:8])
        except Exception as exc:
            session.status = RuntimeStatus.FAILED
            session.error = str(exc)
            logger.error("Runtime %s stop failed: %s", session_id[:8], exc)
        return session

    def restart_runtime(self, session_id: str) -> RuntimeSession:
        self.stop_runtime(session_id)
        time.sleep(1)
        return self.start_runtime(session_id)

    def destroy_runtime(self, session_id: str) -> None:
        session = self._get_session(session_id)
        try:
            if session.runtime_type == RuntimeType.DOCKER and session.container_id:
                from services.container_manager import ContainerManager
                ContainerManager().destroy_container(session.container_id)
            elif session.pid:
                from services.process_manager import ProcessManager
                ProcessManager().terminate(session.pid)
        except Exception as exc:
            logger.warning("Runtime %s destroy cleanup failed: %s", session_id[:8], exc)
        session.status = RuntimeStatus.DESTROYED
        self._save_checkpoint(session)
        logger.info("Runtime %s destroyed", session_id[:8])

    def get_runtime(self, session_id: str) -> RuntimeSession | None:
        return self.sessions.get(session_id)

    def list_runtimes(self, job_id: str | None = None) -> list[dict]:
        with self._lock:
            sessions = list(self.sessions.values())
        if job_id:
            sessions = [s for s in sessions if s.job_id == job_id]
        return [s.to_dict() for s in sorted(sessions, key=lambda x: x.started_at or 0, reverse=True)]

    def get_logs(self, session_id: str, tail: int = 100) -> list[str]:
        session = self._get_session(session_id)
        log_path = RUNTIME_DIR / session.id / "output.log"
        if not log_path.exists():
            return []
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-tail:]

    def get_metrics(self, session_id: str) -> dict[str, Any]:
        session = self._get_session(session_id)
        metrics = {
            "session_id": session_id,
            "status": session.status.value,
            "uptime": 0,
            "cpu_percent": 0.0,
            "memory_mb": 0.0,
        }
        if session.started_at and session.status == RuntimeStatus.RUNNING:
            metrics["uptime"] = time.time() - session.started_at
        if session.container_id:
            try:
                from services.container_manager import ContainerManager
                stats = ContainerManager().get_stats(session.container_id)
                metrics.update(stats)
            except Exception:
                pass
        elif session.pid:
            try:
                import psutil
                proc = psutil.Process(session.pid)
                metrics["cpu_percent"] = proc.cpu_percent()
                metrics["memory_mb"] = proc.memory_info().rss / 1024 / 1024
            except Exception:
                pass
        return metrics

    def recover_failure(self, session_id: str) -> RuntimeSession | None:
        session = self._get_session(session_id)
        if session.status != RuntimeStatus.FAILED:
            return session
        logger.info("Attempting recovery of runtime %s", session_id[:8])
        try:
            return self.restart_runtime(session_id)
        except Exception as exc:
            logger.error("Recovery failed for runtime %s: %s", session_id[:8], exc)
            return None

    def _get_session(self, session_id: str) -> RuntimeSession:
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError(f"Runtime session {session_id} not found")
        return session

    def _save_checkpoint(self, session: RuntimeSession) -> None:
        try:
            cp_dir = RUNTIME_DIR / session.id
            cp_dir.mkdir(parents=True, exist_ok=True)
            path = cp_dir / "checkpoint.json"
            with open(path, "w") as f:
                json.dump(session.to_dict(), f, indent=2, default=str)
            session.checkpoint_path = str(path)
        except Exception as exc:
            logger.warning("Checkpoint save failed: %s", exc)

    def load_checkpoint(self, session_id: str) -> RuntimeSession | None:
        path = RUNTIME_DIR / session_id / "checkpoint.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            session = RuntimeSession(
                id=data["id"], job_id=data.get("job_id", ""),
                name=data.get("name", ""),
                status=RuntimeStatus(data.get("status", "created")),
                runtime_type=RuntimeType(data.get("runtime_type", "subprocess")),
                container_id=data.get("container_id"),
                pid=data.get("pid"), port=data.get("port"),
                host=data.get("host", "localhost"),
                started_at=data.get("started_at"),
                stopped_at=data.get("stopped_at"),
                error=data.get("error"),
            )
            self.sessions[session_id] = session
            return session
        except Exception as exc:
            logger.warning("Checkpoint load failed: %s", exc)
            return None

    def shutdown(self) -> None:
        self._running = False
        for sid in list(self.sessions.keys()):
            try:
                self.stop_runtime(sid)
            except Exception:
                pass


_orchestrator = RuntimeOrchestrator()


def get_orchestrator() -> RuntimeOrchestrator:
    return _orchestrator
