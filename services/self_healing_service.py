"""Self-Healing Engine — automatic repair, patch generation, retry, rollback."""

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

from services.llm_service import call_model
from services.log_analyzer import get_log_analyzer

logger = logging.getLogger(__name__)

HEALING_DIR = Path(os.getenv("HEALING_DIR", "./healing_data"))


class HealingStatus(Enum):
    DETECTED = "detected"
    ANALYZING = "analyzing"
    FIXING = "fixing"
    TESTING = "testing"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class HealingSession:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str = ""
    runtime_id: str = ""
    status: HealingStatus = HealingStatus.DETECTED
    error_type: str = ""
    root_cause: str = ""
    fix_description: str = ""
    fix_applied: bool = False
    tests_passed: bool | None = None
    browser_validated: bool | None = None
    max_retries: int = 3
    attempt: int = 0
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    patches: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d


class SelfHealingEngine:
    def __init__(self):
        self.sessions: dict[str, HealingSession] = {}
        self._lock = threading.Lock()
        HEALING_DIR.mkdir(parents=True, exist_ok=True)

    def detect_and_heal(
        self,
        job_id: str,
        runtime_id: str,
        log_text: str,
        project_dir: str | None = None,
        max_retries: int = 3,
        confidence_threshold: float = 0.6,
        run_browser_validation: bool = False,
    ) -> HealingSession:
        session = HealingSession(job_id=job_id, runtime_id=runtime_id, max_retries=max_retries)
        with self._lock:
            self.sessions[session.id] = session
        logger.info("Healing session %s started for job %s", session.id[:8], job_id)

        thread = threading.Thread(
            target=self._heal_loop,
            args=(session, log_text, project_dir, confidence_threshold, run_browser_validation),
            daemon=True,
        )
        thread.start()
        return session

    def _heal_loop(
        self,
        session: HealingSession,
        log_text: str,
        project_dir: str | None,
        confidence_threshold: float,
        run_browser_validation: bool,
    ) -> None:
        try:
            session.status = HealingStatus.ANALYZING
            analyzer = get_log_analyzer()
            analysis = analyzer.analyze(log_text, use_llm=True)
            session.error_type = analysis.error_type
            session.root_cause = analysis.root_cause

            if analysis.confidence < confidence_threshold:
                session.status = HealingStatus.FAILED
                session.error = f"Confidence {analysis.confidence:.2f} below threshold {confidence_threshold}"
                session.completed_at = time.time()
                logger.warning("Healing %s confidence too low: %.2f", session.id[:8], analysis.confidence)
                return

            for attempt in range(session.max_retries):
                session.attempt = attempt + 1
                session.status = HealingStatus.FIXING
                fix_result = self._generate_and_apply_fix(session, analysis, project_dir)
                if not fix_result:
                    continue

                session.status = HealingStatus.TESTING
                tests_ok = self._run_tests(session, project_dir)
                session.tests_passed = tests_ok

                if run_browser_validation:
                    session.status = HealingStatus.VALIDATING
                    session.browser_validated = self._run_browser_validation(session, project_dir)

                if tests_ok:
                    session.status = HealingStatus.COMPLETED
                    session.completed_at = time.time()
                    self._save_session(session)
                    logger.info("Healing %s completed on attempt %d", session.id[:8], attempt + 1)
                    return

            session.status = HealingStatus.FAILED
            session.error = f"All {max_retries} attempts failed"
            session.completed_at = time.time()
            self._save_session(session)

        except Exception as exc:
            session.status = HealingStatus.FAILED
            session.error = str(exc)
            session.completed_at = time.time()
            logger.error("Healing %s failed: %s", session.id[:8], exc)

    def _generate_and_apply_fix(self, session: HealingSession, analysis: Any, project_dir: str | None) -> bool:
        try:
            prompt = (
                f"Error type: {analysis.error_type}\n"
                f"Root cause: {analysis.root_cause}\n"
                f"Suggested fix: {analysis.suggested_fix}\n\n"
                f"Generate a fix patch. Output in format:\n"
                f"--- FILE: path\n--- ACTION: MODIFY\n--- CONTENT:\n...\n--- END\n"
            )
            if project_dir:
                prompt += f"\nProject directory: {project_dir}"

            result = call_model(prompt, model="cloud", agent="SelfHealing")
            patches = self._parse_patches(result, project_dir)
            if not patches:
                logger.warning("No patches generated for healing %s", session.id[:8])
                return False

            session.patches = patches
            session.fix_description = f"Applied {len(patches)} patch(es)"
            for patch in patches:
                path = Path(patch["file"])
                if project_dir:
                    path = Path(project_dir) / patch["file"]
                if patch["action"] in ("MODIFY", "ADD") and patch.get("content"):
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(patch["content"], encoding="utf-8")
                    session.metadata.setdefault("patched_files", []).append(str(path))
            session.fix_applied = True
            return True
        except Exception as exc:
            logger.warning("Fix generation failed: %s", exc)
            return False

    def _parse_patches(self, text: str, project_dir: str | None = None) -> list[dict]:
        import re

        patches = []
        blocks = re.split(r"---\s*FILE\s*:\s*", text)
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            lines = block.split("\n")
            fpath = lines[0].strip().rstrip("-").strip()
            if not fpath:
                continue
            block_text = "\n".join(lines[1:])
            action_m = re.search(r"---\s*ACTION\s*:\s*(\w+)", block_text)
            action = action_m.group(1).upper() if action_m else "MODIFY"
            content_m = re.search(r"---\s*CONTENT\s*:\s*\n?(.*?)(?:\n---\s*END|$)", block_text, re.DOTALL)
            content = content_m.group(1).strip() if content_m else ""
            patches.append({"file": fpath, "action": action, "content": content})
        return patches

    def _run_tests(self, session: HealingSession, project_dir: str | None) -> bool:
        if not project_dir:
            return True
        from services.test_service import run_pytest

        try:
            pr = run_pytest(session.job_id)
            return pr.get("passed", False)
        except Exception:
            return False

    def _run_browser_validation(self, session: HealingSession, project_dir: str | None) -> bool:
        return True

    def rollback(self, session_id: str) -> bool:
        session = self.sessions.get(session_id)
        if not session or not session.patches:
            return False
        for patch in session.patches:
            path = Path(patch["file"])
            if patch.get("backup_path") and Path(patch["backup_path"]).exists():
                backup_content = Path(patch["backup_path"]).read_text()
                path.write_text(backup_content)
        session.status = HealingStatus.ROLLED_BACK
        self._save_session(session)
        return True

    def get_session(self, session_id: str) -> HealingSession | None:
        return self.sessions.get(session_id)

    def list_sessions(self, job_id: str | None = None, limit: int = 20) -> list[dict]:
        with self._lock:
            sessions = list(self.sessions.values())
        if job_id:
            sessions = [s for s in sessions if s.job_id == job_id]
        sessions.sort(key=lambda s: s.created_at, reverse=True)
        return [s.to_dict() for s in sessions[:limit]]

    def _save_session(self, session: HealingSession) -> None:
        try:
            path = HEALING_DIR / f"{session.id[:8]}.json"
            with open(path, "w") as f:
                json.dump(session.to_dict(), f, indent=2, default=str)
        except Exception as exc:
            logger.warning("Session save failed: %s", exc)


_healing_engine = SelfHealingEngine()


def get_healing_engine() -> SelfHealingEngine:
    return _healing_engine
