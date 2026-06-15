"""
ChromaDB storage layer — ProjectPilot.

Uses EphemeralClient with pre-computed dummy embeddings ([0.0]) to completely
bypass the ONNX embedding model download. ChromaDB is used as a pure
key-value + log store — no semantic search needed.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)

CHROMA_PATH = os.getenv("CHROMA_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chroma_data"))
_client: Optional[chromadb.PersistentClient] = None

_DUMMY_EMBED = [[0.0]]   # single-dim dummy — skips ONNX download entirely


def _get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=CHROMA_PATH,
            settings=Settings(anonymized_telemetry=False),
        )
    return _client


def _col(name: str):
    return _get_client().get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
        embedding_function=None,
    )


def _embed(n: int = 1) -> List[List[float]]:
    """Return n dummy embeddings — one per document."""
    return [[0.0]] * n


def init_db() -> None:
    for name in ("jobs", "generation_logs", "requirements", "blueprints"):
        _col(name)
    logger.info("ChromaDB ready (persistent at %s)", CHROMA_PATH)


# ── Jobs ──────────────────────────────────────────────────────────────────────

def create_job(job_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for collection_name in ("generation_logs", "requirements", "blueprints"):
        try:
            _col(collection_name).delete(where={"job_id": job_id})
        except Exception:
            pass
    _col("jobs").upsert(
        ids=[job_id],
        embeddings=_embed(1),
        documents=[""],
        metadatas=[{
            "status":        "queued",
            "project_name":  "",
            "current_agent": "",
            "progress_pct":  0,
            "error_message": "",
            "file_count":    0,
            "zip_path":      "",
            "created_at":    now,
            "updated_at":    now,
        }],
    )


def save_prompt(job_id: str, prompt: str, project_name: str) -> None:
    existing = _get_job_meta(job_id) or {}
    now = datetime.now(timezone.utc).isoformat()
    _col("jobs").upsert(
        ids=[job_id],
        embeddings=_embed(1),
        documents=[prompt],
        metadatas=[{
            "status":        existing.get("status", "queued"),
            "project_name":  project_name,
            "current_agent": existing.get("current_agent", ""),
            "progress_pct":  existing.get("progress_pct", 0),
            "error_message": existing.get("error_message", ""),
            "file_count":    existing.get("file_count", 0),
            "zip_path":      existing.get("zip_path", ""),
            "created_at":    existing.get("created_at", now),
            "updated_at":    now,
        }],
    )


def _get_job_meta(job_id: str) -> Optional[Dict]:
    try:
        r = _col("jobs").get(ids=[job_id], include=["metadatas", "documents"])
        if r["ids"]:
            meta = dict(r["metadatas"][0])
            meta["prompt"] = r["documents"][0]
            return meta
    except Exception:
        pass
    return None


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    meta = _get_job_meta(job_id)
    if meta:
        meta["job_id"] = job_id
    return meta


def list_jobs(limit: int = 20) -> List[Dict[str, Any]]:
    try:
        r = _col("jobs").get(include=["metadatas", "documents"])
        jobs = []
        for i, jid in enumerate(r["ids"]):
            meta = dict(r["metadatas"][i])
            meta["job_id"] = jid
            meta["prompt"] = r["documents"][i]
            jobs.append(meta)
        jobs.sort(key=lambda j: j.get("created_at", ""), reverse=True)
        return jobs[:limit]
    except Exception:
        return []


def delete_job(job_id: str) -> bool:
    try:
        _col("jobs").delete(ids=[job_id])
        logger.info("Deleted job %s from ChromaDB", job_id)
        return True
    except Exception as exc:
        logger.warning("Failed to delete job %s: %s", job_id, exc)
        return False


def update_job_status(
    job_id: str,
    status: str,
    current_agent: str = "",
    progress_pct: int = 0,
    error_message: str = "",
    **extra: Any,
) -> None:
    existing = _get_job_meta(job_id)
    if not existing:
        logger.warning("update_job_status: job %s not found", job_id)
        return
    meta = {
        "status":        status,
        "project_name":  existing.get("project_name", ""),
        "current_agent": current_agent,
        "progress_pct":  progress_pct,
        "error_message": error_message,
        "file_count":    existing.get("file_count", 0),
        "zip_path":      existing.get("zip_path", ""),
        "test_total":    existing.get("test_total", 0),
        "test_passed":   existing.get("test_passed", 0),
        "test_failed":   existing.get("test_failed", 0),
        "test_skipped":  existing.get("test_skipped", 0),
        "test_summary":  existing.get("test_summary", ""),
        "test_details":  existing.get("test_details", ""),
        "created_at":    existing.get("created_at", datetime.now(timezone.utc).isoformat()),
        "updated_at":    datetime.now(timezone.utc).isoformat(),
    }
    meta.update(extra)
    _col("jobs").upsert(
        ids=[job_id],
        embeddings=_embed(1),
        documents=[existing.get("prompt", "")],
        metadatas=[meta],
    )


def save_generated_project(job_id: str, file_count: int, zip_path: str) -> None:
    existing = _get_job_meta(job_id) or {}
    _col("jobs").upsert(
        ids=[job_id],
        embeddings=_embed(1),
        documents=[existing.get("prompt", "")],
        metadatas=[{
            **{k: existing.get(k, d) for k, d in
               {"status": "", "project_name": "", "current_agent": "", "error_message": "",
                "created_at": "", "test_total": 0, "test_passed": 0, "test_failed": 0,
                "test_skipped": 0, "test_details": "", "test_summary": ""}.items()},
            "progress_pct": existing.get("progress_pct", 100),
            "file_count":   file_count,
            "zip_path":     zip_path,
            "updated_at":   datetime.now(timezone.utc).isoformat(),
        }],
    )


# ── Logs ──────────────────────────────────────────────────────────────────────

def log_to_db(
    job_id: str,
    agent_name: str,
    message: str,
    log_level: str = "INFO",
) -> None:
    level = getattr(logging, log_level, logging.INFO)
    logger.log(level, "[%s/%s] %s", agent_name, job_id[:8], message)
    try:
        _col("generation_logs").add(
            ids=[f"{job_id}_{uuid.uuid4().hex[:10]}"],
            embeddings=_embed(1),
            documents=[message],
            metadatas=[{
                "job_id":     job_id,
                "agent_name": agent_name,
                "log_level":  log_level,
                "timestamp":  datetime.now(timezone.utc).isoformat(),
            }],
        )
    except Exception as exc:
        logger.warning("ChromaDB log write failed: %s", exc)


def get_logs(job_id: str, limit: int = 200) -> List[Dict[str, Any]]:
    try:
        r = _col("generation_logs").get(
            where={"job_id": job_id},
            include=["documents", "metadatas"],
        )
        entries = [
            {
                "agent_name": m.get("agent_name", ""),
                "log_level":  m.get("log_level", "INFO"),
                "message":    doc,
                "timestamp":  m.get("timestamp", ""),
            }
            for doc, m in zip(r["documents"], r["metadatas"])
        ]
        entries.sort(key=lambda e: e["timestamp"])
        return entries[-limit:]
    except Exception:
        return []


# ── Requirements & Blueprints ─────────────────────────────────────────────────

def _upsert_json(collection: str, rec_id: str, job_id: str, data: Dict) -> None:
    _col(collection).upsert(
        ids=[rec_id],
        embeddings=_embed(1),
        documents=[json.dumps(data)],
        metadatas=[{"job_id": job_id, "updated_at": datetime.now(timezone.utc).isoformat()}],
    )


def _fetch_json(collection: str, rec_id: str) -> Optional[Dict]:
    try:
        r = _col(collection).get(ids=[rec_id], include=["documents"])
        if r["documents"]:
            return json.loads(r["documents"][0])
    except Exception:
        pass
    return None


def save_requirements(job_id: str, data: Dict) -> None:
    _upsert_json("requirements", f"req_{job_id}", job_id, data)


def get_requirements(job_id: str) -> Optional[Dict]:
    return _fetch_json("requirements", f"req_{job_id}")


def save_blueprint(job_id: str, data: Dict) -> None:
    _upsert_json("blueprints", f"bp_{job_id}", job_id, data)


def get_blueprint(job_id: str) -> Optional[Dict]:
    return _fetch_json("blueprints", f"bp_{job_id}")


def update_parsed_requirements(job_id: str, parsed_json: str) -> None:
    try:
        save_requirements(job_id, json.loads(parsed_json))
    except Exception:
        pass
