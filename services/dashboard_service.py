"""Dashboard Service — real-time agent telemetry and monitoring.

Provides:
  - Agent status tracking (idle/running/waiting/failed/completed)
  - WebSocket event streaming for live updates
  - Agent activity timeline
  - Execution graph data
  - Cost analytics
  - Memory and CPU usage tracking
"""

import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AgentTelemetry:
    agent_name: str
    status: str = "idle"
    current_task: str = ""
    current_file: str = ""
    current_repo: str = ""
    queue_size: int = 0
    tokens_used: int = 0
    estimated_cost: float = 0.0
    runtime_ms: int = 0
    success_count: int = 0
    failure_count: int = 0
    started_at: str | None = None
    last_heartbeat: str = ""


@dataclass
class DashboardEvent:
    event_type: str
    data: dict[str, Any]
    timestamp: float = field(default_factory=time.time)


_agents: dict[str, AgentTelemetry] = {}
_agent_lock = threading.RLock()
_timeline: list[DashboardEvent] = []
_timeline_lock = threading.Lock()
_MAX_TIMELINE = 1000

_ws_clients: set[Callable[[DashboardEvent], None]] = set()
_ws_lock = threading.Lock()

_START_TIME = time.time()


def register_agent(name: str) -> AgentTelemetry:
    with _agent_lock:
        if name not in _agents:
            _agents[name] = AgentTelemetry(agent_name=name)
        return _agents[name]


def update_agent_status(
    name: str,
    status: str,
    task: str = "",
    file: str = "",
    repo: str = "",
    tokens: int = 0,
    cost: float = 0.0,
    runtime: int = 0,
    success: bool | None = None,
) -> AgentTelemetry:
    with _agent_lock:
        agent = _agents.get(name)
        if not agent:
            agent = register_agent(name)
        agent.status = status
        if task:
            agent.current_task = task
        if file:
            agent.current_file = file
        if repo:
            agent.current_repo = repo
        agent.tokens_used += tokens
        agent.estimated_cost += cost
        agent.runtime_ms += runtime
        if status == "running" and not agent.started_at:
            agent.started_at = datetime.utcnow().isoformat()
        if success is True:
            agent.success_count += 1
        elif success is False:
            agent.failure_count += 1
        agent.last_heartbeat = datetime.utcnow().isoformat()
        agent.queue_size = len(_get_running_agents())
        _publish_event(
            "agent_status",
            {
                "agent": name,
                "status": status,
                "task": task,
                "tokens": agent.tokens_used,
                "cost": agent.estimated_cost,
            },
        )
        return agent


def _get_running_agents() -> list[str]:
    return [n for n, a in _agents.items() if a.status == "running"]


def get_agent(name: str) -> dict | None:
    with _agent_lock:
        agent = _agents.get(name)
        if agent:
            return {
                "name": agent.agent_name,
                "status": agent.status,
                "current_task": agent.current_task,
                "current_file": agent.current_file,
                "current_repo": agent.current_repo,
                "queue_size": agent.queue_size,
                "tokens_used": agent.tokens_used,
                "estimated_cost": round(agent.estimated_cost, 4),
                "runtime_ms": agent.runtime_ms,
                "success_count": agent.success_count,
                "failure_count": agent.failure_count,
                "started_at": agent.started_at,
                "last_heartbeat": agent.last_heartbeat,
            }
        return None


def get_all_agents() -> list[dict]:
    with _agent_lock:
        return [
            {
                "name": a.agent_name,
                "status": a.status,
                "current_task": a.current_task,
                "current_file": a.current_file,
                "tokens_used": a.tokens_used,
                "estimated_cost": round(a.estimated_cost, 4),
                "runtime_ms": a.runtime_ms,
                "success_count": a.success_count,
                "failure_count": a.failure_count,
                "last_heartbeat": a.last_heartbeat,
            }
            for a in sorted(_agents.values(), key=lambda x: x.last_heartbeat or "", reverse=True)
        ]


def get_dashboard_status() -> dict[str, Any]:
    with _agent_lock:
        agents = get_all_agents()
        running = sum(1 for a in agents if a["status"] == "running")
        total_tokens = sum(a.get("tokens_used", 0) for a in agents)
        total_cost = sum(a.get("estimated_cost", 0) for a in agents)
        total_success = sum(a.get("success_count", 0) for a in agents)
        total_failure = sum(a.get("failure_count", 0) for a in agents)
        uptime_s = int(time.time() - _START_TIME)
        avg_runtime = sum(a.get("runtime_ms", 0) for a in agents) / max(len(agents), 1)

    try:
        import psutil
        proc = psutil.Process(os.getpid())
        cpu_usage = proc.cpu_percent(interval=0.1)
        mem = proc.memory_info()
        memory_usage = round(mem.rss / 1024 / 1024, 1)
        gpu_usage = 0
    except ImportError:
        cpu_usage = memory_usage = gpu_usage = 0

    return {
        "total_projects": len(agents),
        "active_jobs": running,
        "total_files": sum(a.get("success_count", 0) for a in agents),
        "total_tokens": total_tokens,
        "avg_duration": round(avg_runtime / 1000, 1),
        "cpu_usage": cpu_usage,
        "memory_usage": memory_usage,
        "gpu_usage": gpu_usage,
        "estimated_cost": round(total_cost, 4),
        "success_rate": round(total_success / max(total_success + total_failure, 1) * 100, 1),
        "uptime_seconds": uptime_s,
        "agents": agents,
        "timestamp": datetime.utcnow().isoformat(),
    }


def get_timeline(limit: int = 100, job_id: str | None = None) -> list[dict]:
    with _timeline_lock:
        events = list(_timeline[-limit:])
        if job_id:
            events = [e for e in events if isinstance(e.data, dict) and e.data.get("job_id") == job_id]
        return [{"type": e.event_type, "data": e.data, "timestamp": e.timestamp} for e in events]


def _publish_event(event_type: str, data: dict[str, Any]):
    event = DashboardEvent(event_type=event_type, data=data)
    with _timeline_lock:
        _timeline.append(event)
        if len(_timeline) > _MAX_TIMELINE:
            _timeline.pop(0)
    with _ws_lock:
        dead = set()
        for callback in _ws_clients:
            try:
                callback(event)
            except Exception:
                dead.add(callback)
        _ws_clients -= dead


def subscribe(callback: Callable[[DashboardEvent], None]) -> Callable:
    with _ws_lock:
        _ws_clients.add(callback)
    return callback


def unsubscribe(callback: Callable):
    with _ws_lock:
        _ws_clients.discard(callback)


def get_execution_graph(agent_name: str | None = None) -> list[dict]:
    events = get_timeline(200)
    if agent_name:
        events = [e for e in events if e["data"].get("agent") == agent_name]
    nodes = set()
    edges = []
    for event in events:
        agent = event["data"].get("agent", "")
        task = event["data"].get("task", "")
        if agent and task:
            nodes.add(agent)
            nodes.add(task)
            edges.append({"source": agent, "target": task, "type": event["type"]})
    return {
        "nodes": [{"id": n, "type": "agent" if n in _agents else "task"} for n in nodes],
        "edges": edges,
    }


def record_task_completion(agent_name: str, task_name: str, duration_ms: int, tokens: int, success: bool):
    cost = tokens * 0.000002  # approximate cost per token
    with _agent_lock:
        agent = _agents.get(agent_name)
        if agent:
            agent.runtime_ms += duration_ms
            agent.tokens_used += tokens
            agent.estimated_cost += cost
            if success:
                agent.success_count += 1
            else:
                agent.failure_count += 1
    _publish_event(
        "task_completed",
        {
            "agent": agent_name,
            "task": task_name,
            "duration_ms": duration_ms,
            "tokens": tokens,
            "cost": round(cost, 6),
            "success": success,
        },
    )


def track_memory_usage() -> dict[str, float]:
    try:
        import psutil

        process = psutil.Process(os.getpid())
        mem = process.memory_info()
        cpu = process.cpu_percent(interval=0.1)
        return {
            "memory_mb": round(mem.rss / 1024 / 1024, 1),
            "memory_percent": round(process.memory_percent(), 1),
            "cpu_percent": cpu,
        }
    except ImportError:
        return {"memory_mb": 0, "memory_percent": 0, "cpu_percent": 0}
