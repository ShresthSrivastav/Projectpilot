"""Session Manager — long-running sessions with persist, resume, recovery after restart."""
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

SESSION_DIR = Path(os.getenv("SESSION_DIR", "./session_data"))


class SessionStatus(Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    RECOVERED = "recovered"


@dataclass
class Session:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str = ""
    name: str = ""
    session_type: str = "pipeline"
    status: SessionStatus = SessionStatus.ACTIVE
    current_stage: str = ""
    completed_tasks: List[str] = field(default_factory=list)
    pending_tasks: List[str] = field(default_factory=list)
    failed_tasks: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    checkpoints: List[Dict] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    error: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    def mark_completed(self, task: str) -> None:
        if task in self.pending_tasks:
            self.pending_tasks.remove(task)
        if task not in self.completed_tasks:
            self.completed_tasks.append(task)
        self.updated_at = time.time()

    def mark_failed(self, task: str, error: str = "") -> None:
        if task in self.pending_tasks:
            self.pending_tasks.remove(task)
        if task not in self.failed_tasks:
            self.failed_tasks.append(task)
        if error:
            self.error = error
        self.updated_at = time.time()

    def progress_pct(self) -> float:
        total = len(self.completed_tasks) + len(self.pending_tasks) + len(self.failed_tasks)
        if total == 0:
            return 0.0
        return round((len(self.completed_tasks) / total) * 100, 1)


class SessionManager:
    def __init__(self):
        self.sessions: Dict[str, Session] = {}
        self._lock = threading.Lock()
        self._handlers: Dict[str, Callable] = {}
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        self._restore_sessions()

    def create_session(
        self,
        job_id: str,
        name: str = "",
        session_type: str = "pipeline",
        tasks: Optional[List[str]] = None,
        context: Optional[Dict] = None,
    ) -> Session:
        session = Session(
            job_id=job_id,
            name=name or f"Session-{job_id[:8]}",
            session_type=session_type,
            pending_tasks=tasks or [],
            context=context or {},
        )
        with self._lock:
            self.sessions[session.id] = session
        self._save_session(session)
        logger.info("Session %s created for job %s (type=%s, tasks=%d)", session.id[:8], job_id, session_type, len(session.pending_tasks))
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        return self.sessions.get(session_id)

    def list_sessions(self, job_id: Optional[str] = None, limit: int = 20) -> List[Dict]:
        with self._lock:
            sessions = list(self.sessions.values())
        if job_id:
            sessions = [s for s in sessions if s.job_id == job_id]
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return [s.to_dict() for s in sessions[:limit]]

    def update_session(self, session_id: str, **kwargs) -> Optional[Session]:
        session = self.sessions.get(session_id)
        if not session:
            return None
        for k, v in kwargs.items():
            if hasattr(session, k) and k not in ("id", "created_at"):
                setattr(session, k, v)
        session.updated_at = time.time()
        self._save_session(session)
        return session

    def complete_session(self, session_id: str) -> Optional[Session]:
        session = self.sessions.get(session_id)
        if session:
            session.status = SessionStatus.COMPLETED
            session.completed_at = time.time()
            self._save_session(session)
        return session

    def fail_session(self, session_id: str, error: str) -> Optional[Session]:
        session = self.sessions.get(session_id)
        if session:
            session.status = SessionStatus.FAILED
            session.error = error
            session.completed_at = time.time()
            self._save_session(session)
        return session

    def pause_session(self, session_id: str) -> Optional[Session]:
        session = self.sessions.get(session_id)
        if session:
            session.status = SessionStatus.PAUSED
            self._save_session(session)
        return session

    def resume_session(self, session_id: str) -> Optional[Session]:
        session = self.sessions.get(session_id)
        if session and session.status == SessionStatus.PAUSED:
            session.status = SessionStatus.ACTIVE
            self._save_session(session)
        return session

    def add_checkpoint(self, session_id: str, data: Dict) -> Optional[Session]:
        session = self.sessions.get(session_id)
        if session:
            cp = {"timestamp": time.time(), "data": data}
            session.checkpoints.append(cp)
            self._save_session(session)
        return session

    def register_handler(self, task_type: str, handler: Callable) -> None:
        self._handlers[task_type] = handler

    def execute_next_task(self, session_id: str) -> Optional[Any]:
        session = self.sessions.get(session_id)
        if not session or not session.pending_tasks:
            return None
        task = session.pending_tasks[0]
        handler = self._handlers.get(task)
        if not handler:
            session.mark_failed(task, "No handler registered")
            return None
        try:
            result = handler(session.context)
            session.mark_completed(task)
            self._save_session(session)
            return result
        except Exception as exc:
            session.mark_failed(task, str(exc))
            self._save_session(session)
            return None

    def execute_all(self, session_id: str) -> Dict[str, Any]:
        results = {}
        while True:
            result = self.execute_next_task(session_id)
            if result is None:
                break
            results[result.__class__.__name__] = result
        session = self.sessions.get(session_id)
        if session:
            if session.failed_tasks and not session.completed_tasks:
                session.status = SessionStatus.FAILED
            elif not session.pending_tasks:
                session.status = SessionStatus.COMPLETED
            session.completed_at = time.time()
            self._save_session(session)
        return results

    def _save_session(self, session: Session) -> None:
        try:
            path = SESSION_DIR / f"session_{session.id[:8]}.json"
            with open(path, "w") as f:
                json.dump(session.to_dict(), f, indent=2, default=str)
        except Exception as exc:
            logger.warning("Session save failed: %s", exc)

    def _restore_sessions(self) -> None:
        if not SESSION_DIR.exists():
            return
        for fpath in SESSION_DIR.glob("session_*.json"):
            try:
                data = json.loads(fpath.read_text())
                session = Session(
                    id=data["id"], job_id=data.get("job_id", ""),
                    name=data.get("name", ""),
                    session_type=data.get("session_type", "pipeline"),
                    status=SessionStatus(data.get("status", "active")),
                    current_stage=data.get("current_stage", ""),
                    completed_tasks=data.get("completed_tasks", []),
                    pending_tasks=data.get("pending_tasks", []),
                    failed_tasks=data.get("failed_tasks", []),
                    metrics=data.get("metrics", {}),
                    checkpoints=data.get("checkpoints", []),
                    metadata=data.get("metadata", {}),
                    context=data.get("context", {}),
                )
                if session.status == SessionStatus.ACTIVE:
                    session.status = SessionStatus.RECOVERED
                self.sessions[session.id] = session
                logger.info("Restored session %s (status=%s, tasks=%d)", session.id[:8], session.status.value, len(session.pending_tasks))
            except Exception as exc:
                logger.warning("Session restore failed for %s: %s", fpath.name, exc)


_session_manager = SessionManager()


def get_session_manager() -> SessionManager:
    return _session_manager
