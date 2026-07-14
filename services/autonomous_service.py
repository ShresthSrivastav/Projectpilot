"""Autonomous Iteration Mode — generate-evaluate-improve-retest loop with metrics tracking and cost per iteration."""

import logging
import os
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from services.llm_service import call_model, get_token_count

logger = logging.getLogger(__name__)

AUTONOMOUS_DIR = Path(os.getenv("AUTONOMOUS_DIR", "./autonomous_data"))

TEXT_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".vue",
    ".svelte",
    ".html",
    ".css",
    ".scss",
    ".less",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".md",
    ".txt",
    ".rst",
    ".sh",
    ".bat",
    ".ps1",
    ".env",
    ".xml",
    ".svg",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".java",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".sql",
    ".graphql",
    ".dockerfile",
    ".gitignore",
}


class IterationStage(Enum):
    GENERATE = "generate"
    EVALUATE = "evaluate"
    IMPROVE = "improve"
    RETEST = "retest"
    REVIEW = "review"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class IterationMetrics:
    iteration: int = 0
    score: float = 0.0
    tokens_used: int = 0
    duration_ms: float = 0.0
    test_passed: int = 0
    test_total: int = 0
    code_quality: float = 0.0
    coverage_pct: float = 0.0
    improvement_delta: float = 0.0
    cost_estimate: float = 0.0
    stage: str = "pending"
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class AutonomousConfig:
    max_iterations: int = 10
    quality_threshold: float = 0.85
    improvement_threshold: float = 0.01
    max_consecutive_no_improvement: int = 3
    auto_fix_tests: bool = True
    run_syntax_check: bool = True
    run_security_scan: bool = True
    generate_reports: bool = True
    model: str = "local"
    review_model: str = "local"
    cost_per_token: float = 0.00001


@dataclass
class AutonomousSession:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str = ""
    config: AutonomousConfig = field(default_factory=AutonomousConfig)
    iterations: list[IterationMetrics] = field(default_factory=list)
    current_iteration: int = 0
    status: str = "pending"
    stage: IterationStage = IterationStage.GENERATE
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    total_tokens: int = 0
    total_duration_ms: float = 0.0
    initial_score: float = 0.0
    final_score: float = 0.0
    improvement_pct: float = 0.0
    total_cost: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "config": asdict(self.config),
            "iterations": [asdict(m) for m in self.iterations],
            "current_iteration": self.current_iteration,
            "status": self.status,
            "stage": self.stage.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "total_tokens": self.total_tokens,
            "total_duration_ms": self.total_duration_ms,
            "initial_score": self.initial_score,
            "final_score": self.final_score,
            "improvement_pct": round(self.improvement_pct, 2),
            "total_cost": round(self.total_cost, 6),
            "iteration_count": len(self.iterations),
        }


class AutonomousEngine:
    def __init__(self):
        self.sessions: dict[str, AutonomousSession] = {}
        self._lock = threading.Lock()
        self._evaluators: dict[str, Callable] = {}
        self._improvers: dict[str, Callable] = {}
        AUTONOMOUS_DIR.mkdir(parents=True, exist_ok=True)

    def register_evaluator(self, name: str, fn: Callable) -> None:
        self._evaluators[name] = fn

    def register_improver(self, name: str, fn: Callable) -> None:
        self._improvers[name] = fn

    def start_session(self, job_id: str, config: AutonomousConfig | None = None) -> AutonomousSession:
        config = config or AutonomousConfig()
        session = AutonomousSession(job_id=job_id, config=config)
        with self._lock:
            self.sessions[session.id] = session

        thread = threading.Thread(target=self._run_autonomous_loop, args=(session,), daemon=True)
        thread.start()
        logger.info(
            "Autonomous session %s started for job %s (max %d iterations, threshold %.2f)",
            session.id[:8],
            job_id,
            config.max_iterations,
            config.quality_threshold,
        )
        return session

    def _run_autonomous_loop(self, session: AutonomousSession) -> None:
        session.status = "running"
        tokens_before = get_token_count()
        no_improvement_count = 0
        prev_score = 0.0

        try:
            session.initial_score = self._evaluate_project(session.job_id, session.config.model)
            prev_score = session.initial_score

            for iteration in range(1, session.config.max_iterations + 1):
                session.current_iteration = iteration
                t0 = time.monotonic()
                metrics = IterationMetrics(iteration=iteration)

                session.stage = IterationStage.GENERATE
                self._generate_iteration(session, iteration)
                metrics.stage = "generate"

                session.stage = IterationStage.EVALUATE
                score = self._evaluate_project(session.job_id, session.config.model)
                metrics.score = score
                metrics.stage = "evaluate"

                session.stage = IterationStage.IMPROVE
                if score < session.config.quality_threshold:
                    improved = self._improve_project(session.job_id, session.config.model, score)
                    metrics.stage = "improve"
                    if improved:
                        score = self._evaluate_project(session.job_id, session.config.model)
                        metrics.score = score
                else:
                    metrics.stage = "complete"

                tokens_used = get_token_count() - tokens_before
                metrics.tokens_used = tokens_used
                metrics.duration_ms = (time.monotonic() - t0) * 1000
                metrics.cost_estimate = tokens_used * session.config.cost_per_token

                tests = self._collect_test_results(session.job_id)
                metrics.test_passed = tests.get("passed", 0)
                metrics.test_total = tests.get("total", 0)
                metrics.coverage_pct = tests.get("coverage", 0.0) if tests.get("total", 0) > 0 else 0.0
                metrics.code_quality = self._assess_code_quality(session.job_id)
                metrics.improvement_delta = score - prev_score

                session.total_tokens += tokens_used
                session.total_duration_ms += metrics.duration_ms
                session.total_cost += metrics.cost_estimate
                session.iterations.append(metrics)

                logger.info(
                    "Iteration %d: score=%.3f (delta=%.3f), tokens=%d, tests=%d/%d",
                    iteration,
                    score,
                    metrics.improvement_delta,
                    tokens_used,
                    metrics.test_passed,
                    metrics.test_total,
                )

                if score >= session.config.quality_threshold:
                    logger.info(
                        "Quality threshold reached at iteration %d (%.3f >= %.3f)",
                        iteration,
                        score,
                        session.config.quality_threshold,
                    )
                    break

                if metrics.improvement_delta < session.config.improvement_threshold:
                    no_improvement_count += 1
                    if no_improvement_count >= session.config.max_consecutive_no_improvement:
                        logger.info("No improvement for %d consecutive iterations, stopping", no_improvement_count)
                        break
                else:
                    no_improvement_count = 0

                prev_score = score

            session.final_score = self._evaluate_project(session.job_id, session.config.model)
            session.improvement_pct = (
                (session.final_score - session.initial_score) / (session.initial_score or 1)
            ) * 100
            session.status = "completed"
            session.stage = IterationStage.COMPLETE

        except Exception as exc:
            session.status = "failed"
            session.stage = IterationStage.FAILED
            logger.error("Autonomous session %s failed: %s", session.id[:8], exc)

        session.completed_at = time.time()

    def _generate_iteration(self, session: AutonomousSession, iteration: int) -> None:
        from services.llm_service import call_model

        job_id = session.job_id
        job_dir = Path(os.getenv("BASE_DIR", "./generated_projects")) / job_id
        if not job_dir.exists():
            return

        files = {}
        for fpath in sorted(job_dir.rglob("*")):
            if not fpath.is_file() or "__pycache__" in str(fpath):
                continue
            if fpath.suffix.lower() not in TEXT_EXTENSIONS:
                continue
            try:
                rel = str(fpath.relative_to(job_dir))
                files[rel] = fpath.read_text(encoding="utf-8")
            except Exception:
                pass

        files_block = "\n\n".join(f"--- {k} ---\n{v[:2000]}" for k, v in sorted(files.items())[:15])
        prompt = (
            f"Iteration {iteration} of project improvement cycle.\n\n"
            f"Project files:\n{files_block}\n\n"
            "Improve the code quality, fix any issues, add error handling, "
            "and ensure all edge cases are covered. "
            "Return changes in this format:\n--- FILE: path\n--- ACTION: MODIFY\n--- CONTENT:\n...\n--- END"
        )
        try:
            call_model(prompt, model=session.config.model, job_id=job_id, agent=f"Autonomous_Iter_{iteration}")
        except Exception as exc:
            logger.warning("Generation iteration %d failed: %s", iteration, exc)

    def _evaluate_project(self, job_id: str, model: str) -> float:
        job_dir = Path(os.getenv("BASE_DIR", "./generated_projects")) / job_id
        if not job_dir.exists():
            return 0.0

        score = 0.5

        test_dir = job_dir / "tests"
        if test_dir.exists():
            test_files = list(test_dir.rglob("test_*.py"))
            if test_files:
                score += 0.1

        py_files = list(job_dir.rglob("*.py"))
        if py_files:
            valid_count = 0
            for pf in py_files:
                if "__pycache__" not in str(pf):
                    try:
                        compile(pf.read_text(encoding="utf-8"), str(pf), "exec")
                        valid_count += 1
                    except SyntaxError:
                        pass
            if py_files:
                score += 0.1 * (valid_count / len(py_files))

        readme = job_dir / "README.md"
        if readme.exists():
            score += 0.05

        from services.test_service import run_pytest

        pr = run_pytest(job_id)
        if pr.get("passed", False):
            score += 0.2
        collected = pr.get("collected", 0)
        if collected > 0:
            passed = collected - len(pr.get("failures", []))
            score += 0.1 * (passed / max(collected, 1))

        return min(round(score, 3), 1.0)

    def _improve_project(self, job_id: str, model: str, current_score: float) -> bool:
        job_dir = Path(os.getenv("BASE_DIR", "./generated_projects")) / job_id
        if not job_dir.exists():
            return False

        files = {}
        for fpath in sorted(job_dir.rglob("*")):
            if fpath.is_file() and "__pycache__" not in str(fpath) and fpath.suffix == ".py":
                try:
                    rel = str(fpath.relative_to(job_dir))
                    files[rel] = fpath.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass

        if not files:
            return False

        files_block = "\n\n".join(f"--- {k} ---\n{v}" for k, v in sorted(files.items())[:10])
        prompt = (
            f"The project currently scores {current_score:.3f}/1.0 on quality.\n\n"
            f"Files:\n{files_block}\n\n"
            "Improve the code: fix bugs, add docstrings, improve error handling, "
            "add input validation, fix any type issues. "
            "Output changes in this format:\n--- FILE: path\n--- ACTION: MODIFY\n--- CONTENT:\n...\n--- END"
        )
        try:
            result = call_model(prompt, model=model, job_id=job_id, agent="AutonomousImprove")
            self._apply_changes(result, job_dir)
            return True
        except Exception as exc:
            logger.warning("Improve failed: %s", exc)
            return False

    def _apply_changes(self, llm_result: str, job_dir: Path) -> None:
        import re

        blocks = re.split(r"---\s*FILE\s*:\s*", llm_result)
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            lines = block.split("\n")
            fpath = lines[0].strip().rstrip("-").strip()
            if not fpath:
                continue
            block_text = "\n".join(lines[1:])
            action_match = re.search(r"---\s*ACTION\s*:\s*(\w+)", block_text)
            action = action_match.group(1).upper() if action_match else "MODIFY"
            content_match = re.search(r"---\s*CONTENT\s*:\s*\n?(.*?)(?:\n---\s*END|$)", block_text, re.DOTALL)
            content = content_match.group(1).strip() if content_match else ""
            full_path = (job_dir / fpath).resolve()
            try:
                full_path.relative_to(job_dir.resolve())
            except ValueError:
                logger.warning("Path traversal blocked: %s", fpath)
                continue
            if action == "ADD" or action == "MODIFY":
                if content:
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_text(content, encoding="utf-8")

    def _collect_test_results(self, job_id: str) -> dict[str, Any]:
        from services.test_service import run_pytest

        pr = run_pytest(job_id)
        return {
            "passed": pr.get("collected", 0) - len(pr.get("failures", [])),
            "total": pr.get("collected", 0),
            "coverage": 0.0,
        }

    def _assess_code_quality(self, job_id: str) -> float:
        job_dir = Path(os.getenv("BASE_DIR", "./generated_projects")) / job_id
        if not job_dir.exists():
            return 0.0
        score = 0.5
        py_files = list(job_dir.rglob("*.py"))
        docstring_count = 0
        type_hint_count = 0
        total_functions = 0
        for pf in py_files:
            if "__pycache__" in str(pf):
                continue
            try:
                content = pf.read_text(encoding="utf-8")
                docstring_count += content.count('"""') // 2
                type_hint_count += content.count(": ") + content.count(" -> ")
                import ast

                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        total_functions += 1
            except (SyntaxError, Exception):
                pass
        if total_functions > 0:
            score += 0.2 * min(docstring_count / total_functions, 1)
            score += 0.1 * min(type_hint_count / (total_functions * 3), 1)
        return min(round(score, 3), 1.0)

    def get_session(self, session_id: str) -> AutonomousSession | None:
        return self.sessions.get(session_id)

    def list_sessions(self, limit: int = 20) -> list[dict]:
        sessions = sorted(self.sessions.values(), key=lambda s: s.started_at, reverse=True)
        return [s.to_dict() for s in sessions[:limit]]

    def get_iteration_history(self, session_id: str) -> dict[str, Any]:
        session = self.sessions.get(session_id)
        if not session:
            return {"error": "Session not found"}
        return {
            "session_id": session.id,
            "job_id": session.job_id,
            "iterations": [asdict(m) for m in session.iterations],
            "total_tokens": session.total_tokens,
            "total_cost": round(session.total_cost, 6),
            "improvement": round(session.improvement_pct, 2),
        }


_autonomous_engine = AutonomousEngine()


def get_autonomous_engine() -> AutonomousEngine:
    return _autonomous_engine
