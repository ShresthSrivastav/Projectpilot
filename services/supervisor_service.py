"""
Supervisor Service — multi-agent orchestration layer.

Wraps the existing Orchestrator with agent registration, inter-agent
messaging, parallel team execution, and routing. Fully backward-compatible.
"""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class AgentPriority(Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class AgentRecord:
    name: str
    entry_point: Callable
    priority: AgentPriority = AgentPriority.NORMAL
    team: str = "default"
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentMessage:
    sender: str
    recipient: str
    topic: str
    payload: dict[str, Any]
    timestamp: float = field(default_factory=time.time)


class Supervisor:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._agents: dict[str, AgentRecord] = {}
        self._teams: dict[str, list[str]] = {}
        self._messages: list[AgentMessage] = []
        self._registrations_lock = threading.Lock()
        self._message_lock = threading.Lock()

    def register_agent(
        self,
        name: str,
        entry_point: Callable,
        priority: AgentPriority = AgentPriority.NORMAL,
        team: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._registrations_lock:
            self._agents[name] = AgentRecord(
                name=name,
                entry_point=entry_point,
                priority=priority,
                team=team,
                enabled=True,
                metadata=metadata or {},
            )
            if team not in self._teams:
                self._teams[team] = []
            if name not in self._teams[team]:
                self._teams[team].append(name)
        logger.info("Supervisor: registered agent '%s' (team=%s, priority=%s)", name, team, priority)

    def unregister_agent(self, name: str) -> bool:
        with self._registrations_lock:
            rec = self._agents.pop(name, None)
            if rec and rec.team in self._teams:
                try:
                    self._teams[rec.team].remove(name)
                except ValueError:
                    pass
            return rec is not None

    def get_agent(self, name: str) -> AgentRecord | None:
        return self._agents.get(name)

    def list_agents(self, team: str | None = None) -> list[AgentRecord]:
        with self._registrations_lock:
            if team:
                return [self._agents[n] for n in self._teams.get(team, []) if n in self._agents]
            return list(self._agents.values())

    def disable_agent(self, name: str) -> bool:
        rec = self._agents.get(name)
        if rec:
            rec.enabled = False
            return True
        return False

    def enable_agent(self, name: str) -> bool:
        rec = self._agents.get(name)
        if rec:
            rec.enabled = True
            return True
        return False

    def send_message(self, sender: str, recipient: str, topic: str, payload: dict[str, Any]) -> None:
        with self._message_lock:
            self._messages.append(AgentMessage(sender=sender, recipient=recipient, topic=topic, payload=payload))

    def get_messages(self, for_agent: str, topic: str | None = None) -> list[AgentMessage]:
        with self._message_lock:
            results = [m for m in self._messages if m.recipient == for_agent]
            if topic:
                results = [m for m in results if m.topic == topic]
            return results

    def clear_messages(self, for_agent: str | None = None) -> None:
        with self._message_lock:
            if for_agent:
                self._messages = [m for m in self._messages if m.recipient != for_agent]
            else:
                self._messages.clear()

    def broadcast(self, sender: str, topic: str, payload: dict[str, Any]) -> None:
        for name in self._agents:
            if name != sender and self._agents[name].enabled:
                self.send_message(sender, name, topic, payload)

    def run_team(
        self,
        team: str,
        context: dict[str, Any],
        timeout_per_agent: int = 300,
    ) -> dict[str, Any]:
        results: dict[str, Any] = {}
        agents = sorted(
            [a for a in self._teams.get(team, []) if a in self._agents and self._agents[a].enabled],
            key=lambda n: self._agents[n].priority.value,
            reverse=True,
        )
        if not agents:
            logger.warning("Supervisor: no enabled agents in team '%s'", team)
            return results

        logger.info("Supervisor: running team '%s' with %d agent(s)", team, len(agents))
        for name in agents:
            rec = self._agents[name]
            try:
                t0 = time.monotonic()
                result = rec.entry_point(context)
                elapsed = time.monotonic() - t0
                results[name] = {"status": "ok", "result": result, "elapsed_s": round(elapsed, 2)}
                logger.info("Supervisor: agent '%s' completed in %.2fs", name, elapsed)
            except Exception as exc:
                results[name] = {"status": "error", "error": str(exc), "elapsed_s": 0}
                logger.error("Supervisor: agent '%s' failed: %s", name, exc)
        return results

    def run_teams_parallel(
        self,
        teams: list[str],
        context: dict[str, Any],
        timeout_per_agent: int = 300,
    ) -> dict[str, Any]:
        all_results: dict[str, Any] = {}
        threads = []
        results_lock = threading.Lock()

        def _run_team(t: str):
            res = self.run_team(t, context, timeout_per_agent)
            with results_lock:
                all_results[t] = res

        for team_name in teams:
            t = threading.Thread(target=_run_team, args=(team_name,), daemon=True)
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=max(timeout_per_agent * 2, 600))

        return all_results

    def delegate(self, agent_name: str, task: dict[str, Any]) -> Any:
        rec = self._agents.get(agent_name)
        if not rec:
            raise ValueError(f"Agent '{agent_name}' not registered")
        if not rec.enabled:
            raise RuntimeError(f"Agent '{agent_name}' is disabled")
        return rec.entry_point(task)

    def reset(self) -> None:
        with self._registrations_lock:
            self._agents.clear()
            self._teams.clear()
        with self._message_lock:
            self._messages.clear()
