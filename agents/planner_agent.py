"""Planner / Architecture Agent — builds implementation blueprint."""

import json
import logging
import re
import time
from typing import Any

from database.chroma_db import log_to_db, save_blueprint
from services.llm_service import call_model

logger = logging.getLogger(__name__)

_SYSTEM = """You are a senior software architect.
Produce an implementation blueprint as valid JSON ONLY — no markdown, no code fences.

Required shape:
{
  "folders":      ["backend", "frontend", "database", "tests"],
  "files":        [{"path": "relative/path.py", "purpose": "what it does"}],
  "routes":       [{"method": "GET|POST|PUT|DELETE", "path": "/endpoint", "description": "..."}],
  "db_tables":    [{"name": "table_name", "columns": ["id:uuid", "name:string"]}],
  "dependencies": ["fastapi==0.111.0", "streamlit==1.35.0"],
  "tech_stack":   {"backend": "FastAPI", "frontend": "Streamlit", "db": "SQLite"}
}"""


def _parse_json(text: str) -> dict[str, Any]:
    for fn in [
        lambda t: json.loads(t),
        lambda t: json.loads(re.search(r"```(?:json)?\s*(\{.*?\})\s*```", t, re.DOTALL).group(1)),
        lambda t: json.loads(re.search(r"\{.*\}", t, re.DOTALL).group(0)),
    ]:
        try:
            return fn(text)
        except Exception:
            continue
    raise ValueError(f"Cannot extract JSON: {text[:300]}")


def _default(req: dict) -> dict:
    pt = req.get("project_type", "crud_dashboard")
    tables = ["users"]
    if "student" in pt:
        tables.append("students")
    elif "inventory" in pt:
        tables.append("products")
    elif "task" in pt:
        tables.append("tasks")
    elif "employee" in pt:
        tables.append("employees")
    elif "blog" in pt:
        tables.extend(["posts", "comments"])
    else:
        tables.append("items")

    has_auth = req.get("auth_required", "auth" in str(req.get("features", [])).lower())
    auth_deps = ["pyjwt==2.8.0", "passlib[bcrypt]==1.7.4"] if has_auth else []

    stack = req.get("stack", {})
    backend_fw = stack.get("backend", "fastapi")
    frontend_fw = stack.get("frontend", "streamlit")

    backend_deps = (
        ["fastapi==0.111.0", "uvicorn[standard]==0.30.1"]
        if backend_fw == "fastapi"
        else ["flask==3.0.0", "flask-cors==4.0.0"]
    )
    frontend_deps = ["streamlit==1.35.0"] if frontend_fw == "streamlit" else []

    return {
        "folders": ["backend", "frontend", "database", "tests"],
        "files": [
            {"path": "backend/main.py", "purpose": f"{backend_fw.title()} application"},
            {"path": "backend/crud.py", "purpose": "Database CRUD operations"},
            {"path": "database/models.py", "purpose": "SQLAlchemy ORM models"},
            {"path": "database/db.py", "purpose": "Database engine / session"},
            {"path": "frontend/app.py", "purpose": f"{frontend_fw.title()} UI"},
            {"path": "requirements.txt", "purpose": "Python dependencies"},
            {"path": "Dockerfile", "purpose": "Container definition"},
            {"path": "README.md", "purpose": "Project documentation"},
        ],
        "routes": [
            {"method": "POST", "path": "/auth/login", "description": "User login"},
            {"method": "GET", "path": "/items", "description": "List all items"},
            {"method": "POST", "path": "/items", "description": "Create item"},
            {"method": "GET", "path": "/items/{id}", "description": "Get item by ID"},
            {"method": "PUT", "path": "/items/{id}", "description": "Update item"},
            {"method": "DELETE", "path": "/items/{id}", "description": "Delete item"},
            {"method": "GET", "path": "/health", "description": "Health check"},
        ],
        "db_tables": [
            {"name": t, "columns": ["id:string", "created_at:datetime", "updated_at:datetime"]} for t in tables
        ],
        "dependencies": backend_deps
        + frontend_deps
        + [
            "sqlalchemy==2.0.30",
            "pydantic==2.7.1",
            "requests==2.32.3",
            "python-multipart==0.0.9",
            "aiosqlite==0.20.0",
        ]
        + auth_deps,
        "tech_stack": {
            "backend": backend_fw.title(),
            "frontend": frontend_fw.title(),
            "db": "SQLite + SQLAlchemy",
            "auth": "JWT" if has_auth else "none",
        },
    }


def run(requirements: dict[str, Any], job_id: str, model: str = None) -> dict[str, Any]:
    log_to_db(job_id, "PlannerAgent", "Starting architecture planning.")

    prompt = (
        f"Requirements:\n{json.dumps(requirements, indent=2)}\n\n"
        "Create a complete implementation blueprint. "
        "List every file, all REST routes, all DB tables with columns, all pip dependencies."
    )
    blueprint: dict = {}
    t0 = time.monotonic()
    try:
        blueprint = _parse_json(call_model(prompt, system_prompt=_SYSTEM, model=model or "local"))
        elapsed = int((time.monotonic() - t0) * 1000)
        log_to_db(job_id, "PlannerAgent", f"Blueprint received from LLM ({elapsed}ms).")
    except (RuntimeError, ValueError) as exc:
        elapsed = int((time.monotonic() - t0) * 1000)
        log_to_db(job_id, "PlannerAgent", f"LLM FAILED after {elapsed}ms: {exc} — using fallback blueprint", "CRITICAL")
        blueprint = _default(requirements)

    # Fill in any missing top-level keys with sensible defaults
    defaults = _default(requirements)
    for key in ("folders", "files", "routes", "db_tables", "dependencies", "tech_stack"):
        if key not in blueprint or not blueprint[key]:
            blueprint[key] = defaults[key]

    save_blueprint(job_id, blueprint)
    log_to_db(
        job_id,
        "PlannerAgent",
        f"Blueprint ready — {len(blueprint.get('files', []))} files, "
        f"{len(blueprint.get('routes', []))} routes, "
        f"{len(blueprint.get('db_tables', []))} tables.",
    )
    return blueprint
