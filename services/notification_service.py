"""Notification service for workspace events."""

import json
import logging
import uuid
from datetime import UTC, datetime

from database.memory_store import _get_conn

logger = logging.getLogger(__name__)

NOTIFICATIONS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT DEFAULT '',
    data TEXT DEFAULT '{}',
    is_read INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_initialized = False


def init_notifications_db():
    global _initialized
    conn = _get_conn()
    conn.execute(NOTIFICATIONS_TABLE_DDL)
    conn.commit()
    _initialized = True
    logger.debug("Initialized notifications table")


def _ensure_table():
    global _initialized
    if not _initialized:
        init_notifications_db()


def create_notification(user_id: str, workspace_id: str, notification_type: str,
                        title: str, message: str = "", data: dict = None) -> None:
    _ensure_table()
    conn = _get_conn()
    conn.execute(
        "INSERT INTO notifications (id, user_id, workspace_id, type, title, message, data) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, workspace_id, notification_type, title, message,
         json.dumps(data or {})),
    )
    conn.commit()


def get_notifications(user_id: str, workspace_id: str = "", limit: int = 20,
                      unread_only: bool = False) -> list[dict]:
    _ensure_table()
    conn = _get_conn()
    where = ["user_id = ?"]
    params = [user_id]
    if workspace_id:
        where.append("workspace_id = ?")
        params.append(workspace_id)
    if unread_only:
        where.append("is_read = 0")
    rows = conn.execute(
        f"SELECT id, user_id, workspace_id, type, title, message, data, is_read, created_at "
        f"FROM notifications WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT ?",
        (*params, limit),
    ).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        try:
            d["data"] = json.loads(d["data"])
        except Exception:
            d["data"] = {}
        results.append(d)
    return results


def mark_notification_read(notification_id: str, user_id: str) -> bool:
    _ensure_table()
    conn = _get_conn()
    cursor = conn.execute(
        "UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?",
        (notification_id, user_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def mark_all_notifications_read(user_id: str, workspace_id: str = "") -> None:
    _ensure_table()
    conn = _get_conn()
    if workspace_id:
        conn.execute(
            "UPDATE notifications SET is_read = 1 WHERE user_id = ? AND workspace_id = ?",
            (user_id, workspace_id),
        )
    else:
        conn.execute(
            "UPDATE notifications SET is_read = 1 WHERE user_id = ?",
            (user_id,),
        )
    conn.commit()
