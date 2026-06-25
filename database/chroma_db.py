"""
ChromaDB storage layer — ProjectPilot.

Workspace-isolated collections: each workspace gets its own set of
collections named workspace_{ws_id}_{type}.

Uses contextvars for automatic workspace detection from request context.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)

CHROMA_PATH = os.getenv(
    "CHROMA_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chroma_data")
)
_client: chromadb.PersistentClient | None = None


def _get_chroma_path() -> str:
    """Return current CHROMA_PATH, re-reading env var if changed."""
    return os.getenv("CHROMA_PATH", CHROMA_PATH)


_DUMMY_EMBED = [[0.0]]

_COLLECTION_TYPES = ("jobs", "generation_logs", "requirements", "blueprints")

# Per-request workspace context
_current_workspace: ContextVar[str] = ContextVar("_current_workspace", default="")


def set_workspace_context(workspace_id: str) -> None:
    """Set the workspace_id for the current request context."""
    _current_workspace.set(workspace_id)


def get_workspace_context() -> str:
    """Get the workspace_id from the current request context."""
    return _current_workspace.get()


def _get_ws() -> str:
    """Get workspace_id from context, falling back to empty string."""
    return _current_workspace.get()


def _get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=_get_chroma_path(),
            settings=Settings(anonymized_telemetry=False),
        )
    return _client


def _col(name: str):
    return _get_client().get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
        embedding_function=None,
    )


def _embed(n: int = 1) -> list[list[float]]:
    return [[0.0]] * n


def _ws_col(workspace_id: str, collection_type: str):
    """Get or create a workspace-scoped collection."""
    name = f"workspace_{workspace_id}_{collection_type}"
    return _col(name)


def get_workspace_collection(workspace_id: str, collection_type: str):
    """Public helper — returns a workspace-scoped ChromaDB collection."""
    return _ws_col(workspace_id, collection_type)


def init_db() -> None:
    """Initialize default (legacy) collections. New usage should call init_workspace()."""
    global _client
    _client = None
    for name in _COLLECTION_TYPES:
        _col(name)
    logger.info("ChromaDB ready (persistent at %s)", _get_chroma_path())


def init_workspace(workspace_id: str) -> None:
    """Ensure all collections exist for a given workspace."""
    for ct in _COLLECTION_TYPES:
        _ws_col(workspace_id, ct)


# ── Internal helpers ──────────────────────────────────────────────────────


def _resolve_ws(workspace_id: str) -> str:
    """Resolve workspace_id: use explicit value, then contextvar."""
    return workspace_id or _get_ws()


def _collection(workspace_id: str, ct: str):
    """Return workspace-scoped collection name, falling back to global."""
    wid = _resolve_ws(workspace_id)
    if wid:
        return f"workspace_{wid}_{ct}"
    return ct


def _get_job_meta(workspace_id: str, job_id: str) -> dict | None:
    wid = _resolve_ws(workspace_id)
    coll = _collection(wid, "jobs")
    try:
        r = _col(coll).get(ids=[job_id], include=["metadatas", "documents"])
        if r["ids"]:
            meta = dict(r["metadatas"][0])
            meta["prompt"] = r["documents"][0]
            return meta
    except Exception:
        pass
    return None


# ── Jobs ──────────────────────────────────────────────────────────────────


def create_job(job_id: str, workspace_id: str = "", user_id: str = "") -> None:
    now = datetime.now(UTC).isoformat()
    wid = _resolve_ws(workspace_id)
    for ct in ("generation_logs", "requirements", "blueprints"):
        coll = _collection(wid, ct)
        try:
            _col(coll).delete(where={"job_id": job_id})
        except Exception:
            pass
    coll = _collection(wid, "jobs")
    _col(coll).upsert(
        ids=[job_id],
        embeddings=_embed(1),
        documents=[""],
        metadatas=[
            {
                "status": "queued",
                "project_name": "",
                "current_agent": "",
                "progress_pct": 0,
                "error_message": "",
                "file_count": 0,
                "zip_path": "",
                "workspace_id": wid,
                "user_id": user_id,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )


def save_prompt(job_id: str, prompt: str, project_name: str, workspace_id: str = "", user_id: str = "") -> None:
    wid = _resolve_ws(workspace_id)
    existing = _get_job_meta(wid, job_id) or {}
    now = datetime.now(UTC).isoformat()
    coll = _collection(wid, "jobs")
    _col(coll).upsert(
        ids=[job_id],
        embeddings=_embed(1),
        documents=[prompt],
        metadatas=[
            {
                "status": existing.get("status", "queued"),
                "project_name": project_name,
                "current_agent": existing.get("current_agent", ""),
                "progress_pct": existing.get("progress_pct", 0),
                "error_message": existing.get("error_message", ""),
                "file_count": existing.get("file_count", 0),
                "zip_path": existing.get("zip_path", ""),
                "workspace_id": wid,
                # Preserve existing user_id; use provided value as fallback
                "user_id": existing.get("user_id") or user_id,
                "created_at": existing.get("created_at", now),
                "updated_at": now,
            }
        ],
    )


def get_job(job_id: str, workspace_id: str = "") -> dict[str, Any] | None:
    wid = _resolve_ws(workspace_id)
    meta = _get_job_meta(wid, job_id)
    if meta:
        meta["job_id"] = job_id
    return meta


def list_jobs(workspace_id: str = "", user_id: str = "", limit: int = 20) -> list[dict[str, Any]]:
    wid = _resolve_ws(workspace_id)
    coll = _collection(wid, "jobs")
    try:
        r = _col(coll).get(include=["metadatas", "documents"])
        jobs = []
        for i, jid in enumerate(r["ids"]):
            meta = dict(r["metadatas"][i])
            meta["job_id"] = jid
            meta["prompt"] = r["documents"][i]
            # User-level isolation: skip records that belong to a different user.
            # Legacy records with no user_id are shown to all workspace members.
            record_uid = meta.get("user_id", "")
            if user_id and record_uid and record_uid != user_id:
                continue
            jobs.append(meta)
        jobs.sort(key=lambda j: j.get("created_at", ""), reverse=True)
        return jobs[:limit]
    except Exception:
        return []


def get_job_owner(job_id: str, workspace_id: str = "") -> str | None:
    """Return the user_id stored in the job record, or None if not found."""
    wid = _resolve_ws(workspace_id)
    meta = _get_job_meta(wid, job_id)
    if meta is None:
        return None
    return meta.get("user_id", "")


def delete_job(job_id: str, workspace_id: str = "") -> bool:
    wid = _resolve_ws(workspace_id)
    coll = _collection(wid, "jobs")
    try:
        _col(coll).delete(ids=[job_id])
        logger.info("Deleted job %s from ChromaDB (ws=%s)", job_id, wid)
        return True
    except Exception as exc:
        logger.warning("Failed to delete job %s: %s", job_id, exc)
        return False


def update_job_status(
    job_id: str,
    status: str,
    workspace_id: str = "",
    current_agent: str = "",
    progress_pct: int = 0,
    error_message: str = "",
    **extra: Any,
) -> None:
    wid = _resolve_ws(workspace_id)
    existing = _get_job_meta(wid, job_id)
    if not existing:
        logger.warning("update_job_status: job %s not found (ws=%s)", job_id, wid)
        return
    meta = {
        "status": status,
        "project_name": existing.get("project_name", ""),
        "current_agent": current_agent,
        "progress_pct": progress_pct,
        "error_message": error_message,
        "file_count": existing.get("file_count", 0),
        "zip_path": existing.get("zip_path", ""),
        "test_total": existing.get("test_total", 0),
        "test_passed": existing.get("test_passed", 0),
        "test_failed": existing.get("test_failed", 0),
        "test_skipped": existing.get("test_skipped", 0),
        "test_summary": existing.get("test_summary", ""),
        "test_details": existing.get("test_details", ""),
        "workspace_id": wid,
        # Preserve user_id — ownership must survive status updates
        "user_id": existing.get("user_id", ""),
        "created_at": existing.get("created_at", datetime.now(UTC).isoformat()),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    meta.update(extra)
    coll = _collection(wid, "jobs")
    _col(coll).upsert(
        ids=[job_id],
        embeddings=_embed(1),
        documents=[existing.get("prompt", "")],
        metadatas=[meta],
    )


def save_generated_project(job_id: str, file_count: int, zip_path: str, workspace_id: str = "") -> None:
    wid = _resolve_ws(workspace_id)
    existing = _get_job_meta(wid, job_id) or {}
    coll = _collection(wid, "jobs")
    _col(coll).upsert(
        ids=[job_id],
        embeddings=_embed(1),
        documents=[existing.get("prompt", "")],
        metadatas=[
            {
                **{
                    k: existing.get(k, d)
                    for k, d in {
                        "status": "",
                        "project_name": "",
                        "current_agent": "",
                        "error_message": "",
                        "created_at": "",
                        "test_total": 0,
                        "test_passed": 0,
                        "test_failed": 0,
                        "test_skipped": 0,
                        "test_details": "",
                        "test_summary": "",
                    }.items()
                },
                "progress_pct": existing.get("progress_pct", 100),
                "file_count": file_count,
                "zip_path": zip_path,
                "workspace_id": wid,
                # Preserve user_id — must not be lost when project is saved
                "user_id": existing.get("user_id", ""),
                "updated_at": datetime.now(UTC).isoformat(),
            }
        ],
    )


# ── Logs ──────────────────────────────────────────────────────────────────


def log_to_db(
    job_id: str,
    agent_name: str,
    message: str,
    log_level: str = "INFO",
    workspace_id: str = "",
) -> None:
    wid = _resolve_ws(workspace_id)
    level = getattr(logging, log_level, logging.INFO)
    logger.log(level, "[%s/%s] %s", agent_name, job_id[:8], message)
    coll = _collection(wid, "generation_logs")
    try:
        _col(coll).add(
            ids=[f"{job_id}_{uuid.uuid4().hex[:10]}"],
            embeddings=_embed(1),
            documents=[message],
            metadatas=[
                {
                    "job_id": job_id,
                    "agent_name": agent_name,
                    "log_level": log_level,
                    "workspace_id": wid,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            ],
        )
    except Exception as exc:
        logger.warning("ChromaDB log write failed: %s", exc)


def get_logs(job_id: str, workspace_id: str = "", limit: int = 200) -> list[dict[str, Any]]:
    wid = _resolve_ws(workspace_id)
    coll = _collection(wid, "generation_logs")
    try:
        r = _col(coll).get(
            where={"job_id": job_id},
            include=["documents", "metadatas"],
        )
        entries = [
            {
                "agent_name": m.get("agent_name", ""),
                "log_level": m.get("log_level", "INFO"),
                "message": doc,
                "timestamp": m.get("timestamp", ""),
            }
            for doc, m in zip(r["documents"], r["metadatas"])
        ]
        entries.sort(key=lambda e: e["timestamp"])
        return entries[-limit:]
    except Exception:
        return []


# ── Requirements & Blueprints ─────────────────────────────────────────────


def _upsert_json(workspace_id: str, collection: str, rec_id: str, job_id: str, data: dict) -> None:
    wid = _resolve_ws(workspace_id)
    coll = _collection(wid, collection)
    _col(coll).upsert(
        ids=[rec_id],
        embeddings=_embed(1),
        documents=[json.dumps(data)],
        metadatas=[{"job_id": job_id, "workspace_id": wid, "updated_at": datetime.now(UTC).isoformat()}],
    )


def _fetch_json(workspace_id: str, collection: str, rec_id: str) -> dict | None:
    wid = _resolve_ws(workspace_id)
    coll = _collection(wid, collection)
    try:
        r = _col(coll).get(ids=[rec_id], include=["documents"])
        if r["documents"]:
            return json.loads(r["documents"][0])
    except Exception:
        pass
    return None


def save_requirements(job_id: str, data: dict, workspace_id: str = "") -> None:
    wid = _resolve_ws(workspace_id)
    _upsert_json(wid, "requirements", f"req_{job_id}", job_id, data)


def get_requirements(job_id: str, workspace_id: str = "") -> dict | None:
    return _fetch_json(workspace_id, "requirements", f"req_{job_id}")


def save_blueprint(job_id: str, data: dict, workspace_id: str = "") -> None:
    wid = _resolve_ws(workspace_id)
    _upsert_json(wid, "blueprints", f"bp_{job_id}", job_id, data)


def get_blueprint(job_id: str, workspace_id: str = "") -> dict | None:
    return _fetch_json(workspace_id, "blueprints", f"bp_{job_id}")


def update_parsed_requirements(job_id: str, parsed_json: str, workspace_id: str = "") -> None:
    wid = _resolve_ws(workspace_id)
    try:
        save_requirements(job_id, json.loads(parsed_json), wid)
    except Exception:
        pass
