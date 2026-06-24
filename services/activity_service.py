"""Workspace activity feed service."""

import logging
import uuid
from datetime import UTC, datetime

from database.memory_store import _get_conn

logger = logging.getLogger(__name__)

ACTIVITY_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS workspace_activity (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    action TEXT NOT NULL,
    description TEXT DEFAULT '',
    resource_type TEXT DEFAULT '',
    resource_id TEXT DEFAULT '',
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_initialized = False


def init_activity_db():
    global _initialized
    conn = _get_conn()
    conn.execute(ACTIVITY_TABLE_DDL)
    conn.commit()
    _initialized = True
    logger.debug("Initialized workspace_activity table")


def _ensure_table():
    global _initialized
    if not _initialized:
        init_activity_db()


def log_activity(
    workspace_id: str, user_id: str, action: str, description: str = "", resource_type: str = "", resource_id: str = ""
) -> None:
    _ensure_table()
    conn = _get_conn()
    conn.execute(
        "INSERT INTO workspace_activity (id, workspace_id, user_id, action, description, resource_type, resource_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), workspace_id, user_id, action, description, resource_type, resource_id),
    )
    conn.commit()


def get_activities(workspace_id: str, limit: int = 50) -> list[dict]:
    _ensure_table()
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, workspace_id, user_id, action, description, resource_type, resource_id, timestamp "
        "FROM workspace_activity WHERE workspace_id = ? ORDER BY timestamp DESC LIMIT ?",
        (workspace_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]
