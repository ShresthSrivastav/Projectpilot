"""Shared helpers and state extracted from backend/main.py for route modules."""

import json
import logging
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from database.chroma_db import (
    create_job,
    delete_job,
    get_blueprint,
    get_job,
    get_logs,
    init_db,
    list_jobs,
    save_prompt,
    update_job_status,
)
from database.chroma_db import set_workspace_context
from database.database import init_db as init_sqlalchemy_db
from database.memory_store import (
    create_chat_conversation,
    delete_chat_conversation,
    delete_cross_repo_changes_by_org,
    delete_impact_reports_by_org,
    delete_repositories_by_org,
    delete_repository_relationships_by_org,
    get_analytics_summary,
    get_chat_messages,
    get_project_analytics,
    get_repository_relationships,
    list_chat_conversations,
    verify_conversation_ownership,
    mem_delete_custom_agent,
    mem_delete_custom_workflow,
    mem_delete_plugin,
    mem_get_leaderboard,
    mem_get_leaderboard_categories,
    mem_get_learning_insights,
    mem_get_version_comparisons,
    mem_list_custom_agents,
    mem_list_custom_workflows,
    mem_list_evaluation_reports,
    mem_list_evaluation_runs,
    mem_list_learning_patterns,
    mem_list_learning_recommendations,
    mem_list_regressions,
    mem_save_custom_agent,
    mem_save_custom_workflow,
    mem_save_evaluation_report,
    mem_save_evaluation_run,
    mem_save_marketplace_package,
    mem_save_plugin,
    save_github_repo,
    save_repository_relationship,
    delete_organization as mem_del_organization,
    delete_repository as mem_del_repository,
    get_cross_repo_changes as mem_get_cross_repo_changes,
    get_impact_report_by_id as mem_get_impact_report,
    get_impact_reports as mem_get_impact_reports,
    init_db as init_memory_db,
    save_cross_repo_change as mem_save_cross_repo_change,
    save_impact_report as mem_save_impact_report,
    save_organization as mem_save_organization,
    save_repository as mem_save_repository,
)
from services.auth_service import Role, lookup_role
from services.audit_service import init_audit_db, log_audit_event
from services.activity_service import init_activity_db
from services.notification_service import init_notifications_db
from services.jwt_service import decode_access_token
from services.chat_service import execute_confirmed_action as chat_execute_action
from services.chat_service import process_message as chat_process_message
from services.cleanup_service import start_cleanup_daemon
from services.file_service import BASE_DIR, list_files
from services.llm_service import (
    CLOUD_MODEL,
    call_model,
    ensure_models,
    get_available_models,
    get_available_providers,
    get_pull_status,
    is_available,
    is_cloud_available,
)
from services.marketplace_service import get_marketplace_service
from services.plugin_registry import get_plugin_registry
from services.rate_limiter import RateLimitMiddleware
from services.test_service import run_pytest, run_syntax_check
from services.zip_service import get_zip_path, zip_exists

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4)

_cancel_flags: dict[str, threading.Event] = {}
_flags_lock = threading.Lock()

MAX_BODY_SIZE = int(os.getenv("MAX_REQUEST_BODY_SIZE", "10_485_760"))

VALID_BACKENDS = {"fastapi", "flask", "express", "spring", "go-gin", "none"}
VALID_FRONTENDS = {"streamlit", "react", "vue", "angular", "svelte", "html", "none"}
VALID_DBS = {"sqlite", "postgresql", "mysql", "mongodb", "redis", "dynamodb", "none"}
VALID_CSS = {"none", "bootstrap", "tailwind", "bulma", "materialize"}
VALID_TESTING = {"pytest", "unittest", "jest", "mocha", "vitest", "none"}
VALID_ORM = {"none", "sqlalchemy", "prisma", "typeorm", "django-orm", "mongoose", "sqlx"}
VALID_AUTH = {"none", "jwt", "oauth2", "session", "firebase", "auth0"}
VALID_DEPLOY = {"none", "docker", "docker-compose", "kubernetes", "serverless", "heroku"}

RAG_UPLOAD_DIR = BASE_DIR / "_rag_uploads"


def _resolve_job_path(job_id: str) -> Path:
    p = (BASE_DIR / job_id).resolve()
    if BASE_DIR.resolve() not in p.parents and p != BASE_DIR.resolve():
        raise HTTPException(status_code=403, detail="Invalid job_id.")
    return p


def _validate_file_path(base: Path, relative: str) -> Path:
    target = (base.resolve() / relative).resolve()
    try:
        target.relative_to(base.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Path traversal denied.")
    return target


def _require_job_owner(job_id: str, ws_id: str, uid: str) -> dict:
    job = get_job(job_id, workspace_id=ws_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    owner = job.get("user_id", "")
    if uid and owner and owner != uid:
        raise HTTPException(status_code=403, detail="Forbidden: you do not own this project.")
    return job


def _append_changelog(job_id: str, action: str, details: str) -> None:
    job_dir = BASE_DIR / job_id
    if not job_dir.exists():
        return
    changelog = job_dir / "CHANGELOG.md"
    entry = f"\n## {datetime.now():%Y-%m-%d %H:%M} — {action}\n{details}\n"
    try:
        with open(changelog, "a", encoding="utf-8") as f:
            f.write(entry)
    except OSError:
        pass


def _normalize_job_dir(job_dir: Path) -> None:
    nested = job_dir / job_dir.name
    if nested.exists():
        try:
            import shutil
            for item in nested.iterdir():
                dest = job_dir / item.name
                if dest.exists():
                    if dest.is_dir():
                        shutil.rmtree(str(dest))
                    else:
                        dest.unlink()
                item.rename(dest)
            nested.rmdir()
        except Exception:
            pass


async def _read_all_project_files(job_dir: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for fp in job_dir.rglob("*"):
        if fp.is_file():
            try:
                rel = str(fp.relative_to(job_dir))
                files[rel] = fp.read_text(encoding="utf-8")
            except Exception:
                pass
    return files
