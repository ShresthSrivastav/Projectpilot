"""Workspace audit logging service."""

import logging
import uuid
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


AUDIT_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT DEFAULT '',
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_audit_logs_ws ON audit_logs(workspace_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_ts ON audit_logs(timestamp);
"""


def init_audit_db():
    from database.memory_store import _get_conn

    try:
        conn = _get_conn()
        conn.executescript(AUDIT_TABLE_DDL)
        conn.execute("DELETE FROM audit_logs")
        conn.commit()
    except Exception as exc:
        logger.warning("audit table init failed: %s", exc)


def log_audit_event(
    workspace_id: str,
    user_id: str,
    action: str,
    resource_type: str,
    resource_id: str = "",
) -> None:
    from database.memory_store import _get_conn

    try:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO audit_logs (id, workspace_id, user_id, action, resource_type, resource_id, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                workspace_id,
                user_id,
                action,
                resource_type,
                resource_id,
                datetime.now(UTC).isoformat(),
            ),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("audit log failed: %s", exc)


def get_audit_logs(workspace_id: str, limit: int = 50) -> list[dict]:
    from database.memory_store import _get_conn

    try:
        conn = _get_conn()
        cur = conn.execute(
            "SELECT * FROM audit_logs WHERE workspace_id=? ORDER BY timestamp DESC LIMIT ?",
            (workspace_id, limit),
        )
        return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []
