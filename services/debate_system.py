"""Multi-Agent Debate System — independent solvers, consensus, arbitration, quality scoring."""
import json
import logging
import os
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from services.llm_service import call_model

logger = logging.getLogger(__name__)

DEBATE_DIR = os.getenv("DEBATE_OUTPUT_DIR", "./debate_output")


class DebateRound(Enum):
    INDEPENDENT = "independent"
    DISCUSSION = "discussion"
    CONSENSUS = "consensus"
    ARBITRATION = "arbitration"
    COMPLETE = "complete"


class ConsensusMethod(Enum):
    MAJORITY = "majority"
    WEIGHTED = "weighted"
    RANKED = "ranked"
    ARBITER = "arbiter"


@dataclass
class SolverResult:
    solver_id: str
    solver_name: str
    solution: str
    reasoning: str = ""
    confidence: float = 0.0
    score: float = 0.0
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DebateConfig:
    solvers: list[str] = field(default_factory=lambda: ["cloud", "cloud", "cloud"])
    independent_rounds: int = 1
    discussion_rounds: int = 2
    consensus_method: ConsensusMethod = ConsensusMethod.WEIGHTED
    arbiter_model: str = "cloud"
    quality_threshold: float = 0.7
    max_solution_length: int = 8000
    include_reasoning: bool = True


@dataclass
class DebateSession:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    topic: str = ""
    config: DebateConfig = field(default_factory=DebateConfig)
    round: DebateRound = DebateRound.INDEPENDENT
    results: list[SolverResult] = field(default_factory=list)
    final_solution: str | None = None
    consensus_score: float = 0.0
    arbitration_reasoning: str = ""
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    status: str = "pending"
    metadata: dict[str, Any] = field(default_factory=dict)
    discussion_history: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "topic": self.topic[:100],
            "config": asdict(self.config),
            "round": self.round.value,
            "results": [asdict(r) for r in self.results],
            "final_solution": self.final_solution[:500] if self.final_solution else None,
            "consensus_score": self.consensus_score,
            "arbitration_reasoning": self.arbitration_reasoning[:500] if self.arbitration_reasoning else "",
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "solver_count": len(self.results),
        }


class DebateSystem:
    def __init__(self):
        self.sessions: dict[str, DebateSession] = {}
        self._lock = threading.Lock()
        self._solvers: dict[str, Callable] = {}
        self._register_default_solvers()

    def _register_default_solvers(self) -> None:
        self.register_solver("local", self._local_solver)
        self.register_solver("cloud", self._cloud_solver)

    def register_solver(self, name: str, solver_fn: Callable) -> None:
        self._solvers[name] = solver_fn

    def _local_solver(self, topic: str, context: str = "", job_id: str = "") -> tuple[str, str, float]:
        result = call_model(
            f"Solve this programming task:\n\n{topic}\n\nContext:\n{context}\n\nProvide a complete solution.",
            model="local", job_id=job_id or None, agent="DebateSolver_local",
        )
        return result, "Using Ollama with local model for independent solution.", 0.7

    def _cloud_solver(self, topic: str, context: str = "", job_id: str = "") -> tuple[str, str, float]:
        result = call_model(
            f"Solve this programming task:\n\n{topic}\n\nContext:\n{context}\n\nProvide a comprehensive production-grade solution.",
            model="cloud", job_id=job_id or None, agent="DebateSolver_cloud",
        )
        return result, "Using Google Gemini for independent solution.", 0.8

    def start_debate(self, topic: str, config: DebateConfig | None = None,
                     context: str = "", job_id: str = "") -> DebateSession:
        config = config or DebateConfig()
        session = DebateSession(topic=topic, config=config)
        session.metadata["context"] = context
        session.metadata["job_id"] = job_id
        with self._lock:
            self.sessions[session.id] = session
        logger.info("Debate started: %s (%s solvers)", session.id[:8], len(config.solvers))

        thread = threading.Thread(target=self._run_debate, args=(session, context, job_id), daemon=True)
        thread.start()
        return session

    def _run_debate(self, session: DebateSession, context: str, job_id: str) -> None:
        try:
            session.round = DebateRound.INDEPENDENT
            session.status = "running"
            for solver_name in session.config.solvers:
                if solver_name not in self._solvers:
                    logger.warning("Solver %s not registered, skipping", solver_name)
                    continue
                t0 = time.monotonic()
                try:
                    solution, reasoning, confidence = self._solvers[solver_name](session.topic, context, job_id)
                    duration = (time.monotonic() - t0) * 1000
                    result = SolverResult(
                        solver_id=solver_name,
                        solver_name=solver_name,
                        solution=solution,
                        reasoning=reasoning,
                        confidence=confidence,
                        duration_ms=duration,
                    )
                    session.results.append(result)
                    logger.info("Solver %s completed in %.0fms (confidence: %.2f)", solver_name, duration, confidence)
                except Exception as exc:
                    logger.error("Solver %s failed: %s", solver_name, exc)
                    session.results.append(SolverResult(
                        solver_id=solver_name, solver_name=solver_name,
                        solution="", reasoning=f"Solver failed: {exc}", confidence=0.0,
                    ))

            valid_results = [r for r in session.results if r.solution and len(r.solution) > 50]
            if len(valid_results) < 2:
                session.final_solution = valid_results[0].solution if valid_results else "No valid solutions generated."
                session.consensus_score = valid_results[0].confidence if valid_results else 0.0
                session.round = DebateRound.COMPLETE
                session.status = "completed"
                session.completed_at = time.time()
                logger.info("Debate %s completed (fallback to best single solver)", session.id[:8])
                return

            session.round = DebateRound.DISCUSSION
            discussion_prompt = self._build_discussion_prompt(session, context)
            try:
                discussion = call_model(
                    discussion_prompt,
                    model=session.config.arbiter_model,
                    job_id=job_id or None,
                    agent="DebateArbiter",
                )
                session.discussion_history.append({"round": "discussion", "content": discussion})
            except Exception as exc:
                session.discussion_history.append({"round": "discussion", "content": f"Discussion failed: {exc}"})

            session.round = DebateRound.CONSENSUS
            session.final_solution, session.consensus_score = self._reach_consensus(session)
            session.round = DebateRound.COMPLETE
            session.status = "completed"
            session.completed_at = time.time()
            logger.info("Debate %s completed — consensus: %.2f", session.id[:8], session.consensus_score)
        except Exception as exc:
            session.status = "failed"
            session.completed_at = time.time()
            logger.error("Debate %s failed: %s", session.id[:8], exc)

    def _build_discussion_prompt(self, session: DebateSession, context: str) -> str:
        solutions_text = "\n\n".join(
            f"=== Solver {r.solver_name} ===\nConfidence: {r.confidence:.2f}\nReasoning: {r.reasoning}\nSolution:\n{r.solution[:2000]}"
            for r in session.results if r.solution
        )
        return (
            f"You are an arbiter for multiple AI solvers debating this topic:\n\n{session.topic}\n\n"
            f"Context: {context}\n\n"
            f"Here are their independent solutions:\n\n{solutions_text}\n\n"
            "Analyze each solution for:\n"
            "1. Correctness — does it solve the problem?\n"
            "2. Completeness — are all requirements addressed?\n"
            "3. Code quality — is it maintainable and well-structured?\n"
            "4. Security — are there any vulnerabilities?\n"
            "5. Performance — is it efficient?\n\n"
            "Identify the strengths and weaknesses of each approach. "
            "Then recommend the best solution or a hybrid approach."
        )

    def _reach_consensus(self, session: DebateSession) -> tuple[str, float]:
        valid = [r for r in session.results if r.solution and len(r.solution) > 50]
        if not valid:
            return "No valid solutions found.", 0.0

        if session.config.consensus_method == ConsensusMethod.MAJORITY:
            return self._majority_consensus(valid)
        elif session.config.consensus_method == ConsensusMethod.WEIGHTED:
            return self._weighted_consensus(valid)
        elif session.config.consensus_method == ConsensusMethod.ARBITER:
            return self._arbiter_consensus(session, valid)
        else:
            return self._weighted_consensus(valid)

    def _majority_consensus(self, results: list[SolverResult]) -> tuple[str, float]:
        best = max(results, key=lambda r: r.confidence)
        return best.solution, best.confidence

    def _weighted_consensus(self, results: list[SolverResult]) -> tuple[str, float]:
        valid = [r for r in results if r.confidence > 0.3]
        if not valid:
            valid = results
        total_weight = sum(r.confidence for r in valid)
        if total_weight == 0:
            return valid[0].solution, 0.0
        best = max(valid, key=lambda r: r.confidence)
        avg_confidence = total_weight / len(valid)
        return best.solution, round(avg_confidence, 3)

    def _arbiter_consensus(self, session: DebateSession, results: list[SolverResult]) -> tuple[str, float]:
        solutions_json = json.dumps([{"solver": r.solver_name, "solution": r.solution[:3000], "confidence": r.confidence} for r in results])
        prompt = (
            f"Debate topic: {session.topic}\n\n"
            f"Solutions from {len(results)} solvers:\n{solutions_json}\n\n"
            "Select the best solution. Output:\n"
            "--- SELECTED: solver_name\n"
            "--- SCORE: 0.0-1.0\n"
            "--- REASONING: brief explanation\n"
            "If no solution is adequate, output:\n--- NO_CONSENSUS: reason"
        )
        try:
            response = call_model(prompt, model=session.config.arbiter_model, agent="DebateConsensus")
            selected = ""
            score = 0.0
            for line in response.splitlines():
                if line.startswith("--- SELECTED:"):
                    selected = line.split(":", 1)[1].strip()
                elif line.startswith("--- SCORE:"):
                    try:
                        score = float(line.split(":", 1)[1].strip())
                    except ValueError:
                        score = 0.5
            if selected and "NO_CONSENSUS" not in selected:
                for r in results:
                    if r.solver_name == selected:
                        return r.solution, min(score, 1.0)
        except Exception as exc:
            logger.warning("Arbiter consensus failed: %s", exc)
        best = max(results, key=lambda r: r.confidence)
        return best.solution, best.confidence

    def _find_common_patterns(self, results: list[SolverResult]) -> dict[str, int]:
        patterns = {}
        for r in results:
            words = set(r.solution.lower().split())
            for w in list(words)[:50]:
                patterns[w] = patterns.get(w, 0) + 1
        return {k: v for k, v in sorted(patterns.items(), key=lambda x: -x[1])[:20]}

    def get_session(self, session_id: str) -> DebateSession | None:
        return self.sessions.get(session_id)

    def list_sessions(self, limit: int = 20) -> list[dict]:
        sessions = sorted(self.sessions.values(), key=lambda s: s.created_at, reverse=True)
        return [s.to_dict() for s in sessions[:limit]]

    def evaluate_quality(self, session_id: str) -> dict[str, Any]:
        session = self.sessions.get(session_id)
        if not session:
            return {"error": "Session not found"}
        scores = []
        for r in session.results:
            if r.solution:
                scores.append({
                    "solver": r.solver_name,
                    "confidence": r.confidence,
                    "solution_length": len(r.solution),
                    "has_error": False,
                })
            else:
                scores.append({"solver": r.solver_name, "confidence": 0.0, "solution_length": 0, "has_error": True})
        return {
            "session_id": session.id,
            "consensus_score": session.consensus_score,
            "solver_count": len(session.results),
            "valid_solutions": sum(1 for r in session.results if r.solution and len(r.solution) > 50),
            "scores": scores,
            "arbitration_reasoning": session.arbitration_reasoning[:500] if session.arbitration_reasoning else "",
        }


_debate_system = DebateSystem()


def get_debate_system() -> DebateSystem:
    return _debate_system
