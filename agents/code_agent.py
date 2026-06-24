"""
Code Generation Agent — generates all project source files.

New in v4:
  - Parallel LLM calls via ThreadPoolExecutor (models.py / crud.py / frontend / reqs run concurrently)
  - Thread-safe file tracking with threading.Lock
  - Stack-aware prompts (backend_framework, frontend_framework, db)
  - job_id / agent passed to call_model for structured logging
"""

import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from typing import Any

from database.chroma_db import log_to_db
from services.file_service import create_job_directory, write_file
from services.llm_service import call_model, clean_code_response, is_cloud_available

logger = logging.getLogger(__name__)

_CODE_SYS = (
    "You are an expert Python developer. "
    "Output raw, complete, runnable code ONLY — no markdown fences, no explanations."
)
_REQS_SYS = (
    "You are a Python dependency manager. "
    "Output only requirements.txt contents — one package==version per line. "
    "No markdown, no comments."
)

# ── Fallback templates (used when LLM fails) ─────────────────────────────────

_FALLBACK_BACKEND = """\
import json
import uuid
from datetime import datetime
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database.db import Base, engine, get_db
from database.models import *

app = FastAPI(title="Generated API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)

@app.get("/health")
def health():
    return {"status": "ok"}
"""

_FALLBACK_MODELS = """\
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from database.db import Base

class Placeholder(Base):
    __tablename__ = "placeholders"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Placeholder id={self.id}>"
"""

_FALLBACK_CRUD = """\
from sqlalchemy.orm import Session
from database.db import Base
from database.models import Placeholder

def get_placeholder(db: Session, placeholder_id: str):
    return db.query(Placeholder).filter(Placeholder.id == placeholder_id).first()

def get_all_placeholders(db: Session, skip: int = 0, limit: int = 100):
    return db.query(Placeholder).offset(skip).limit(limit).all()
"""

_FALLBACK_FRONTEND = """\
import streamlit as st
import requests

st.set_page_config(page_title="Generated App", page_icon=":rocket:")
st.title("Generated App")

API_URL = "http://localhost:8000"

try:
    r = requests.get(f"{API_URL}/health", timeout=5)
    st.success(f"Backend: {r.json().get('status', 'unknown')}")
except Exception as e:
    st.error(f"Cannot reach backend: {e}")
"""

# ── Static file templates ─────────────────────────────────────────────────────

_DOCKERFILE = """\
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/data
EXPOSE 8000
COPY start.sh /start.sh
RUN chmod +x /start.sh
CMD ["/start.sh"]
"""

_START_SH = """\
#!/bin/bash
set -e
uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
sleep 3
# Frontend will be started separately if applicable
wait $BACKEND_PID
"""

_DB_SETUP = '''\
"""Database engine, session factory, and declarative Base."""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
'''

# ── LLM helpers ───────────────────────────────────────────────────────────────


def _gen(prompt: str, model: str, job_id: str, agent: str = "CodeAgent") -> str:
    result = clean_code_response(
        call_model(prompt, system_prompt=_CODE_SYS, model=model or "local", job_id=job_id, agent=agent)
    )
    if not result.strip():
        raise RuntimeError(f"LLM returned empty content for {agent} prompt")
    return result


def _stack_note(req: dict) -> str:
    s = req.get("stack", {})
    return (
        f"Backend: {s.get('backend', 'fastapi')}, "
        f"Frontend: {s.get('frontend', 'streamlit')}, "
        f"DB: {s.get('db', 'sqlite')}"
    )


def _gen_backend(req: dict, bp: dict, model: str, job_id: str) -> str:
    backend = req.get("stack", {}).get("backend", "fastapi")
    features = req.get("features", [])

    return _gen(
        f"""Generate a complete {backend.title()} backend (backend/main.py).

The file MUST contain ALL of the following in order:
1. IMPORTS: from fastapi/flask, pydantic, database.db (Base, engine), database.models (all models)
2. CREATE THE APP: app = FastAPI() or app = Flask(__name__)
3. CORS middleware
4. Pydantic request/response schemas (use suffix like Schema/Create/Out, e.g. UserCreate, UserOut)
5. Auth utils if 'auth' in features (jwt + passlib)
6. lifespan / before_first_request that calls Base.metadata.create_all(bind=engine)
7. ALL endpoints listed in Routes below with full implementations
8. /health endpoint returning {{"status":"ok"}}

CRITICAL RULES:
- DO NOT define SQLAlchemy ORM models or Base - import them from database.models and database.db
- DO NOT skip the app creation or routes
- Async endpoints with type hints (FastAPI) or sync (Flask)
- CORS allow all origins
- HTTPException for errors
- Runnable as: {"uvicorn backend.main:app" if backend == "fastapi" else "python backend/main.py"}

Project: {req.get("project_name", "App")}
Type: {req.get("project_type")}
Features: {", ".join(features)}
Routes: {json.dumps(bp.get("routes", []), indent=2)}
DB Tables: {json.dumps(bp.get("db_tables", []), indent=2)}
Stack: {_stack_note(req)}""",
        model,
        job_id,
    )


def _gen_frontend(req: dict, bp: dict, model: str, job_id: str) -> str:
    frontend = req.get("stack", {}).get("frontend", "streamlit")

    if frontend == "react":
        return _gen(
            f"""Generate a complete React frontend (frontend/ directory):
Project: {req.get("project_name", "App")}
Type: {req.get("project_type")}
Features: {", ".join(req.get("features", []))}
Backend URL: http://localhost:8000
Routes: {json.dumps(bp.get("routes", []), indent=2)}
Stack: {_stack_note(req)}

Generate a single HTML file (frontend/index.html) with embedded CSS and JS using React via CDN.
Rules:
- React via CDN script tags (react, react-dom, babel standalone)
- Fetch API for all backend calls
- Simple, clean UI with navigation
- Form inputs for create/edit operations
- Display lists/data in tables
- Auth token stored in localStorage""",
            model,
            job_id,
        )

    return _gen(
        f"""Generate a complete Streamlit frontend (frontend/app.py):
Project: {req.get("project_name", "App")}
Type: {req.get("project_type")}
Features: {", ".join(req.get("features", []))}
Backend URL: http://localhost:8000
Routes: {json.dumps(bp.get("routes", []), indent=2)}
Stack: {_stack_note(req)}

Rules:
- st.set_page_config with title and icon
- sidebar navigation between sections
- st.dataframe for list views
- st.form for create / edit forms
- st.success / st.error feedback
- requests library for all API calls
- st.session_state for auth token storage
- runnable with: streamlit run frontend/app.py""",
        model,
        job_id,
    )


def _gen_models(req: dict, bp: dict, model: str, job_id: str) -> str:
    return _gen(
        f"""Generate SQLAlchemy ORM models (database/models.py):
Tables: {json.dumps(bp.get("db_tables", []), indent=2)}
Features: {", ".join(req.get("features", []))}

RULES - YOU MUST FOLLOW ALL:
1. Import Base from database.db: `from database.db import Base`
2. Import `from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Date, Text`
3. Import `import uuid` and `from datetime import datetime` at the top
4. Use `Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))` for all id columns (SQLite-compatible string UUIDs)
5. Use `Column(DateTime, default=datetime.utcnow)` for created_at
6. Use `Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)` for updated_at
7. Use proper relationships with back_populates
8. Add __repr__ method on each model
9. Add password_hash column to user/employee tables if auth in features
10. DO NOT use UUID type from sqlalchemy (it is not SQLite compatible)""",
        model,
        job_id,
    )


def _gen_crud(req: dict, bp: dict, model: str, job_id: str) -> str:
    return _gen(
        f"""Generate CRUD module (backend/crud.py):
Tables: {json.dumps(bp.get("db_tables", []), indent=2)}
Features: {", ".join(req.get("features", []))}

Rules:
- Import Base from database.db, import all ORM models from database.models
- Functions: create_X, get_X, get_all_X, update_X, delete_X for each entity
- Full type hints using SQLAlchemy Session
- Return None for not-found cases
- get_user_by_email function if auth in features""",
        model,
        job_id,
    )


def _build_reqs(req: dict) -> list[str]:
    """Build requirements list from stack config."""
    backend = req.get("stack", {}).get("backend", "fastapi")
    frontend = req.get("stack", {}).get("frontend", "streamlit")
    features = req.get("features", [])

    pkgs = ["fastapi", "uvicorn[standard]", "sqlalchemy", "pydantic", "requests", "python-multipart", "aiosqlite"]
    if backend == "flask":
        pkgs = ["flask", "flask-cors", "sqlalchemy", "pydantic", "requests", "aiosqlite"]
    if frontend == "streamlit":
        pkgs.append("streamlit")
    if "auth" in features:
        pkgs.extend(["pyjwt", "passlib[bcrypt]"])
    return pkgs


def _gen_requirements(req: dict, bp: dict, model: str, job_id: str) -> str:
    must_have = _build_reqs(req)

    raw = call_model(
        f"Generate requirements.txt for a project.\n"
        f"Backend: {backend}, Frontend: {frontend}\n"
        f"Features: {', '.join(features)}\n"
        f"Must include: {', '.join(must_have)}\n"
        "Pinned versions only (package==x.y.z). One package per line.",
        system_prompt=_REQS_SYS,
        model=model or "local",
        job_id=job_id,
        agent="CodeAgent",
    )
    lines = [l.strip() for l in raw.splitlines() if l.strip() and "==" in l and not l.strip().startswith(("```", "#"))]
    if lines:
        return "\n".join(lines)
    return "\n".join(f"{p}==0.0.0" for p in must_have) + "\n"


# ── Main entry point ──────────────────────────────────────────────────────────

_LLM_TASK_TIMEOUT = int(os.getenv("LLM_TASK_TIMEOUT", "950"))
_PARALLEL_WORKERS_LOCAL = int(os.getenv("PARALLEL_WORKERS_LOCAL", "2"))
_PARALLEL_WORKERS_CLOUD = int(os.getenv("PARALLEL_WORKERS_CLOUD", "5"))
_SERIAL_FALLBACK = os.getenv("SERIAL_FALLBACK", "true").lower() in ("true", "1", "yes")


def _pick_model(preset: str, requirements: dict, blueprint: dict) -> str:
    if preset == "cloud" and is_cloud_available():
        return "cloud"
    return preset or "local"


def run(
    requirements: dict[str, Any],
    blueprint: dict[str, Any],
    job_id: str,
    model: str = None,
) -> list[str]:
    effective_model = _pick_model(model or "local", requirements, blueprint)
    log_to_db(job_id, "CodeAgent", f"Starting code generation (model={effective_model}, original={model or 'local'}).")
    create_job_directory(job_id)

    generated: list[str] = []
    _lock = threading.Lock()
    _failed: list[str] = []

    def _write(path: str, content: str) -> None:
        content = content or ""
        write_file(job_id, path, content)
        with _lock:
            generated.append(path)
        log_to_db(job_id, "CodeAgent", f"Generated: {path}")

    # ── Parallel LLM generation ───────────────────────────────────────────────
    frontend_fw = requirements.get("stack", {}).get("frontend", "streamlit")
    frontend_path = "frontend/index.html" if frontend_fw != "streamlit" else "frontend/app.py"

    parallel_tasks = {
        "backend/main.py": lambda: _gen_backend(requirements, blueprint, effective_model, job_id),
        "database/models.py": lambda: _gen_models(requirements, blueprint, effective_model, job_id),
        "backend/crud.py": lambda: _gen_crud(requirements, blueprint, effective_model, job_id),
        frontend_path: lambda: _gen_frontend(requirements, blueprint, effective_model, job_id),
        "requirements.txt": lambda: _gen_requirements(requirements, blueprint, effective_model, job_id),
    }

    is_local = effective_model == "local"
    max_workers = _PARALLEL_WORKERS_LOCAL if is_local else _PARALLEL_WORKERS_CLOUD
    log_to_db(
        job_id, "CodeAgent", f"Submitting {len(parallel_tasks)} files (max_workers={max_workers}, local={is_local})…"
    )

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_path = {pool.submit(fn): path for path, fn in parallel_tasks.items()}
        for future in as_completed(future_to_path):
            path = future_to_path[future]
            t0 = time.monotonic()
            try:
                content = future.result(timeout=_LLM_TASK_TIMEOUT)
                elapsed = int((time.monotonic() - t0) * 1000)
                log_to_db(job_id, "CodeAgent", f"{path} completed in {elapsed}ms")
                _write(path, content)
            except TimeoutError:
                elapsed = int((time.monotonic() - t0) * 1000)
                log_to_db(job_id, "CodeAgent", f"{path} TIMEOUT after {elapsed}ms", "ERROR")
                with _lock:
                    _failed.append(path)
            except Exception as exc:
                elapsed = int((time.monotonic() - t0) * 1000)
                log_to_db(job_id, "CodeAgent", f"{path} failed after {elapsed}ms: {exc}", "ERROR")
                with _lock:
                    _failed.append(path)

    # ── Helper: retry a single file with a given model ───────────────────────
    def _retry_fn(path: str, req: dict, bp: dict, mdl: str, jid: str):
        mapping = {
            "backend/main.py": lambda: _gen_backend(req, bp, mdl, jid),
            "database/models.py": lambda: _gen_models(req, bp, mdl, jid),
            "backend/crud.py": lambda: _gen_crud(req, bp, mdl, jid),
            frontend_path: lambda: _gen_frontend(req, bp, mdl, jid),
            "requirements.txt": lambda: _gen_requirements(req, bp, mdl, jid),
        }
        f = mapping.get(path)
        if f is None:
            raise ValueError(f"No generator for {path}")
        return f

    # ── Emergency fallback templates ─────────────────────────────────────────
    _fallback_reqs = "\n".join(f"{p}==0.0.0" for p in _build_reqs(requirements)) + "\n"
    _FALLBACK_TEMPLATES: dict[str, str] = {
        "backend/main.py": _FALLBACK_BACKEND,
        "database/models.py": _FALLBACK_MODELS,
        "backend/crud.py": _FALLBACK_CRUD,
        "requirements.txt": _fallback_reqs,
        frontend_path: _FALLBACK_FRONTEND,
    }

    def _use_fallback_template(path: str) -> None:
        tmpl = _FALLBACK_TEMPLATES.get(path)
        if tmpl and path not in generated:
            log_to_db(job_id, "CodeAgent", f"Using fallback template for {path}", "WARN")
            _write(path, tmpl)

    # ── Serial fallback (same model first, then local if cloud failed) ──────
    if _failed and _SERIAL_FALLBACK:
        log_to_db(job_id, "CodeAgent", f"Retrying {len(_failed)} failed file(s) in serial mode…")
        for attempt_model in [effective_model, "local"] if effective_model != "local" else [effective_model]:
            still_failed = [p for p in _failed if p not in generated]
            if not still_failed:
                break
            log_to_db(job_id, "CodeAgent", f"Serial retry with model={attempt_model} for {len(still_failed)} file(s)")
            for path in still_failed:
                if path in parallel_tasks:
                    t0 = time.monotonic()
                    try:
                        fn = _retry_fn(path, requirements, blueprint, attempt_model, job_id)
                        content = fn()
                        elapsed = int((time.monotonic() - t0) * 1000)
                        log_to_db(job_id, "CodeAgent", f"{path} completed (serial, {attempt_model}) in {elapsed}ms")
                        _write(path, content)
                    except Exception as exc:
                        elapsed = int((time.monotonic() - t0) * 1000)
                        log_to_db(
                            job_id, "CodeAgent", f"{path} serial ({attempt_model}) failed ({elapsed}ms): {exc}", "ERROR"
                        )

    # ── Final fallback for any still-missing critical files ──────────────────
    for path in list(_failed):
        if path not in generated:
            _use_fallback_template(path)

    # ── Static files (fast, no LLM needed) ───────────────────────────────────
    _write("Dockerfile", _DOCKERFILE)
    backend_fw = requirements.get("stack", {}).get("backend", "fastapi")
    if backend_fw == "flask":
        _write("start.sh", "#!/bin/bash\nset -e\npython backend/main.py\n")
    else:
        _write("start.sh", _START_SH)
    _write("database/db.py", _DB_SETUP)
    for pkg in ("backend", "frontend", "database"):
        _write(f"{pkg}/__init__.py", "")

    log_to_db(job_id, "CodeAgent", f"Complete — {len(generated)} files generated, {len(_failed)} failed.")
    return generated
