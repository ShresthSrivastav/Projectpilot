"""Analytics Service — tracks agent activity, execution time, token usage."""
import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from database.memory_store import get_project_analytics, get_analytics_summary

logger = logging.getLogger(__name__)


class AgentTimer:
    """Context manager to time agent execution and record analytics."""

    def __init__(self, agent_name: str, job_id: str, metadata: Optional[Dict] = None):
        self.agent_name = agent_name
        self.job_id = job_id
        self.metadata = metadata or {}
        self.start_time = 0.0
        self.elapsed_ms = 0

    def __enter__(self):
        self.start_time = time.monotonic()
        return self

    def __exit__(self, _exc_type, _exc_val, _exc_tb):
        self.elapsed_ms = int((time.monotonic() - self.start_time) * 1000)
        duration = self.elapsed_ms
        record = {
            "agent": self.agent_name,
            "job_id": self.job_id,
            "duration_ms": duration,
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(exc_val) if exc_val else None,
            **self.metadata,
        }
        logger.info("ANALYTICS %s", json.dumps(record))
        return False


def get_project_stats(job_id: str) -> Dict[str, Any]:
    all_projects = get_project_analytics(limit=200)
    for p in all_projects:
        if p.get("job_id") == job_id:
            return p
    return {}


def get_overview() -> Dict[str, Any]:
    return get_analytics_summary()


def get_agent_leaderboard(limit: int = 10) -> List[Dict[str, Any]]:
    all_projects = get_project_analytics(limit=200)
    if not all_projects:
        return []
    total_duration = sum(p.get("total_duration_ms", 0) for p in all_projects)
    total_files = sum(p.get("file_count", 0) for p in all_projects)
    total_tokens = sum(p.get("token_usage", 0) for p in all_projects)
    completed = sum(1 for p in all_projects if p.get("status") == "complete")
    return [
        {"metric": "Projects Completed", "value": completed, "detail": f"out of {len(all_projects)} total"},
        {"metric": "Avg Duration", "value": f"{total_duration // max(len(all_projects), 1) // 1000}s", "detail": "per project"},
        {"metric": "Avg Files/Project", "value": round(total_files / max(len(all_projects), 1), 1), "detail": "files"},
        {"metric": "Total Tokens", "value": total_tokens, "detail": "across all projects"},
    ]
