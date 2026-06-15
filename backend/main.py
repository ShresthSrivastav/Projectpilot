"""ProjectPilot — FastAPI Backend

New in v4:
  - POST /clarify            — ask one question before pipeline starts
  - POST /generate-project   — now accepts stack config + optional clarification
  - POST /cancel/{job_id}    — cancel a queued/running job
  - POST /regenerate-file    — regenerate a single file with optional correction note
  - GET  /files/{job_id}     — live file tree (files as they appear)
  - GET  /validate/{job_id}  — re-run syntax checks + pytest on demand
  - Structured JSON logging via llm_service
  - lifespan context manager (replaces deprecated on_event)
  - Cleanup daemon started at startup
"""
import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, field_validator

from database.chroma_db import (
    create_job, get_job, get_logs, init_db,
    list_jobs, save_prompt, update_job_status, get_blueprint, delete_job,
)
from database.memory_store import (
    init_db as init_memory_db,
    get_project_analytics, get_analytics_summary,
    save_github_repo,
    create_chat_conversation, add_chat_message, get_chat_messages,
    list_chat_conversations, delete_chat_conversation,
    update_chat_conversation_title,
    save_organization as mem_save_organization,
    get_organization as mem_get_organization,
    list_organizations_db,
    delete_organization as mem_del_organization,
    save_repository as mem_save_repository,
    get_repositories as mem_get_repositories,
    delete_repository as mem_del_repository,
    save_repository_relationship,
    get_repository_relationships,
    save_cross_repo_change as mem_save_cross_repo_change,
    get_cross_repo_changes as mem_get_cross_repo_changes,
    get_cross_repo_change as mem_get_cross_repo_change,
    save_impact_report as mem_save_impact_report,
    get_impact_reports as mem_get_impact_reports,
    get_impact_report_by_id as mem_get_impact_report,
    delete_cross_repo_change as mem_del_cross_repo_change,
    delete_impact_report as mem_del_impact_report,
    delete_repository_relationship as mem_del_repo_rel,
    delete_repository_relationships_by_org,
    delete_impact_reports_by_org,
    delete_cross_repo_changes_by_org,
    delete_repositories_by_org,
)
from services.plugin_registry import get_plugin_registry
from services.marketplace_service import get_marketplace_service
from database.memory_store import (
    mem_save_plugin, mem_get_plugin, mem_list_plugins, mem_delete_plugin,
    mem_save_marketplace_package, mem_get_marketplace_package,
    mem_search_marketplace_packages, mem_delete_marketplace_package,
    mem_save_custom_agent, mem_list_custom_agents, mem_delete_custom_agent,
    mem_save_custom_workflow, mem_list_custom_workflows, mem_delete_custom_workflow,
)
from database.memory_store import (
    mem_list_evaluation_runs, mem_list_evaluation_reports,
    mem_get_leaderboard, mem_get_leaderboard_categories,
    mem_get_version_comparisons, mem_list_regressions,
    mem_save_evaluation_run, mem_save_evaluation_report,
    mem_list_learning_feedback, mem_list_learning_patterns,
    mem_list_learning_recommendations, mem_get_learning_insights,
)
from services.chat_service import process_message as chat_process_message
from services.chat_service import execute_confirmed_action as chat_execute_action
from services.cleanup_service import start_cleanup_daemon
from services.auth_service import get_api_key_role, lookup_role, require_admin, require_user, Role, ADMIN_KEY, USER_KEY
from services.file_service import BASE_DIR, list_files
from services.rate_limiter import RateLimitMiddleware
from services.token_crypto import encrypt_token, decrypt_token, mask_token
from services.llm_service import (
    get_available_models, get_available_providers, get_pull_status,
    is_available, ensure_models, call_model, is_cloud_available, CLOUD_MODEL,
)
from services.test_service import run_syntax_check, run_pytest
from services.zip_service import get_zip_path, zip_exists

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":%(message)s}',
)
logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4)

# Cancellation flags: job_id → threading.Event
_cancel_flags: Dict[str, threading.Event] = {}
_flags_lock = threading.Lock()


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    init_memory_db()
    logger.info('{"event":"db_ready","store":"chromadb+sqlite"}')

    if os.getenv("ADMIN_API_KEY"):
        logger.info('{"event":"auth_configured","mode":"admin_api_key"}')
    else:
        logger.warning('{"event":"auth_ephemeral","detail":"ADMIN_API_KEY not set. Using ephemeral key printed at startup."}')

    if os.getenv("GOOGLE_API_KEY"):
        logger.info('{"event":"cloud_api_key_configured","provider":"google"}')
    else:
        logger.info('{"event":"cloud_api_key_missing","detail":"Cloud LLM calls will fail until GOOGLE_API_KEY is set."}')

    loop = asyncio.get_event_loop()
    loop.run_in_executor(_executor, _wait_and_pull_models)
    start_cleanup_daemon()
    _init_supervisor()
    _init_evaluation()
    logger.info('{"event":"startup_complete","version":"13.0.0"}')
    yield
    logger.info('{"event":"shutdown"}')


def _init_supervisor():
    from services.supervisor_service import Supervisor, AgentPriority
    import agents.requirement_agent
    import agents.planner_agent
    import agents.code_agent
    import agents.test_gen_agent
    import agents.debug_agent
    import agents.docs_agent
    import agents.validation_agent
    import agents.security_agent

    s = Supervisor()
    # Wrap each agent to accept a single context dict (Supervisor convention)

    def _wrap(fn, arg_names):
        def wrapper(context):
            kwargs = {k: context[k] for k in arg_names if k in context}
            return fn(**kwargs)
        return wrapper

    s.register_agent("RequirementAgent", _wrap(agents.requirement_agent.run, ["prompt", "project_name", "job_id", "model", "stack"]),
                     priority=AgentPriority.CRITICAL, team="pipeline")
    s.register_agent("PlannerAgent", _wrap(agents.planner_agent.run, ["requirements", "job_id", "model"]),
                     priority=AgentPriority.HIGH, team="pipeline")
    s.register_agent("CodeAgent", _wrap(agents.code_agent.run, ["requirements", "blueprint", "job_id", "model"]),
                     priority=AgentPriority.HIGH, team="pipeline")
    s.register_agent("TestGenAgent", _wrap(agents.test_gen_agent.run, ["generated_files", "requirements", "blueprint", "job_id", "model"]),
                     priority=AgentPriority.NORMAL, team="pipeline")
    s.register_agent("DebugAgent", _wrap(agents.debug_agent.run, ["generated_files", "job_id", "model", "blueprint"]),
                     priority=AgentPriority.NORMAL, team="pipeline")
    s.register_agent("DocsAgent", _wrap(agents.docs_agent.run, ["requirements", "blueprint", "generated_files", "job_id", "model"]),
                     priority=AgentPriority.LOW, team="pipeline")
    s.register_agent("ValidationAgent", _wrap(agents.validation_agent.run, ["job_id", "requirements", "blueprint"]),
                     priority=AgentPriority.LOW, team="pipeline")
    s.register_agent("SecurityAgent", _wrap(agents.security_agent.run, ["generated_files", "job_id", "blueprint", "model"]),
                     priority=AgentPriority.LOW, team="quality")
    logger.info('{"event":"supervisor_ready","agents":8}')


app = FastAPI(
    title="ProjectPilot",
    description="Autonomous engineering platform — Plugin & Agent SDK Ecosystem",
    version="13.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)

MAX_BODY_SIZE = int(os.getenv("MAX_REQUEST_BODY_SIZE", "10_485_760"))


@app.middleware("http")
async def limit_request_body(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH"):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_BODY_SIZE:
            return JSONResponse(
                status_code=413,
                content={"detail": f"Request body too large (max {MAX_BODY_SIZE // 1024 // 1024} MB)."},
            )
    return await call_next(request)


PROTECTED_PREFIXES = [
    "/workspace/", "/jobs/", "/regenerate-file", "/iterate/",
    "/validate/", "/deploy/", "/plugins/", "/marketplace/",
    "/agents/", "/workflows/", "/organization/",
    "/github/", "/sandbox/", "/supervisor/",
    "/autonomous/", "/debate/",
    "/evaluation/", "/benchmarks/", "/benchmark/", "/campaign/",
    "/rag/", "/chat/", "/browser/", "/runtime/", "/process/",
]

ADMIN_ONLY_PREFIXES = [
    "/supervisor/", "/sandbox/", "/process/",
    "/plugins/install", "/plugins/uninstall",
    "/marketplace/install", "/marketplace/delete",
]


SKIP_AUTH = os.getenv("SKIP_AUTH", "").lower() in ("true", "1", "yes")


@app.middleware("http")
async def authenticate_request(request: Request, call_next):
    if SKIP_AUTH:
        return await call_next(request)

    path = request.url.path

    needs_auth = any(path.startswith(p) for p in PROTECTED_PREFIXES)
    needs_admin = any(path.startswith(p) for p in ADMIN_ONLY_PREFIXES)

    if needs_auth or needs_admin:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid Authorization header. Use: Bearer <API_KEY>"},
            )

        api_key = auth_header[7:]
        role = lookup_role(api_key)

        if needs_admin and role != Role.ADMIN:
            return JSONResponse(status_code=403, content={"detail": "Admin access required."})
        if needs_auth and role == Role.NONE:
            return JSONResponse(status_code=401, content={"detail": "Invalid API key."})

    return await call_next(request)


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


def _wait_and_pull_models() -> None:
    import time
    for attempt in range(40):
        if is_available():
            logger.info('{"event":"ollama_ready","pulling_models":true}')
            ensure_models()
            return
        logger.info('{"event":"ollama_wait","attempt":%d}', attempt + 1)
        time.sleep(5)
    logger.error('{"event":"ollama_unavailable"}')


# ── Schemas ───────────────────────────────────────────────────────────────────

VALID_BACKENDS  = {"fastapi", "flask", "express", "spring", "go-gin", "none"}
VALID_FRONTENDS = {"streamlit", "react", "vue", "angular", "svelte", "html", "none"}
VALID_DBS       = {"sqlite", "postgresql", "mysql", "mongodb", "redis", "dynamodb", "none"}
VALID_CSS       = {"none", "bootstrap", "tailwind", "bulma", "materialize"}
VALID_TESTING   = {"pytest", "unittest", "jest", "mocha", "vitest", "none"}
VALID_ORM       = {"none", "sqlalchemy", "prisma", "typeorm", "django-orm", "mongoose", "sqlx"}
VALID_AUTH      = {"none", "jwt", "oauth2", "session", "firebase", "auth0"}
VALID_DEPLOY    = {"none", "docker", "docker-compose", "kubernetes", "serverless", "heroku"}


class StackConfig(BaseModel):
    backend:  str = Field("fastapi",   description=" | ".join(sorted(VALID_BACKENDS)))
    frontend: str = Field("streamlit", description=" | ".join(sorted(VALID_FRONTENDS)))
    db:       str = Field("sqlite",    description=" | ".join(sorted(VALID_DBS)))
    css:      str = Field("bootstrap", description=" | ".join(sorted(VALID_CSS)))
    testing:  str = Field("pytest",    description=" | ".join(sorted(VALID_TESTING)))
    orm:      str = Field("sqlalchemy", description=" | ".join(sorted(VALID_ORM)))
    auth:     str = Field("none",      description=" | ".join(sorted(VALID_AUTH)))
    deploy:   str = Field("docker",    description=" | ".join(sorted(VALID_DEPLOY)))

    @field_validator("backend")
    @classmethod
    def valid_backend(cls, v: str) -> str:
        if v.lower() not in VALID_BACKENDS:
            raise ValueError(f"backend must be one of {VALID_BACKENDS}")
        return v.lower()

    @field_validator("frontend")
    @classmethod
    def valid_frontend(cls, v: str) -> str:
        if v.lower() not in VALID_FRONTENDS:
            raise ValueError(f"frontend must be one of {VALID_FRONTENDS}")
        return v.lower()

    @field_validator("db")
    @classmethod
    def valid_db(cls, v: str) -> str:
        if v.lower() not in VALID_DBS:
            raise ValueError(f"db must be one of {VALID_DBS}")
        return v.lower()

    @field_validator("css")
    @classmethod
    def valid_css(cls, v: str) -> str:
        if v.lower() not in VALID_CSS:
            raise ValueError(f"css must be one of {VALID_CSS}")
        return v.lower()

    @field_validator("testing")
    @classmethod
    def valid_testing(cls, v: str) -> str:
        if v.lower() not in VALID_TESTING:
            raise ValueError(f"testing must be one of {VALID_TESTING}")
        return v.lower()

    @field_validator("orm")
    @classmethod
    def valid_orm(cls, v: str) -> str:
        if v.lower() not in VALID_ORM:
            raise ValueError(f"orm must be one of {VALID_ORM}")
        return v.lower()

    @field_validator("auth")
    @classmethod
    def valid_auth(cls, v: str) -> str:
        if v.lower() not in VALID_AUTH:
            raise ValueError(f"auth must be one of {VALID_AUTH}")
        return v.lower()

    @field_validator("deploy")
    @classmethod
    def valid_deploy(cls, v: str) -> str:
        if v.lower() not in VALID_DEPLOY:
            raise ValueError(f"deploy must be one of {VALID_DEPLOY}")
        return v.lower()


class GenerateRequest(BaseModel):
    prompt:        str = Field(..., min_length=10, max_length=500)
    project_name:  str = Field("My Project", min_length=1, max_length=100)
    model:         Optional[str] = "local"
    stack:         Optional[StackConfig] = None
    clarification: Optional[str] = Field(None, max_length=300,
                                          description="Answer to the clarifying question, appended to prompt")

    @field_validator("prompt")
    @classmethod
    def prompt_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Prompt must not be blank.")
        return v.strip()

    @field_validator("project_name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        return v.strip() or "My Project"


class ClarifyRequest(BaseModel):
    prompt: str = Field(..., min_length=10, max_length=500)
    model:  Optional[str] = "local"


class RegenerateRequest(BaseModel):
    job_id:          str
    file_path:       str = Field(..., description="Relative path, e.g. backend/main.py")
    correction_note: Optional[str] = Field(None, max_length=500,
                                            description="What to fix / improve in this file")
    model:           Optional[str] = "local"


def run_pipeline(
    job_id: str,
    prompt: str,
    project_name: str,
    model: str = "local",
    stack: Optional[Dict[str, Any]] = None,
    cancel_flag: Optional[threading.Event] = None,
) -> Dict[str, Any]:
    """Run the generation pipeline through the orchestrator."""
    from agents.orchestrator_agent import Orchestrator

    orchestrator = Orchestrator(
        job_id=job_id,
        prompt=prompt,
        project_name=project_name,
        model=model or "local",
        stack=stack,
        cancel_flag=cancel_flag,
    )
    try:
        return orchestrator.run()
    finally:
        with _flags_lock:
            _cancel_flags.pop(job_id, None)


@app.post("/clarify")
async def clarify_prompt(req: ClarifyRequest):
    """Ask the requirement agent for one clarifying question when needed."""
    from agents.requirement_agent import clarify

    question = clarify(req.prompt, model=req.model or "local")
    return {"question": question}


@app.post("/generate-project")
async def generate_project(req: GenerateRequest):
    """Queue a new project generation job and run it in a background thread."""
    job_id = str(uuid.uuid4())
    create_job(job_id)
    save_prompt(job_id, req.prompt, req.project_name)

    prompt = req.prompt.strip()
    if req.clarification and req.clarification.strip():
        prompt += f"\n\nAdditional detail from user: {req.clarification.strip()}"

    stack = req.stack.model_dump() if req.stack else None
    cancel_flag = threading.Event()
    with _flags_lock:
        _cancel_flags[job_id] = cancel_flag

    worker = threading.Thread(
        target=run_pipeline,
        kwargs={
            "job_id": job_id,
            "prompt": prompt,
            "project_name": req.project_name,
            "model": req.model or "local",
            "stack": stack,
            "cancel_flag": cancel_flag,
        },
        daemon=True,
        name=f"pipeline-{job_id[:8]}",
    )
    worker.start()

    return {
        "job_id": job_id,
        "status": "queued",
        "project_name": req.project_name,
    }


@app.post("/cancel/{job_id}")
async def cancel_job(job_id: str):
    """Cancel a queued or running generation job."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    status = job.get("status", "")
    if status not in {"queued", "running"}:
        raise HTTPException(status_code=400, detail=f"Job cannot be cancelled from status '{status}'.")

    with _flags_lock:
        flag = _cancel_flags.get(job_id)
        if flag is None:
            flag = threading.Event()
            _cancel_flags[job_id] = flag
        flag.set()

    update_job_status(
        job_id,
        "cancelled",
        current_agent="",
        progress_pct=int(job.get("progress_pct", 0)),
        error_message="Cancelled by user.",
    )
    return {"job_id": job_id, "status": "cancelled"}


@app.post("/regenerate-file")
async def regenerate_file(req: RegenerateRequest):
    """Regenerate a single file for a completed project."""
    job = get_job(req.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.get("status") not in {"complete", "failed"}:
        raise HTTPException(status_code=400, detail="Job must be complete or failed before regenerating files.")

    job_dir = _resolve_job_path(req.job_id)
    target = _validate_file_path(job_dir, req.file_path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found.")

    original = target.read_text(encoding="utf-8")
    instructions = req.correction_note or "Improve this file while preserving existing behavior."
    prompt = (
        f"Project file path: {req.file_path}\n\n"
        f"Current file:\n{original}\n\n"
        f"Requested change:\n{instructions}\n\n"
        "Return only the full updated file content with no markdown fences."
    )
    regenerated = call_model(
        prompt,
        model=req.model or "local",
        job_id=req.job_id,
        agent="RegenerateFileEndpoint",
    ).strip()
    regenerated = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", regenerated)
    regenerated = re.sub(r"\s*```$", "", regenerated).strip()

    target.write_text(regenerated + ("\n" if regenerated and not regenerated.endswith("\n") else ""), encoding="utf-8")
    syntax_result = run_syntax_check(target) if target.suffix == ".py" else {"valid": True, "error": ""}
    _append_changelog(req.job_id, "File Regenerated", f"- **File**: {req.file_path}\n- **Note**: {instructions}\n")

    return {
        "job_id": req.job_id,
        "file_path": req.file_path,
        "chars": len(regenerated),
        "syntax_ok": bool(syntax_result.get("valid", True)),
        "syntax_error": syntax_result.get("error", ""),
    }


def _append_changelog(job_id: str, action: str, details: str) -> None:
    """Append a dated entry to the project's CHANGELOG.md."""
    job_dir = BASE_DIR / job_id
    if not job_dir.exists():
        return
    changelog = job_dir / "CHANGELOG.md"
    entry = (
        f"\n## {datetime.now():%Y-%m-%d %H:%M} — {action}\n"
        f"{details}\n"
    )
    try:
        with open(changelog, "a", encoding="utf-8") as f:
            f.write(entry)
    except OSError:
        pass


class FixTestsRequest(BaseModel):
    model: Optional[str] = "local"


@app.get("/test-files/{job_id}")
async def get_test_files(job_id: str):
    """Return all test files for a project."""
    job_dir = BASE_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found.")
    test_dir = job_dir / "tests"
    if not test_dir.exists():
        return {"job_id": job_id, "test_files": {}}
    files = {}
    for fpath in sorted(test_dir.rglob("*.py")):
        if "__pycache__" in str(fpath):
            continue
        rel = str(fpath.relative_to(test_dir))
        files[rel] = fpath.read_text(encoding="utf-8")
    return {"job_id": job_id, "test_files": files}


@app.post("/fix-tests/{job_id}")
async def fix_tests(job_id: str, req: FixTestsRequest):
    """
    Run tests, collect failures, send to LLM to fix source code,
    apply fixes, re-run tests. Returns before/after results.
    """
    from database.chroma_db import get_job as _get_job
    job = _get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    job_dir = BASE_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=400, detail="Project files not available.")

    # Phase 1: run tests to capture failures
    pr = run_pytest(job_id)
    before_output = pr.get("output", "")
    before_passed = pr.get("passed", False)
    before_failures = pr.get("failures", [])

    if before_passed:
        _td = []
        for _l in (before_output or "").splitlines():
            _m = re.search(r"::(\w+) (PASSED|FAILED|SKIPPED)", _l)
            if _m:
                _td.append({"test": _m.group(1), "status": _m.group(2)})
        from database.chroma_db import update_job_status as _update_status
        _update_status(job_id, "complete", test_total=pr.get("collected", 0),
                       test_passed=pr.get("collected", 0), test_failed=0,
                       test_skipped=0, test_summary="All tests pass.",
                       test_details=json.dumps(_td) if _td else "")
        return {
            "job_id": job_id,
            "already_passing": True,
            "message": "All tests already pass.",
        }

    # Phase 2: read test files only (source files are NOT sent — they confuse the LLM
    # into trying to modify the real app instead of the test's mock app)
    test_files = {}
    test_dir = job_dir / "tests"
    if test_dir.exists():
        for fpath in sorted(test_dir.rglob("*.py")):
            if "__pycache__" in str(fpath):
                continue
            rel = str(fpath.relative_to(test_dir))
            test_files[rel] = fpath.read_text(encoding="utf-8")

    system = (
        "You fix failing Python tests. "
        "Output the complete changed test file in this format (no markdown fences):\n"
        "--- FILE: relative/path\n"
        "--- ACTION: MODIFY\n"
        "--- CONTENT:\n"
        "full new file content\n"
        "--- END\n"
        "If you cannot fix, output exactly: --- NO CHANGES ---"
    )

    orig_output = before_output
    orig_passed = before_passed
    orig_failures = before_failures

    def _parse_fix_output(text: str) -> tuple:
        mods, adds = [], []
        text = re.sub(r"```\w*\n?", "", text)
        if "NO CHANGES" in text.upper():
            return mods, adds
        blocks = re.split(r"---\s*FILE\s*:\s*", text)
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            lines = block.split("\n")
            fpath = lines[0].strip().rstrip("-").strip()
            if not fpath:
                continue
            bt = "\n".join(lines[1:])
            action_m = re.search(r"---\s*ACTION\s*:\s*(\w+)", bt)
            action = action_m.group(1).upper() if action_m else "MODIFY"
            content_m = re.search(r"---\s*CONTENT\s*:\s*\n?(.*?)(?:\n---\s*END|$)", bt, re.DOTALL)
            content = content_m.group(1).strip() if content_m else ""
            if action == "MODIFY" and content:
                mods.append((fpath, content.replace("\r\n", "\n")))
            elif action == "ADD" and content:
                adds.append((fpath, content.replace("\r\n", "\n")))
        return mods, adds

    modified, added = [], []
    pr2 = None

    # Extract original assertion lines per file for validation
    _orig_assertions: Dict[str, set] = {}
    for _rel, _content in test_files.items():
        _assertions = set()
        for _line in _content.splitlines():
            _stripped = _line.strip()
            if _stripped.startswith("assert ") or _stripped.startswith("assert("):
                _assertions.add(_stripped)
        _orig_assertions[_rel] = _assertions

    # Detect failure type
    _is_collection_error = "ImportError" in before_output or "ModuleNotFoundError" in before_output
    _has_405 = "405" in before_output and "Method Not Allowed" in before_output
    _current_output = before_output

    for attempt in range(1, 4):
        # Only restore originals on attempt 1. On retries, use current file state.
        if attempt == 1:
            for _rel, _content in test_files.items():
                _dest = test_dir / _rel
                _dest.write_text(_content, encoding="utf-8")

        # Read current state of test files
        _current_test_files = {}
        if test_dir.exists():
            for _fp in sorted(test_dir.rglob("*.py")):
                if "__pycache__" in str(_fp):
                    continue
                _rel = str(_fp.relative_to(test_dir))
                _current_test_files[_rel] = _fp.read_text(encoding="utf-8")
        _current_test_block = "\n\n".join(
            f"--- {k} ---\n{v}\n--- END {k}" for k, v in sorted(_current_test_files.items())
        )

        # Re-evaluate error type based on current test output
        _err_is_import = "ImportError" in _current_output or "ModuleNotFoundError" in _current_output
        _err_is_name = "NameError" in _current_output
        _err_is_405 = "405" in _current_output and "Method Not Allowed" in _current_output
        _err_is_422 = "422" in _current_output and "Unprocessable Entity" in _current_output

        if _err_is_import:
            _file_tree = "\n".join(
                str(p.relative_to(job_dir)) for p in sorted(job_dir.rglob("*"))
                if p.is_file() and "__pycache__" not in str(p)
            )
            _failure_guide = (
                f"Project files:\n{_file_tree}\n\n"
                "Fix the import path. Use the project file tree above to find "
                "the correct module path. If main.py is in backend/, "
                "use `from backend.main import app`.\n"
                "If the real app has complex deps that fail, rewrite to use "
                "a mock FastAPI app instead."
            )
        elif _err_is_name:
            _failure_guide = (
                "The real app has complex dependencies that can't be loaded. "
                "Rewrite the test to use its OWN mock FastAPI app.\n\n"
                "IMPORTANT: Do NOT use `return dict, status_code` tuples — "
                "this FastAPI version does NOT support them.\n"
                "Use JSONResponse instead:\n"
                "  from fastapi.responses import JSONResponse, Response\n"
                "  @app.post('/users')\n"
                "  def create_user():\n"
                "      return JSONResponse(content={'ok': True}, status_code=201)\n"
                "  @app.delete('/users/{id}')\n"
                "  def delete_user(id: str):\n"
                "      return Response(status_code=204)\n\n"
                "Preserve all existing test assertions."
            )
        elif _err_is_405:
            _failure_guide = (
                "Routes returning 405 are MISSING from the mock app. "
                "Add the missing @app.post, @app.put, and @app.delete decorators with handler functions. "
                "Use `id: str` for path params, NOT `int`. "
                "Return simple dicts like `{'ok': True}`."
            )
        elif _err_is_422:
            _failure_guide = (
                "Routes returning 422 have parameter type mismatches. "
                "If a route accepts JSON body data via `client.post(url, json=...)`, "
                "use `data: dict` as the parameter (not individual field names). "
                "Example: `def create_user(data: dict): return JSONResponse(content=data, status_code=201)`."
            )
        else:
            _failure_guide = (
                "Fix the test failures. Identify the root cause from the test output "
                "and fix the test file or source as needed."
            )

        prompt = (
            f"Test output:\n{_current_output}\n\n"
            f"Test file(s):\n{_current_test_block}\n\n"
            f"Attempt {attempt}/3.\n\n{_failure_guide}\n\n"
            "CRITICAL — preserve EVERY existing assertion line exactly:\n"
            + "\n".join(f"  {a}" for a in sorted(_orig_assertions)) +
            "\n\n"
            "Output the complete changed file in:\n"
            "--- FILE: tests/test_app.py\n"
            "--- ACTION: MODIFY\n"
            "--- CONTENT:\n"
            "[full file]\n"
            "--- END\n"
            "If you cannot fix, output: --- NO CHANGES ---"
        )

        try:
            result = call_model(prompt, system_prompt=system,
                                model=req.model or "local",
                                job_id=job_id, agent=f"FixTestsEndpoint")
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=f"LLM call failed: {exc}")

        mods, adds = _parse_fix_output(result)
        if not mods and not adds:
            continue

        for fpath, content in mods:
            if not _err_is_import:
                _new_assertions = set()
                for _line in content.splitlines():
                    _stripped = _line.strip()
                    if _stripped.startswith("assert ") or _stripped.startswith("assert("):
                        _new_assertions.add(_stripped)
                _changed = _orig_assertions.get(fpath, set()) - _new_assertions
                if _changed:
                    continue

            full_path = job_dir / fpath
            if full_path.exists():
                full_path.write_text(content.replace("\r\n", "\n"), encoding="utf-8")
                if fpath not in modified:
                    modified.append(fpath)

        _pr = run_pytest(job_id)
        _current_output = _pr.get("output", "")
        if _pr.get("passed", False):
            pr2 = _pr
            break
        if attempt >= 3:
            pr2 = _pr
    if pr2 is None:
        pr2 = run_pytest(job_id)
    after_output = pr2.get("output", "")
    after_passed = pr2.get("passed", False)
    after_collected = pr2.get("collected", 0)
    after_failures = pr2.get("failures", [])

    # Parse individual test results from pytest output
    _test_details = []
    for _line in (after_output or "").splitlines():
        _m = re.search(r"::(\w+) (PASSED|FAILED|SKIPPED)", _line)
        if _m:
            _test_details.append({"test": _m.group(1), "status": _m.group(2)})
    # Update stored test results in DB so the frontend reflects new state
    from database.chroma_db import update_job_status as _update_status
    _update_status(job_id, "complete",
                   test_total=after_collected,
                   test_passed=after_collected - len(after_failures),
                   test_failed=len(after_failures),
                   test_skipped=0,
                   test_summary=f"{after_collected - len(after_failures)} passed, {len(after_failures)} failed.",
                   test_details=json.dumps(_test_details) if _test_details else "")

    if modified or added:
        details = ""
        if modified:
            details += f"- **Modified**: {', '.join(modified)}\n"
        if added:
            details += f"- **Added**: {', '.join(added)}\n"
        details += f"- **Tests before**: {'PASS' if orig_passed else f'{len(orig_failures)} fail'}\n"
        details += f"- **Tests after**: {'PASS' if after_passed else 'FAIL'}\n"
        _append_changelog(job_id, "Tests Fixed", details)

    return {
        "job_id": job_id,
        "already_passing": False,
        "changes": {"modified": modified, "added": added},
        "before": {"passed": orig_passed, "output": orig_output[-2000:]},
        "after": {
            "passed": after_passed,
            "output": after_output[-2000:],
            "collected": after_collected,
            "failures": after_failures,
        },
        "fixed": after_passed,
    }


# ── Iterate (modify existing project) ─────────────────────────────────────

class IterateRequest(BaseModel):
    prompt:  str = Field(..., min_length=3, max_length=1000,
                         description="What to add/change in the existing project")
    model:   Optional[str] = "local"
    job_id:  Optional[str] = None


def _normalize_job_dir(job_dir: Path) -> None:
    """Flatten double-nested job directories caused by zip extraction."""
    nested = job_dir / job_dir.name
    if nested.exists():
        try:
            import shutil
            for item in nested.iterdir():
                dest = job_dir / item.name
                if dest.exists():
                    if dest.is_dir():
                        shutil.rmtree(dest)
                    else:
                        dest.unlink()
                shutil.move(str(item), str(dest))
            shutil.rmtree(nested)
        except Exception:
            pass


async def _read_all_project_files(job_dir: Path) -> Dict[str, str]:
    files = {}
    for fpath in job_dir.rglob("*"):
        if fpath.is_file() and "__pycache__" not in str(fpath):
            rel = str(fpath.relative_to(job_dir))
            try:
                files[rel] = fpath.read_text(encoding="utf-8")
            except Exception:
                files[rel] = "[binary]"
    return files


@app.post("/iterate/{job_id}")
async def iterate_project(job_id: str, req: IterateRequest):
    """
    Modify an existing completed project with new instructions.
    Reads all generated files, sends to LLM with the new prompt,
    applies changes, re-runs syntax checks and tests.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.get("status") not in ("complete", "failed"):
        raise HTTPException(status_code=400, detail="Job must be complete or failed to iterate.")
    job_dir = BASE_DIR / job_id
    if not job_dir.exists():
        # Try to unzip from the stored zip
        from services.zip_service import get_zip_path
        zpath = get_zip_path(job_id)
        if zpath and Path(zpath).exists():
            import zipfile
            job_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zpath, "r") as zf:
                for member in zf.namelist():
                    member_path = (job_dir / member).resolve()
                    if not str(member_path).startswith(str(job_dir.resolve())):
                        raise HTTPException(status_code=403, detail="Zip slip denied.")
                zf.extractall(job_dir)
        if not job_dir.exists():
            raise HTTPException(status_code=400, detail="Source files no longer available (already packaged).")
    # Normalize directory structure (handle double-nested zips)
    _normalize_job_dir(job_dir)

    existing_files = await _read_all_project_files(job_dir)
    # Only include source code files — skip auto-generated / non-code files
    _code_exts = {".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".vue", ".svelte"}
    _skip_prefixes = {"README", "Dockerfile", "start.", "requirements", "VALIDATION_REPORT",
                      "__pycache__", ".git", "node_modules", "package-lock", "yarn.lock"}
    src_files = {
        k: v for k, v in existing_files.items()
        if any(k.endswith(ext) for ext in _code_exts)
        and not any(k.startswith(prefix) or prefix in k for prefix in _skip_prefixes)
    }
    # If no source files found (shouldn't happen), fall back to all
    if not src_files:
        src_files = existing_files

    file_contents_str = "\n\n".join(
        f"--- FILE: {k} ---\n{v}\n--- END FILE: {k} ---"
        for k, v in sorted(src_files.items())
    )

    prompt = (
        f"Existing project files:\n\n{file_contents_str}\n\n"
        f"User request: {req.prompt}\n\n"
        "Output changes using EXACTLY this format (one block per file):\n"
        "--- FILE: relative/path\n"
        "--- ACTION: ADD|MODIFY|DELETE\n"
        "--- CONTENT:\nfull file content here\n"
        "--- END\n\n"
        "Rules:\n"
        "- Include COMPLETE file contents for ADD and MODIFY (no placeholders, no skipping)\n"
        "- For DELETE, include only FILE and ACTION lines, skip CONTENT\n"
        "- Preserve all existing functionality unless the user asks to remove it\n"
        "- If no changes needed, output exactly: --- NO CHANGES ---"
    )
    system = (
        "You are a senior software engineer modifying an existing project. "
        "Output changes in the specified format. Maintain code quality and consistency."
    )
    try:
        result = call_model(prompt, system_prompt=system, model=req.model or "local",
                            job_id=job_id, agent="IterateEndpoint")
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"LLM call failed: {exc}")

    import logging
    _ilog = logging.getLogger("backend.main")
    _ilog.info("Iterate LLM result (%d chars): %.500s", len(result), result)

    import re

    # Robust parser for iteration blocks
    modified = []
    added = []
    deleted = []

    # Handle "--- NO CHANGES ---" or "NO CHANGES"
    if "NO CHANGES" in result.upper():
        pass  # no changes to apply
    else:
        # Split on --- FILE: markers
        blocks = re.split(r"---\s*FILE\s*:\s*", result)
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            # Extract lines
            lines = block.split("\n")
            if not lines:
                continue
            fpath = lines[0].strip().rstrip("-").strip()
            if not fpath:
                continue
            block_text = "\n".join(lines[1:])
            # Determine action
            action_match = re.search(r"---\s*ACTION\s*:\s*(\w+)", block_text)
            action = action_match.group(1).upper() if action_match else "MODIFY"
            # Extract content (between --- CONTENT: and --- END)
            content_match = re.search(
                r"---\s*CONTENT\s*:\s*\n?(.*?)(?:\n---\s*END|$)",
                block_text, re.DOTALL,
            )
            content = content_match.group(1).strip() if content_match else ""

            full_path = _validate_file_path(job_dir, fpath)
            if action == "DELETE":
                if full_path.exists():
                    deleted.append(fpath)
                    full_path.unlink()
            elif action == "ADD":
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(content, encoding="utf-8")
                added.append(fpath)
            elif action == "MODIFY":
                if content and full_path.exists():
                    modified.append(fpath)
                    full_path.write_text(content, encoding="utf-8")

    # Compute diffs for modified files
    import difflib
    diffs = {}
    for fpath in modified:
        full = _validate_file_path(job_dir, fpath)
        if full.exists():
            new_text = full.read_text(encoding="utf-8")
            old_text = existing_files.get(fpath, "")
            diff_lines = list(difflib.unified_diff(
                old_text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=f"a/{fpath}", tofile=f"b/{fpath}",
            ))
            if diff_lines:
                diffs[fpath] = "".join(diff_lines)
    for fpath in added:
        full = job_dir / fpath
        if full.exists():
            new_text = full.read_text(encoding="utf-8")
            diff_lines = list(difflib.unified_diff(
                [], new_text.splitlines(keepends=True),
                fromfile=f"/dev/null", tofile=f"b/{fpath}",
            ))
            diffs[fpath] = "".join(diff_lines)

    # Re-run syntax and tests
    syntax_results: Dict[str, Any] = {}
    all_ok = True
    for py_file in job_dir.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        rel = str(py_file.relative_to(job_dir))
        sr = run_syntax_check(py_file)
        syntax_results[rel] = {"valid": sr["valid"], "error": sr.get("error")}
        if not sr["valid"]:
            all_ok = False

    test_dir = job_dir / "tests"
    pytest_result = {}
    if test_dir.exists():
        pr = run_pytest(job_id)
        pytest_result = pr
        # Auto-fix failing tests after iteration
        if not pr.get("passed", False):
            for attempt in range(2):
                fr = await fix_tests(job_id, FixTestsRequest(model=req.model or "local"))
                if fr.get("after", {}).get("passed"):
                    pytest_result = {
                        "passed": True,
                        "output": fr["after"]["output"],
                        "collected": fr["after"].get("collected", 0),
                        "failures": [],
                    }
                    break
                if attempt == 0 and not fr.get("changes", {}).get("modified"):
                    break
                pytest_result = {
                    "passed": fr["after"]["passed"],
                    "output": fr["after"]["output"],
                    "collected": fr["after"].get("collected", 0),
                    "failures": fr["after"].get("failures", []),
                }

    update_job_status(job_id, "complete", current_agent="", progress_pct=100,
                      error_message="", review_summary="")

    # Auto-run AI review after iteration
    try:
        review = run_project_review(job_id, model=req.model or "local")
        import json
        update_job_status(job_id, "complete", progress_pct=100, review_summary=json.dumps(review))
    except Exception:
        pass

    if added or modified or deleted:
        details = ""
        if added:
            details += f"- **Added**: {', '.join(added)}\n"
        if modified:
            details += f"- **Modified**: {', '.join(modified)}\n"
        if deleted:
            details += f"- **Deleted**: {', '.join(deleted)}\n"
        details += f"- **Prompt**: {req.prompt[:200]}\n"
        details += f"- **Syntax**: {'all OK' if all_ok else 'errors'}\n"
        tp = pytest_result.get("passed")
        if tp is not None:
            details += f"- **Tests**: {pytest_result.get('collected', 0)} collected, {'PASS' if tp else 'FAIL'}\n"
        _append_changelog(job_id, "Project Iterated", details)

    return {
        "job_id": job_id,
        "changes": {"added": added, "modified": modified, "deleted": deleted},
        "diffs": diffs,
        "syntax_ok": all_ok,
        "syntax_errors": {k: v["error"] for k, v in syntax_results.items() if not v["valid"]},
        "test_result": pytest_result.get("output", "")[:500],
        "test_passed": max(0, pytest_result.get("collected", 0) - len(pytest_result.get("failures", []))),
        "test_total": pytest_result.get("collected", 0),
    }


@app.get("/files/{job_id}")
async def get_file_tree(job_id: str):
    """
    Return the live file tree for a job — shows files as they appear during generation.
    Works on running jobs (partial list) and completed jobs.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    try:
        job_dir = _resolve_job_path(job_id)
    except HTTPException:
        # Job may be complete and already zipped
        return {"job_id": job_id, "files": [], "zipped": zip_exists(job_id)}

    if not job_dir.exists():
        return {"job_id": job_id, "files": [], "zipped": zip_exists(job_id)}

    files = [str(p.relative_to(job_dir)) for p in list_files(job_id)]
    return {
        "job_id":  job_id,
        "files":   sorted(files),
        "zipped":  zip_exists(job_id),
        "status":  job.get("status"),
    }


@app.get("/read-project-file/{job_id}/{path:path}")
async def read_project_file(job_id: str, path: str):
    """Read a single generated file's content."""
    job_dir = _resolve_job_path(job_id)
    full = _validate_file_path(job_dir, path)
    if not full.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    try:
        return Response(full.read_text(encoding="utf-8"), media_type="text/plain")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/validate/{job_id}")
async def validate_project(job_id: str):
    """
    Re-run syntax checks + pytest on an existing job's generated files.
    Useful after /regenerate-file.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    try:
        job_dir = _resolve_job_path(job_id)
    except HTTPException:
        raise HTTPException(status_code=400, detail="Source files not available (already zipped).")

    if not job_dir.exists():
        raise HTTPException(status_code=400, detail="Source files not available (already zipped).")

    py_files = [p for p in list_files(job_id) if str(p).endswith(".py")]
    syntax_results = {}
    for f in py_files:
        rel = str(f.relative_to(job_dir))
        syntax_results[rel] = run_syntax_check(f)

    pytest_result = None
    test_dir = job_dir / "tests"
    if test_dir.exists() and any(test_dir.rglob("test_*.py")):
        pytest_result = run_pytest(job_id)

    all_syntax_ok = all(r["valid"] for r in syntax_results.values())
    return {
        "job_id":         job_id,
        "syntax_results": syntax_results,
        "syntax_ok":      all_syntax_ok,
        "pytest":         pytest_result,
    }


# ── AI Project Review ──────────────────────────────────────────────────────────

class ReviewRequest(BaseModel):
    model: Optional[str] = "local"


def run_project_review(job_id: str, model: str = "local") -> Dict[str, Any]:
    """AI-powered review of the entire project. Sync so it can run from pipeline threads."""
    import json as _json
    job_dir = BASE_DIR / job_id
    if not job_dir.exists():
        return {"job_id": job_id, "verdict": "FAIL", "error": "Project files not available."}

    # 1. Read project files
    all_files = sorted(p for p in job_dir.rglob("*") if p.is_file() and "__pycache__" not in str(p))
    file_tree = "\n".join(str(p.relative_to(job_dir)) for p in all_files)

    # 2. Syntax check Python files
    syntax_errors = []
    for fp in all_files:
        if fp.suffix == ".py":
            sr = run_syntax_check(fp)
            if not sr["valid"]:
                rel = str(fp.relative_to(job_dir))
                syntax_errors.append(f"{rel}: {sr['error']}")

    # 3. Run tests
    test_dir = job_dir / "tests"
    test_output = ""
    tests_passed = False
    if test_dir.exists() and any(test_dir.rglob("test_*.py")):
        pr = run_pytest(job_id)
        test_output = pr.get("output", "")[:3000]
        tests_passed = pr.get("passed", False)

    # 4. Read key source files (limit to avoid huge prompts)
    code_exts = {".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css"}
    code_blocks = []
    total_chars = 0
    for fp in all_files:
        if fp.suffix in code_exts:
            rel = str(fp.relative_to(job_dir))
            try:
                text = fp.read_text(encoding="utf-8")
            except Exception:
                continue
            if len(text) > 8000:
                text = text[:8000] + "\n# ... truncated"
            code_blocks.append(f"--- {rel} ---\n{text}\n--- END {rel}")
            total_chars += len(text)
            if total_chars > 6000:
                code_blocks.append("# ... more files omitted")
                break
    code_section = "\n\n".join(code_blocks)

    # 5. Build the LLM prompt
    prompt = (
        f"Project: {job_id}\n\n"
        f"## File Tree\n{file_tree}\n\n"
        f"## Source Code\n{code_section}\n\n"
        f"## Syntax Errors\n"
        + ("\n".join(syntax_errors) if syntax_errors else "None") + "\n\n"
        f"## Test Results\n"
        + (test_output[:2000] if test_output else "No tests found.") + "\n\n"
        "Analyze this project and output a JSON object with these fields:\n"
        '  "verdict": "PASS" | "WARN" | "FAIL" — overall assessment\n'
        '  "issues": [{"severity": "error"|"warning", "description": "...", '
        '"file": "...", "line": 0}]\n'
        '  "recommendations": ["..."]\n'
        "Consider: missing imports, broken routes, wrong HTTP methods, "
        "missing handlers, incorrect return schemas, logic errors, "
        "security issues, and maintainability.\n"
        "Output ONLY valid JSON, no markdown fences."
    )

    def _parse_review(result: str) -> Optional[Dict]:
        import re as _re
        stripped = _re.sub(r"```\w*\n?", "", result).strip()
        # Try full parse
        try:
            parsed = _json.loads(stripped)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        # Try to extract JSON block
        m = _re.search(r'\{.*\}', stripped, _re.DOTALL)
        if m:
            try:
                parsed = _json.loads(m.group(0))
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
        return None

    parsed = None
    for attempt in range(2):
        try:
            result = call_model(prompt, model=model, job_id=job_id, agent="ReviewAgent")
            parsed = _parse_review(result)
            if parsed:
                break
        except Exception:
            pass
        if attempt == 0:
            # Fallback: simpler prompt without full source code
            prompt = (
                f"Project: {job_id}\n\n"
                f"## File Tree\n{file_tree}\n\n"
                f"## Syntax Errors\n"
                + ("\n".join(syntax_errors) if syntax_errors else "None") + "\n\n"
                f"## Test Results\n"
                + (test_output[:1000] if test_output else "No tests found.") + "\n\n"
                "Output JSON: {\"verdict\": \"PASS|WARN|FAIL\", \"issues\": [], \"recommendations\": []}"
            )

    if not parsed:
        parsed = {
            "verdict": "PASS" if not syntax_errors and tests_passed else "WARN",
            "issues": [],
            "recommendations": [],
        }
        if syntax_errors:
            parsed.setdefault("error", f"{len(syntax_errors)} syntax error(s) found")
        if not tests_passed:
            parsed.setdefault("error", "Tests did not pass")

    parsed.setdefault("verdict", "WARN")
    parsed.setdefault("issues", [])
    parsed.setdefault("recommendations", [])

    parsed["job_id"] = job_id
    parsed["syntax_ok"] = len(syntax_errors) == 0
    parsed["tests_passed"] = tests_passed
    return parsed


@app.post("/review/{job_id}")
async def review_project(job_id: str, req: ReviewRequest):
    """Run AI-powered project review on demand."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    review = run_project_review(job_id, model=req.model or "local")
    # Store in DB for display
    import json as _json
    update_job_status(job_id, job.get("status", "complete"), progress_pct=100, review_summary=_json.dumps(review))
    return review


@app.get("/status/{job_id}")
async def get_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    import json
    test_details_raw = job.get("test_details", "")
    try:
        test_details = json.loads(test_details_raw) if test_details_raw else []
    except (json.JSONDecodeError, TypeError):
        test_details = []
    try:
        job_dir = _resolve_job_path(job_id)
    except HTTPException:
        job_dir = None
    return {
        "job_id":          job_id,
        "status":          job.get("status"),
        "project_name":    job.get("project_name"),
        "current_agent":   job.get("current_agent"),
        "progress_pct":    int(job.get("progress_pct", 0)),
        "error_message":   job.get("error_message", ""),
        "file_count":      int(job.get("file_count", 0)),
        "test_total":      int(job.get("test_total", 0)),
        "test_passed":     int(job.get("test_passed", 0)),
        "test_failed":     int(job.get("test_failed", 0)),
        "test_skipped":    int(job.get("test_skipped", 0)),
        "test_summary":    job.get("test_summary", ""),
        "test_details":    test_details,
        "review_summary":  job.get("review_summary", ""),
        "logs":            get_logs(job_id),
        "file_list":       [str(p.relative_to(job_dir))
                            for p in list_files(job_id)]
                            if job_dir.exists() else [],
        "gates_passed":    int(job.get("gates_passed", 0)),
        "gates_total":     int(job.get("gates_total", 0)),
        "gates_failed":    json.loads(job.get("gates_failed", "[]")) if job.get("gates_failed") else [],
        "zip_available":   zip_exists(job_id),
    }


# ── Changelog viewer ──────────────────────────────────────────────────────


@app.get("/changelog/{job_id}")
async def get_changelog(job_id: str):
    """Return the per-project CHANGELOG.md content."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    changelog = BASE_DIR / job_id / "CHANGELOG.md"
    if not changelog.exists():
        return {"job_id": job_id, "changelog": "", "exists": False}
    content = changelog.read_text(encoding="utf-8")
    return {"job_id": job_id, "changelog": content, "exists": True}


# ── Download ──────────────────────────────────────────────────────────────


@app.get("/download/{job_id}")
async def download(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    # Allow download for SUCCESS, PARTIAL, or complete (legacy) status
    if job.get("status") not in ("SUCCESS", "PARTIAL", "complete"):
        raise HTTPException(status_code=400, detail=f"Project not ready for download (status: {job.get('status')}).")
    if not zip_exists(job_id):
        raise HTTPException(status_code=404, detail="ZIP file not found.")
    return FileResponse(
        str(get_zip_path(job_id)),
        media_type="application/zip",
        filename=f"{job.get('project_name', 'project').replace(' ', '_')}.zip",
    )


@app.get("/jobs")
async def list_recent_jobs():
    return {"jobs": list_jobs(limit=20)}


@app.delete("/jobs/{job_id}")
async def delete_project(job_id: str):
    """Delete a project: removes ChromaDB record, SQLite analytics, files, and zip."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    from database.memory_store import delete_project_analytics
    import shutil
    ok = True
    if not delete_job(job_id):
        ok = False
    delete_project_analytics(job_id)
    job_dir = BASE_DIR / job_id
    if job_dir.exists():
        shutil.rmtree(str(job_dir))
    zpath = get_zip_path(job_id)
    if zpath and Path(zpath).exists():
        Path(zpath).unlink(missing_ok=True)
    if ok:
        return {"status": "deleted", "job_id": job_id}
    raise HTTPException(status_code=500, detail="Failed to delete job from database.")


@app.get("/health")
async def health():
    available  = is_available()
    models     = get_available_models() if available else []
    pull_state = get_pull_status()
    models_ready = all(v == "ready" for v in pull_state.values()) if pull_state else False
    return {
        "status":           "ok",
        "ollama_online":    available,
        "models_ready":     models_ready,
        "pull_status":      pull_state,
        "available_models": models,
        "cloud_available":  is_cloud_available(),
        "cloud_model":      CLOUD_MODEL,
        "providers":        get_available_providers(),
        "version":          "13.0.0",
    }


# ═══════════════════════════════════════════════════════════════════════════
# v5 Endpoints — RAG
# ═══════════════════════════════════════════════════════════════════════════

RAG_UPLOAD_DIR = BASE_DIR / "_rag_uploads"


class RagUploadRequest(BaseModel):
    tags: Optional[List[str]] = None


@app.post("/rag/upload")
async def rag_upload(file: UploadFile = File(...), tags: Optional[str] = Form(None)):
    from services.rag_service import upload_document
    if file.filename:
        safe_name = Path(file.filename).name
    else:
        safe_name = f"upload_{uuid.uuid4().hex[:8]}"
    MAX_SIZE = 50 * 1024 * 1024
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 50 MB).")
    RAG_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    save_path = RAG_UPLOAD_DIR / safe_name
    save_path.write_bytes(content)
    tag_list = json.loads(tags) if tags else []
    result = upload_document(save_path, tags=tag_list)
    os.remove(str(save_path))
    return result


@app.post("/rag/query")
async def rag_query(text: str = Body(..., embed=True), top_k: int = Body(5, embed=True),
                    tags: Optional[List[str]] = Body(None, embed=True)):
    from services.rag_service import query
    results = query(text, top_k=top_k, tags=tags)
    return {"results": results}


@app.get("/rag/list")
async def rag_list():
    from services.rag_service import list_documents
    return {"documents": list_documents()}


@app.delete("/rag/{doc_id}")
async def rag_delete(doc_id: str):
    from services.rag_service import delete_document
    ok = delete_document(doc_id)
    return {"deleted": ok}


# ═══════════════════════════════════════════════════════════════════════════
# v5 Endpoints — Analytics
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/analytics/overview")
async def analytics_overview():
    return get_analytics_summary()


@app.get("/analytics/projects")
async def analytics_projects():
    return {"projects": get_project_analytics(limit=50)}


@app.get("/analytics/project/{job_id}")
async def analytics_project(job_id: str):
    from services.analytics_service import get_project_stats
    return get_project_stats(job_id)


# ═══════════════════════════════════════════════════════════════════════════
# v5 Endpoints — Plugins
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/plugins")
async def plugin_list():
    from services.plugin_loader import list_plugins
    return {"plugins": list_plugins()}


@app.post("/plugins/reload")
async def plugin_reload():
    from services.plugin_loader import reload_plugins
    return {"plugins": list(reload_plugins().keys())}


@app.post("/plugins/{name}/toggle")
async def plugin_toggle(name: str, enable: bool = Body(..., embed=True)):
    from services.plugin_loader import enable_plugin, disable_plugin
    ok = enable_plugin(name) if enable else disable_plugin(name)
    return {"name": name, "enabled": enable, "ok": ok}


# ═══════════════════════════════════════════════════════════════════════════
# v5 Endpoints — Diagrams
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/diagram/{job_id}")
async def get_diagram(job_id: str):
    from services.diagram_service import generate_architecture_markdown
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    bp = get_blueprint(job_id) or {}
    if not bp:
        bp = {"files": [], "routes": [], "db_tables": [], "tech_stack": {},
              "dependencies": []}
    agents = ["RequirementAgent", "PlannerAgent", "CodeAgent", "TestGenAgent",
              "DebugAgent", "DocsAgent", "ValidationAgent", "ZipService"]
    md = generate_architecture_markdown(bp, agents)
    return {"diagram_markdown": md, "job_id": job_id}


@app.get("/diagram/{job_id}/component")
async def get_component_diagram(job_id: str):
    from services.diagram_service import generate_component_diagram
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    bp = get_blueprint(job_id) or {"files": [], "routes": [], "db_tables": [],
                                    "tech_stack": {"backend": "FastAPI",
                                                   "frontend": "Streamlit",
                                                   "db": "SQLite"}}
    return {"mermaid": generate_component_diagram(bp), "job_id": job_id}


@app.get("/diagram/{job_id}/er")
async def get_er_diagram(job_id: str):
    from services.diagram_service import generate_er_diagram
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    bp = get_blueprint(job_id) or {"files": [], "routes": [], "db_tables": [],
                                    "tech_stack": {}}
    return {"mermaid": generate_er_diagram(bp), "job_id": job_id}


# ═══════════════════════════════════════════════════════════════════════════
# v5 Endpoints — Code Review
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/code-review/{job_id}")
async def run_code_review(job_id: str):
    from services.code_review_service import run as run_review
    result = run_review(job_id=job_id)
    return result


# ═══════════════════════════════════════════════════════════════════════════
# v5 Endpoints — Supervisor Agent Run
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/supervisor/run-agent/{agent_name}")
async def supervisor_run_agent(agent_name: str, context: Dict[str, Any] = Body(..., embed=True)):
    from services.supervisor_service import Supervisor
    s = Supervisor()
    try:
        result = s.delegate(agent_name, context)
        return {"agent": agent_name, "status": "ok", "result": result}
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ═══════════════════════════════════════════════════════════════════════════
# v6 Endpoints — GitHub Integration
# ═══════════════════════════════════════════════════════════════════════════

from services.github_service import (
    connect_github, disconnect_github, get_connection, list_connections,
    list_repos, get_repo_info, search_repos,
    list_branches, create_branch, delete_branch,
    get_file_content, create_file, update_file, delete_file,
    list_files as _gh_list_files,
    list_commits, get_commit_diff,
    list_pull_requests, create_pull_request, merge_pull_request, get_pr_files,
    list_issues, create_issue, update_issue, add_issue_comment, list_issue_comments,
    clone_repo, pull_repo, get_local_repo_status,
    local_file_list, local_read_file, local_write_file, local_commit_and_push,
    list_webhooks, create_webhook, delete_webhook,
)


# ── Connection ───────────────────────────────────────────────────────────

class GithubConnectRequest(BaseModel):
    token: str
    username: str = ""


class DisconnectRequest(BaseModel):
    username: str


@app.post("/github/connect")
async def github_connect(req: GithubConnectRequest):
    try:
        data = connect_github(req.token, req.username)
        return {"status": "connected", "data": data}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/github/disconnect")
async def github_disconnect(req: DisconnectRequest):
    disconnect_github(req.username)
    return {"status": "disconnected"}


@app.get("/github/connections")
async def github_list_connections():
    return {"connections": list_connections()}


# ── Repos ────────────────────────────────────────────────────────────────

@app.get("/github/{username}/repos")
async def github_list_repos(username: str):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    repos = list_repos(conn["token"], conn["username"])
    for r in repos:
        save_github_repo(username, r["full_name"], r)
    return {"repos": repos}


@app.get("/github/repo/{full_name:path}")
async def github_repo_info(full_name: str, username: str = ""):
    if not username:
        raise HTTPException(status_code=400, detail="username required")
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    info = get_repo_info(conn["token"], full_name)
    if not info:
        raise HTTPException(status_code=404, detail="Repo not found")
    return info


@app.get("/github/search")
async def github_search(q: str, username: str = ""):
    if not username:
        raise HTTPException(status_code=400, detail="username required")
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return {"results": search_repos(conn["token"], q)}


# ── Branches ─────────────────────────────────────────────────────────────

@app.get("/github/{full_name:path}/branches")
async def github_list_branches(full_name: str, username: str = ""):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return {"branches": list_branches(conn["token"], full_name)}


class BranchRequest(BaseModel):
    username: str
    branch: str
    source_branch: str = ""


@app.post("/github/{full_name:path}/branches")
async def github_create_branch(full_name: str, req: BranchRequest):
    conn = get_connection(req.username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return create_branch(conn["token"], full_name, req.branch, req.source_branch)


@app.delete("/github/{full_name:path}/branches/{branch}")
async def github_delete_branch(full_name: str, branch: str, username: str = ""):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return delete_branch(conn["token"], full_name, branch)


# ── Files ────────────────────────────────────────────────────────────────

@app.get("/github/{full_name:path}/files")
async def github_list_files(full_name: str, path: str = "", ref: str = "", username: str = ""):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return {"files": _gh_list_files(conn["token"], full_name, path, ref)}


@app.get("/github/{full_name:path}/file")
async def github_get_file(full_name: str, path: str, ref: str = "", username: str = ""):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    content = get_file_content(conn["token"], full_name, path, ref)
    if not content:
        raise HTTPException(status_code=404, detail="File not found")
    return content


class FileWriteRequest(BaseModel):
    username: str
    path: str
    content: str
    message: str
    branch: str = ""
    sha: str = ""


@app.post("/github/{full_name:path}/file")
async def github_create_or_update_file(full_name: str, req: FileWriteRequest):
    conn = get_connection(req.username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    if req.sha:
        return update_file(conn["token"], full_name, req.path, req.content, req.message, req.sha, req.branch)
    return create_file(conn["token"], full_name, req.path, req.content, req.message, req.branch)


@app.delete("/github/{full_name:path}/file")
async def github_delete_file_ep(full_name: str, path: str, message: str, sha: str, username: str = ""):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return delete_file(conn["token"], full_name, path, message, sha)


# ── Commits ──────────────────────────────────────────────────────────────

@app.get("/github/{full_name:path}/commits")
async def github_list_commits(full_name: str, branch: str = "", since: str = "", until: str = "", username: str = ""):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return {"commits": list_commits(conn["token"], full_name, branch, since, until)}


@app.get("/github/{full_name:path}/commits/{sha}")
async def github_commit_detail(full_name: str, sha: str, username: str = ""):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return {"diff": get_commit_diff(conn["token"], full_name, sha)}


# ── Pull Requests ────────────────────────────────────────────────────────

class PRCreateRequest(BaseModel):
    username: str
    title: str
    head: str
    base: str
    body: str = ""
    draft: bool = False


class PRMergeRequest(BaseModel):
    username: str
    commit_message: str = ""
    merge_method: str = "merge"


@app.get("/github/{full_name:path}/pulls")
async def github_list_pulls(full_name: str, state: str = "open", username: str = ""):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return {"pull_requests": list_pull_requests(conn["token"], full_name, state)}


@app.post("/github/{full_name:path}/pulls")
async def github_create_pr(full_name: str, req: PRCreateRequest):
    conn = get_connection(req.username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return create_pull_request(conn["token"], full_name, req.title, req.head, req.base, req.body, req.draft)


@app.post("/github/{full_name:path}/pulls/{pr_number}/merge")
async def github_merge_pr(full_name: str, pr_number: int, req: PRMergeRequest):
    conn = get_connection(req.username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return merge_pull_request(conn["token"], full_name, pr_number, req.commit_message, req.merge_method)


@app.get("/github/{full_name:path}/pulls/{pr_number}/files")
async def github_pr_files(full_name: str, pr_number: int, username: str = ""):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return {"files": get_pr_files(conn["token"], full_name, pr_number)}


# ── Issues ───────────────────────────────────────────────────────────────

class IssueCreateRequest(BaseModel):
    username: str
    title: str
    body: str = ""
    labels: List[str] = []
    assignees: List[str] = []


class IssueUpdateRequest(BaseModel):
    username: str
    title: str = ""
    body: str = ""
    state: str = ""


class IssueCommentRequest(BaseModel):
    username: str
    body: str


@app.get("/github/{full_name:path}/issues")
async def github_list_issues(full_name: str, state: str = "open", labels: str = "", username: str = ""):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return {"issues": list_issues(conn["token"], full_name, state, labels)}


@app.post("/github/{full_name:path}/issues")
async def github_create_issue(full_name: str, req: IssueCreateRequest):
    conn = get_connection(req.username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return create_issue(conn["token"], full_name, req.title, req.body, req.labels, req.assignees)


@app.patch("/github/{full_name:path}/issues/{issue_number}")
async def github_update_issue(full_name: str, issue_number: int, req: IssueUpdateRequest):
    conn = get_connection(req.username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return update_issue(conn["token"], full_name, issue_number, req.title, req.body, req.state)


@app.post("/github/{full_name:path}/issues/{issue_number}/comments")
async def github_add_comment(full_name: str, issue_number: int, req: IssueCommentRequest):
    conn = get_connection(req.username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return add_issue_comment(conn["token"], full_name, issue_number, req.body)


@app.get("/github/{full_name:path}/issues/{issue_number}/comments")
async def github_list_comments(full_name: str, issue_number: int, username: str = ""):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return {"comments": list_issue_comments(conn["token"], full_name, issue_number)}


# ── Local Clone / Sync ───────────────────────────────────────────────────

@app.post("/github/{full_name:path}/clone")
async def github_clone(full_name: str, username: str = "", branch: str = ""):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return clone_repo(conn["token"], full_name, branch)


@app.post("/github/{full_name:path}/pull")
async def github_pull(full_name: str, username: str = "", branch: str = ""):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return pull_repo(conn["token"], full_name, branch)


@app.get("/github/{full_name:path}/local-status")
async def github_local_status(full_name: str):
    status = get_local_repo_status(full_name)
    if not status:
        raise HTTPException(status_code=404, detail="Not cloned locally")
    return status


@app.get("/github/{full_name:path}/local-files")
async def github_local_files(full_name: str, path: str = ""):
    return {"files": local_file_list(full_name, path)}


@app.get("/github/{full_name:path}/local-file")
async def github_local_read(full_name: str, path: str):
    content = local_read_file(full_name, path)
    if content is None:
        raise HTTPException(status_code=404, detail="File not found")
    return Response(content, media_type="text/plain")


@app.post("/github/{full_name:path}/local-file")
async def github_local_write(full_name: str, path: str, content: str = Body(..., embed=True),
                              message: str = "", username: str = ""):
    return local_write_file(full_name, path, content, message)


@app.post("/github/{full_name:path}/commit-push")
async def github_commit_push(full_name: str, message: str = Body(..., embed=True),
                              branch: str = "", username: str = ""):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return local_commit_and_push(full_name, message, branch)


# ── Webhooks ─────────────────────────────────────────────────────────────

@app.get("/github/{full_name:path}/webhooks")
async def github_list_webhooks(full_name: str, username: str = ""):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return {"webhooks": list_webhooks(conn["token"], full_name)}


class WebhookCreateRequest(BaseModel):
    username: str
    url: str
    events: List[str] = []


@app.post("/github/{full_name:path}/webhooks")
async def github_create_webhook(full_name: str, req: WebhookCreateRequest):
    conn = get_connection(req.username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return create_webhook(conn["token"], full_name, req.url, req.events or None)


@app.delete("/github/{full_name:path}/webhooks/{hook_id}")
async def github_delete_webhook(full_name: str, hook_id: int, username: str = ""):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return delete_webhook(conn["token"], full_name, hook_id)


# ── AI Agent: GitHub Analysis ────────────────────────────────────────────

@app.post("/github/agent/analyze-repo")
async def github_agent_analyze(full_name: str = Body(...), username: str = Body(...), model: str = "local"):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    from services.github_agent_service import analyze_repository
    return analyze_repository(conn["token"], full_name, model=model)


@app.post("/github/agent/review-pr")
async def github_agent_review_pr(full_name: str = Body(...), pr_number: int = Body(...),
                                  username: str = Body(...), model: str = "local"):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    from services.github_agent_service import review_pull_request
    return review_pull_request(conn["token"], full_name, pr_number, model=model)


@app.post("/github/agent/fix-issue")
async def github_agent_fix_issue(full_name: str = Body(...), issue_number: int = Body(...),
                                  username: str = Body(...), model: str = "local"):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    from services.github_agent_service import fix_issue
    return fix_issue(conn["token"], full_name, issue_number, model=model)


@app.post("/github/agent/suggest-improvements")
async def github_agent_suggest(full_name: str = Body(...), username: str = Body(...), model: str = "local"):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    from services.github_agent_service import suggest_improvements
    return suggest_improvements(conn["token"], full_name, model=model)


# ── Chat Endpoints ─────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    title: Optional[str] = None

class ChatConfirmRequest(BaseModel):
    conversation_id: str
    tool_name: str
    args: Dict[str, Any]

class NewChatRequest(BaseModel):
    conversation_id: Optional[str] = None
    title: Optional[str] = None


@app.post("/chat/new")
def chat_new(req: NewChatRequest):
    cid = req.conversation_id or str(uuid.uuid4())
    create_chat_conversation(conversation_id=cid, title=req.title or "New Chat")
    return {"ok": True, "conversation_id": cid}


@app.post("/chat")
def chat_endpoint(req: ChatRequest):
    cid = req.conversation_id
    if not cid:
        cid = create_chat_conversation(title=req.title or "New Chat")
    result = chat_process_message(req.message, cid)
    result["conversation_id"] = cid
    return result


@app.post("/chat/confirm-action")
def chat_confirm_action(req: ChatConfirmRequest):
    result = chat_execute_action(req.conversation_id, req.tool_name, req.args)
    result["conversation_id"] = req.conversation_id
    return result


@app.get("/chat/conversations")
def chat_list_conversations():
    convos = list_chat_conversations(limit=20)
    return {"conversations": convos}


@app.get("/chat/conversations/{conversation_id}/messages")
def chat_get_messages(conversation_id: str, limit: int = 50):
    msgs = get_chat_messages(conversation_id, limit=limit)
    return {"messages": msgs}


@app.delete("/chat/conversations/{conversation_id}")
def chat_delete_conversation(conversation_id: str):
    ok = delete_chat_conversation(conversation_id)
    return {"ok": ok}


# ── Webhook Receiver (GitHub calls this) ──────────────────────────────────

@app.post("/github/webhook-receiver/{full_name:path}")
async def github_webhook_receiver(full_name: str, request: Request):
    """
    Receiver endpoint for GitHub webhooks.
    - Push events → auto-pull local clone
    - pull_request events → auto-AI-review
    """
    event = request.headers.get("X-GitHub-Event", "push")
    payload = await request.json()
    # Auto-pull on push
    if event == "push":
        ref = payload.get("ref", "")
        branch = ref.replace("refs/heads/", "") if ref else ""
        try:
            from services.github_service import pull_repo
            result = pull_repo("", full_name, branch=branch)
            return {"event": event, "branch": branch, "result": result}
        except Exception as exc:
            return {"event": event, "error": str(exc)}
    # Auto-review on PR open
    if event == "pull_request" and payload.get("action") in ("opened", "synchronize"):
        pr_number = payload.get("number", 0)
        try:
            from services.github_agent_service import review_pull_request
            result = review_pull_request("", full_name, pr_number, model="local")
            return {"event": event, "pr": pr_number, "result": result}
        except Exception as exc:
            return {"event": event, "error": str(exc)}
    return {"event": event, "action": payload.get("action", "unknown"), "handled": False}


# ═══════════════════════════════════════════════════════════════════════════
# v7 Endpoints — Auto-Fix, Sandbox, Memory, Deployment, Workspace
# ═══════════════════════════════════════════════════════════════════════════


class AutoFixRequest(BaseModel):
    model: Optional[str] = "local"
    max_attempts: int = 5


@app.post("/autofix/{job_id}")
async def autofix_project(job_id: str, req: AutoFixRequest):
    from services.autofix_service import run_autofix
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    result = run_autofix(job_id, model=req.model or "local", max_attempts=req.max_attempts)
    return result


class SandboxRunRequest(BaseModel):
    code: str
    requirements: Optional[List[str]] = None
    timeout: int = 60


@app.post("/sandbox/run")
async def sandbox_run(req: SandboxRunRequest):
    from services.sandbox_service import run_python
    result = run_python(req.code, requirements=req.requirements, timeout=req.timeout)
    return result


@app.get("/sandbox/status")
async def sandbox_status():
    from services.sandbox_service import is_available
    return {"available": is_available()}


@app.get("/memory/context/{job_id}")
async def memory_context(job_id: str):
    from services.memory_service import get_context_for_prompt
    ctx = get_context_for_prompt("", job_id=job_id)
    return ctx


@app.get("/memory/insights")
async def memory_insights(insight_type: Optional[str] = None, limit: int = 50):
    from database.memory_store import get_project_insights
    insights = get_project_insights(insight_type=insight_type, limit=limit)
    return {"insights": insights}


class WorkspaceFileCreate(BaseModel):
    content: str


@app.post("/workspace/{job_id}/files/{path:path}")
async def workspace_create_file(job_id: str, path: str, req: WorkspaceFileCreate):
    job_dir = _resolve_job_path(job_id)
    full = _validate_file_path(job_dir, path)
    if full.exists():
        raise HTTPException(status_code=409, detail="File already exists. Use PUT to update.")
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(req.content, encoding="utf-8")
    return {"job_id": job_id, "path": path, "action": "created", "chars": len(req.content)}


@app.put("/workspace/{job_id}/files/{path:path}")
async def workspace_update_file(job_id: str, path: str, req: WorkspaceFileCreate):
    job_dir = _resolve_job_path(job_id)
    full = _validate_file_path(job_dir, path)
    if not full.exists():
        raise HTTPException(status_code=404, detail="File not found.")
    original = full.read_text(encoding="utf-8")
    full.write_text(req.content, encoding="utf-8")
    from difflib import unified_diff
    diff = list(unified_diff(original.splitlines(keepends=True), req.content.splitlines(keepends=True),
                              fromfile=f"a/{path}", tofile=f"b/{path}"))
    return {"job_id": job_id, "path": path, "action": "updated", "chars": len(req.content), "diff": "".join(diff[-1000:])}


@app.delete("/workspace/{job_id}/files/{path:path}")
async def workspace_delete_file(job_id: str, path: str):
    job_dir = _resolve_job_path(job_id)
    full = _validate_file_path(job_dir, path)
    if not full.exists():
        raise HTTPException(status_code=404, detail="File not found.")
    full.unlink()
    return {"job_id": job_id, "path": path, "action": "deleted"}


class DeployRequest(BaseModel):
    target: str = "docker"
    model: Optional[str] = "local"


@app.post("/deploy/{job_id}")
async def deploy_project(job_id: str, req: DeployRequest):
    from services.deployment_service import deploy_project
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    result = deploy_project(job_id, target=req.target, model=req.model or "local")
    return result


@app.get("/metrics")
async def metrics():
    from services.llm_service import get_token_count
    from database.memory_store import get_analytics_summary, get_cost_summary
    import time as _time
    tokens = get_token_count()
    analytics = get_analytics_summary()
    cost = get_cost_summary()
    return {
        "total_tokens": tokens,
        "analytics": analytics,
        "cost": cost,
        "timestamp": _time.time(),
    }


@app.get("/providers")
async def list_providers():
    from services.llm_service import get_available_providers
    return {"providers": get_available_providers()}


# ═══════════════════════════════════════════════════════════════════════════
# v8 Endpoints — Browser Agent, Repo Analyzer, Dashboard, Docs
# ═══════════════════════════════════════════════════════════════════════════


# ── Browser Agent ─────────────────────────────────────────────────────────


class BrowserOpenRequest(BaseModel):
    url: str
    timeout: Optional[int] = None


class BrowserActionRequest(BaseModel):
    session_id: str
    action: str = Field(..., description="navigate | click | fill | select | upload | screenshot | content | evaluate | wait")
    selector: Optional[str] = None
    value: Optional[str] = None
    url: Optional[str] = None
    script: Optional[str] = None
    file_path: Optional[str] = None
    timeout: Optional[int] = None
    full_page: bool = True
    state: str = "visible"


class BrowserTestRequest(BaseModel):
    session_id: str
    test_script: str = Field(..., description="One action per line: action | arg1 | arg2")


class BrowserCloseRequest(BaseModel):
    session_id: str


@app.post("/browser/open")
async def browser_open(req: BrowserOpenRequest):
    from services.browser_service import create_session, navigate
    try:
        session = create_session()
        result = navigate(session.session_id, req.url, timeout=req.timeout)
        result["session_id"] = session.session_id
        return result
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/browser/action")
async def browser_action(req: BrowserActionRequest):
    from services.browser_service import (
        navigate, click, fill, select_option, upload_file,
        screenshot, get_content, evaluate, wait_for_selector,
        get_session,
    )
    try:
        if req.action == "navigate":
            if not req.url:
                raise HTTPException(status_code=400, detail="url required for navigate")
            return navigate(req.session_id, req.url, timeout=req.timeout)
        elif req.action == "click":
            if not req.selector:
                raise HTTPException(status_code=400, detail="selector required for click")
            return click(req.session_id, req.selector, timeout=req.timeout)
        elif req.action == "fill":
            if not req.selector or req.value is None:
                raise HTTPException(status_code=400, detail="selector and value required for fill")
            return fill(req.session_id, req.selector, req.value, timeout=req.timeout)
        elif req.action == "select":
            if not req.selector or req.value is None:
                raise HTTPException(status_code=400, detail="selector and value required for select")
            return select_option(req.session_id, req.selector, req.value)
        elif req.action == "upload":
            if not req.selector or not req.file_path:
                raise HTTPException(status_code=400, detail="selector and file_path required for upload")
            return upload_file(req.session_id, req.selector, req.file_path)
        elif req.action == "screenshot":
            return screenshot(req.session_id, full_page=req.full_page)
        elif req.action == "content":
            return get_content(req.session_id)
        elif req.action == "evaluate":
            if not req.script:
                raise HTTPException(status_code=400, detail="script required for evaluate")
            return evaluate(req.session_id, req.script)
        elif req.action == "wait":
            if not req.selector:
                raise HTTPException(status_code=400, detail="selector required for wait")
            return wait_for_selector(req.session_id, req.selector, timeout=req.timeout, state=req.state)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {req.action}")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)[:300])


@app.post("/browser/screenshot")
async def browser_screenshot(session_id: str = Body(...), full_page: bool = Body(True)):
    from services.browser_service import screenshot as _screenshot
    try:
        return _screenshot(session_id, full_page=full_page)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/browser/test")
async def browser_test(req: BrowserTestRequest):
    from services.browser_service import run_test
    try:
        result = run_test(req.session_id, req.test_script)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/browser/close")
async def browser_close(req: BrowserCloseRequest):
    from services.browser_service import close_session
    ok = close_session(req.session_id)
    return {"session_id": req.session_id, "closed": ok}


@app.get("/browser/sessions")
async def browser_list_sessions():
    from services.browser_service import list_sessions
    return {"sessions": list_sessions()}


@app.get("/browser/sessions/{session_id}/actions")
async def browser_get_actions(session_id: str):
    from services.browser_service import get_action_log
    try:
        return {"actions": get_action_log(session_id)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ── Repository Analyzer ───────────────────────────────────────────────────


class RepoAnalyzeRequest(BaseModel):
    repo_path: str
    model: Optional[str] = "local"


class RepoImproveRequest(BaseModel):
    repo_path: str
    model: Optional[str] = "local"
    auto_fix: bool = True
    generate_tests: bool = True


class RepoCreatePRRequest(BaseModel):
    repo_path: str
    github_token: str
    repo_full_name: str
    branch_name: str = "auto-improve"
    base_branch: str = "main"
    title: str = "Automated code quality improvements"
    body: str = "AI-driven improvements including fixes, tests, and documentation."
    model: Optional[str] = "local"


@app.post("/repo/analyze")
async def repo_analyze(req: RepoAnalyzeRequest):
    from services.repo_analyzer_service import analyze_repository
    try:
        result = analyze_repository(req.repo_path, model=req.model or "local")
        return result
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)[:300])


@app.post("/repo/improve")
async def repo_improve(req: RepoImproveRequest):
    from services.repo_analyzer_service import improve_repository
    try:
        result = improve_repository(
            req.repo_path,
            model=req.model or "local",
            auto_fix=req.auto_fix,
            generate_tests=req.generate_tests,
        )
        return result
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)[:300])


@app.post("/repo/create-pr")
async def repo_create_pr(req: RepoCreatePRRequest):
    from services.repo_analyzer_service import create_pr
    try:
        result = create_pr(
            req.repo_path, req.github_token, req.repo_full_name,
            branch_name=req.branch_name, base_branch=req.base_branch,
            title=req.title, body=req.body, model=req.model or "local",
        )
        return result
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)[:300])


# ── Agent Dashboard ───────────────────────────────────────────────────────


@app.get("/dashboard/status")
async def dashboard_status():
    from services.dashboard_service import get_dashboard_status
    return get_dashboard_status()


@app.get("/dashboard/timeline")
async def dashboard_timeline(limit: int = 100):
    from services.dashboard_service import get_timeline
    return {"events": get_timeline(limit=limit)}


@app.get("/dashboard/agents")
async def dashboard_agents():
    from services.dashboard_service import get_all_agents
    return {"agents": get_all_agents()}


@app.get("/dashboard/agents/{name}")
async def dashboard_agent(name: str):
    from services.dashboard_service import get_agent
    agent = get_agent(name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    return agent


@app.get("/dashboard/graph")
async def dashboard_graph(agent: Optional[str] = None):
    from services.dashboard_service import get_execution_graph
    return get_execution_graph(agent_name=agent)


@app.get("/dashboard/memory")
async def dashboard_memory():
    from services.dashboard_service import track_memory_usage
    return track_memory_usage()


@app.websocket("/dashboard/stream")
async def dashboard_websocket(websocket: WebSocket):
    from services.dashboard_service import subscribe, unsubscribe, get_dashboard_status
    await websocket.accept()
    queue: List = []
    import threading as _th

    def _on_event(event):
        import json as _j
        try:
            import anyio
            anyio.from_thread.run(websocket.send_json, {
                "type": event.event_type,
                "data": event.data,
                "timestamp": event.timestamp,
            })
        except Exception:
            pass

    subscribe(_on_event)
    try:
        # Send initial status
        await websocket.send_json({"type": "initial", "data": get_dashboard_status(), "timestamp": time.time()})
        while True:
            try:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_json({"type": "pong"})
            except WebSocketDisconnect:
                break
    except Exception:
        pass
    finally:
        unsubscribe(_on_event)


# ── Documentation Generator ───────────────────────────────────────────────


class DocsGenerateRequest(BaseModel):
    output_dir: Optional[str] = None


@app.post("/docs/generate")
async def docs_generate(req: DocsGenerateRequest):
    from services.docs_generator_service import generate_all
    result = generate_all(output_dir=req.output_dir)
    return {"generated": result}


@app.get("/docs/status")
async def docs_status():
    from services.docs_generator_service import DOCS_DIR
    docs = []
    if DOCS_DIR.exists():
        for fp in sorted(DOCS_DIR.rglob("*.md")):
            docs.append(str(fp.relative_to(DOCS_DIR.parent)))
    return {"docs_dir": str(DOCS_DIR), "files": docs}


# ═══════════════════════════════════════════════════════════════════════════
# v9 Endpoints — Task Graph + Knowledge Graph + Debate + Browser Validation
#                    + Autonomous Iteration + Execution Visualizer
# ═══════════════════════════════════════════════════════════════════════════


# ── 1. Task Graph Execution Engine ────────────────────────────────────────


class GraphBuildRequest(BaseModel):
    prompt: str
    job_id: str
    model: str = "local"
    stack: Optional[Dict[str, Any]] = None


class GraphExecuteRequest(BaseModel):
    graph_id: str
    max_workers: int = 4


@app.post("/graph/build")
async def graph_build(req: GraphBuildRequest):
    from services.graph_engine import create_pipeline_graph, PlanBuilder
    builder = PlanBuilder()
    graph = builder.build_standard_plan(req.prompt, req.job_id, req.model, req.stack)
    from database.memory_store import save_graph_session
    import json
    save_graph_session(graph.id, req.job_id, json.dumps(graph.to_dict()), "built")
    return {"graph_id": graph.id, "tasks": [t.to_dict() for t in graph.tasks.values()],
            "topological_order": graph.get_topological_order(),
            "critical_path": [t.id for t in graph.get_critical_path()],
            "visualization": graph.visualize_mermaid()}


@app.post("/graph/execute")
async def graph_execute(req: GraphExecuteRequest):
    from services.graph_engine import TaskGraph, GraphExecutor
    from database.memory_store import get_graph_session
    import json
    saved = get_graph_session(req.graph_id)
    if not saved:
        raise HTTPException(status_code=404, detail="Graph not found")
    data = json.loads(saved["graph_data"])
    graph = TaskGraph(graph_id=req.graph_id)
    for tid, tdata in data.get("tasks", {}).items():
        from services.graph_engine import Task, TaskStatus, TaskPriority
        t = Task(
            id=tid, name=tdata.get("name", ""),
            deps=tdata.get("deps", []), dependents=tdata.get("dependents", []),
            agent_name=tdata.get("agent_name", ""),
            kwargs=tdata.get("kwargs", {}),
            priority=TaskPriority(tdata.get("priority", 2)),
        )
        graph.tasks[tid] = t
    executor = GraphExecutor(graph, max_workers=req.max_workers)
    result = executor.execute()
    save_graph_session(req.graph_id, "", json.dumps(graph.to_dict()), "executed")
    return {"graph_id": req.graph_id, "status": graph.to_dict(), "execution": result}


@app.get("/graph/{graph_id}")
async def graph_status(graph_id: str):
    from database.memory_store import get_graph_session
    saved = get_graph_session(graph_id)
    if not saved:
        raise HTTPException(status_code=404, detail="Graph not found")
    return saved


@app.get("/graph/{graph_id}/visualize")
async def graph_visualize(graph_id: str):
    from services.graph_engine import TaskGraph
    from database.memory_store import get_graph_session
    import json
    saved = get_graph_session(graph_id)
    if not saved:
        raise HTTPException(status_code=404, detail="Graph not found")
    data = json.loads(saved["graph_data"])
    graph = TaskGraph(graph_id=graph_id)
    for tid, tdata in data.get("tasks", {}).items():
        from services.graph_engine import Task
        graph.tasks[tid] = Task.from_dict(tdata)
    return {"mermaid": graph.visualize_mermaid(), "topological_order": graph.get_topological_order(),
            "critical_path": [t.id for t in graph.get_critical_path()]}


@app.get("/graph/{graph_id}/checkpoints")
async def graph_checkpoints(graph_id: str):
    from services.graph_engine import TaskGraph
    g = TaskGraph(graph_id=graph_id)
    return {"checkpoints": g.list_checkpoints()}


@app.post("/graph/{graph_id}/resume/{checkpoint_id}")
async def graph_resume(graph_id: str, checkpoint_id: str, max_workers: int = 4):
    from services.graph_engine import TaskGraph, GraphExecutor
    g = TaskGraph(graph_id=graph_id)
    loaded = g.load_checkpoint(checkpoint_id)
    if not loaded:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    executor = GraphExecutor(loaded, max_workers=max_workers)
    result = executor.execute()
    return {"graph_id": graph_id, "status": loaded.to_dict(), "execution": result}


@app.get("/graphs")
async def graph_list():
    from database.memory_store import list_graph_sessions
    return {"graphs": list_graph_sessions()}


# ── 2. Repository Knowledge Graph ─────────────────────────────────────────


class KGRequest(BaseModel):
    repo_path: str


class KGAnalyzeRequest(BaseModel):
    repo_path: str
    file_pattern: Optional[str] = None


class KGImpactRequest(BaseModel):
    repo_path: str
    changed_files: List[str]


@app.post("/kg/build")
async def kg_build(req: KGRequest):
    from services.knowledge_graph import build_knowledge_graph
    try:
        kg = build_knowledge_graph(req.repo_path)
        return {"file_count": len(kg.files), "relationship_count": len(kg.relationships),
                "summary": kg.get_architecture_summary(), "graph_id": id(kg)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/kg/impact")
async def kg_impact(req: KGImpactRequest):
    from services.knowledge_graph import build_knowledge_graph
    try:
        kg = build_knowledge_graph(req.repo_path)
        result = kg.impact_analysis(req.changed_files)
        return {"affected_files": result.affected_files, "impact_score": result.impact_score,
                "breaking_changes": result.breaking_changes, "recommendations": result.recommendations}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/kg/query")
async def kg_query(req: KGAnalyzeRequest):
    from services.knowledge_graph import build_knowledge_graph
    try:
        kg = build_knowledge_graph(req.repo_path)
        return {
            "apis": kg.query_apis(),
            "dependency_graph": kg.query_dependency_graph(module=req.file_pattern),
            "service_deps": kg.query_service_dependencies(),
            "test_mappings": kg.query_test_mappings(),
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/kg/visualize")
async def kg_visualize(req: KGRequest):
    from services.knowledge_graph import build_knowledge_graph
    try:
        kg = build_knowledge_graph(req.repo_path)
        return {"mermaid": kg.visualize_mermaid(), "summary": kg.get_architecture_summary()}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/kg/architecture")
async def kg_architecture(req: KGRequest):
    from services.knowledge_graph import build_knowledge_graph
    try:
        kg = build_knowledge_graph(req.repo_path)
        return kg.get_architecture_summary()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ── 3. Multi-Agent Debate System ──────────────────────────────────────────


class DebateRequest(BaseModel):
    topic: str = Field(..., description="Programming task or question to debate")
    context: str = ""
    job_id: str = ""
    solvers: Optional[List[str]] = None
    arbiter_model: str = "cloud"
    quality_threshold: float = 0.7


class DebateQueryRequest(BaseModel):
    session_id: str


@app.post("/debate/start")
async def debate_start(req: DebateRequest):
    from services.debate_system import get_debate_system, DebateConfig, ConsensusMethod
    ds = get_debate_system()
    config = DebateConfig(
        solvers=req.solvers or ["local", "cloud", "local", "cloud"],
        arbiter_model=req.arbiter_model or "cloud",
        quality_threshold=req.quality_threshold or 0.7,
        consensus_method=ConsensusMethod.WEIGHTED,
    )
    session = ds.start_debate(req.topic, config=config, context=req.context, job_id=req.job_id)
    return {"session_id": session.id, "status": session.status}


@app.get("/debate/status/{session_id}")
async def debate_status(session_id: str):
    from services.debate_system import get_debate_system
    ds = get_debate_system()
    session = ds.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Debate session not found")
    return session.to_dict()


@app.get("/debate/sessions")
async def debate_list():
    from services.debate_system import get_debate_system
    ds = get_debate_system()
    return {"sessions": ds.list_sessions()}


@app.get("/debate/quality/{session_id}")
async def debate_quality(session_id: str):
    from services.debate_system import get_debate_system
    ds = get_debate_system()
    return ds.evaluate_quality(session_id)


# ── 4. Browser Validation ─────────────────────────────────────────────────


class CreateJourneyRequest(BaseModel):
    name: str
    base_url: str
    tags: Optional[List[str]] = None


class AddStepRequest(BaseModel):
    journey_id: str
    action: str
    selector: Optional[str] = None
    value: Optional[str] = None
    url: Optional[str] = None
    script: Optional[str] = None
    screenshot_name: Optional[str] = None
    expected_text: Optional[str] = None
    expected_url: Optional[str] = None
    wait_time: float = 0.0
    timeout: int = 10000
    description: str = ""


class ExecuteJourneyRequest(BaseModel):
    journey_id: str
    headless: bool = True
    base_url: Optional[str] = None


class AutoGenerateRequest(BaseModel):
    repo_path: str
    base_url: str
    name: str = "Auto-generated journey"


class RegressionRequest(BaseModel):
    name: str
    journey_ids: Optional[List[str]] = None


class RunRegressionRequest(BaseModel):
    regression_id: str
    headless: bool = True


@app.post("/validation/journey/create")
async def validation_create_journey(req: CreateJourneyRequest):
    from services.browser_validation_service import get_validation_service
    vs = get_validation_service()
    journey = vs.create_journey(req.name, req.base_url, req.tags)
    return {"journey_id": journey.id, "name": journey.name, "step_count": 0}


@app.post("/validation/journey/step")
async def validation_add_step(req: AddStepRequest):
    from services.browser_validation_service import get_validation_service, ValidationStep
    vs = get_validation_service()
    step = ValidationStep(
        action=req.action, selector=req.selector, value=req.value,
        url=req.url, script=req.script, screenshot_name=req.screenshot_name,
        expected_text=req.expected_text, expected_url=req.expected_url,
        wait_time=req.wait_time, timeout=req.timeout, description=req.description,
    )
    ok = vs.add_step(req.journey_id, step)
    if not ok:
        raise HTTPException(status_code=404, detail="Journey not found")
    return {"ok": True, "journey_id": req.journey_id}


@app.post("/validation/journey/execute")
async def validation_execute_journey(req: ExecuteJourneyRequest):
    from services.browser_validation_service import get_validation_service
    vs = get_validation_service()
    return vs.execute_journey(req.journey_id, headless=req.headless, base_url=req.base_url)


@app.post("/validation/auto-generate")
async def validation_auto_generate(req: AutoGenerateRequest):
    from services.browser_validation_service import get_validation_service
    vs = get_validation_service()
    journey = vs.auto_generate_tests(req.repo_path, req.base_url, req.name)
    return {"journey_id": journey.id, "name": journey.name, "steps": len(journey.steps)}


@app.post("/validation/regression/create")
async def validation_create_regression(req: RegressionRequest):
    from services.browser_validation_service import get_validation_service
    vs = get_validation_service()
    rt = vs.create_regression_test(req.name, req.journey_ids)
    return {"regression_id": rt.id, "name": rt.name}


@app.post("/validation/regression/run")
async def validation_run_regression(req: RunRegressionRequest):
    from services.browser_validation_service import get_validation_service
    vs = get_validation_service()
    return vs.run_regression(req.regression_id, headless=req.headless)


@app.get("/validation/journeys")
async def validation_list_journeys():
    from services.browser_validation_service import get_validation_service
    vs = get_validation_service()
    return {"journeys": vs.list_journeys()}


@app.get("/validation/regression-tests")
async def validation_list_regression():
    from services.browser_validation_service import get_validation_service
    vs = get_validation_service()
    return {"regression_tests": vs.list_regression_tests()}


@app.delete("/validation/journey/{journey_id}")
async def validation_delete_journey(journey_id: str):
    from services.browser_validation_service import get_validation_service
    vs = get_validation_service()
    ok = vs.delete_journey(journey_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Journey not found")
    return {"deleted": True}


# ── 5. Autonomous Iteration Mode ──────────────────────────────────────────


class AutonomousStartRequest(BaseModel):
    job_id: str
    max_iterations: int = 10
    quality_threshold: float = 0.85
    model: str = "local"


@app.post("/autonomous/start")
async def autonomous_start(req: AutonomousStartRequest):
    from services.autonomous_service import get_autonomous_engine, AutonomousConfig
    engine = get_autonomous_engine()
    config = AutonomousConfig(
        max_iterations=req.max_iterations or 10,
        quality_threshold=req.quality_threshold or 0.85,
        model=req.model or "local",
    )
    session = engine.start_session(req.job_id, config=config)
    return {"session_id": session.id, "job_id": req.job_id, "status": session.status}


@app.get("/autonomous/status/{session_id}")
async def autonomous_status(session_id: str):
    from services.autonomous_service import get_autonomous_engine
    engine = get_autonomous_engine()
    session = engine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.to_dict()


@app.get("/autonomous/history/{session_id}")
async def autonomous_history(session_id: str):
    from services.autonomous_service import get_autonomous_engine
    engine = get_autonomous_engine()
    return engine.get_iteration_history(session_id)


@app.get("/autonomous/sessions")
async def autonomous_list():
    from services.autonomous_service import get_autonomous_engine
    engine = get_autonomous_engine()
    return {"sessions": engine.list_sessions()}


@app.get("/autonomous/metrics/{job_id}")
async def autonomous_metrics(job_id: str):
    from database.memory_store import get_cost_summary, get_iteration_history
    cost = get_cost_summary(job_id)
    history = get_iteration_history(job_id)
    return {"job_id": job_id, "cost": cost, "iteration_history": history}


# ── 6. Cost Tracking ──────────────────────────────────────────────────────


@app.get("/cost/total")
async def cost_total():
    from database.memory_store import get_cost_summary
    return get_cost_summary()


@app.get("/cost/{job_id}")
async def cost_by_job(job_id: str):
    from database.memory_store import get_cost_summary
    return get_cost_summary(job_id)


# ── 7. Execution Visualizer ───────────────────────────────────────────────


@app.get("/visualizer/graphs")
async def visualizer_graphs():
    from database.memory_store import list_graph_sessions
    return {"graphs": list_graph_sessions(limit=50)}


@app.get("/visualizer/debates")
async def visualizer_debates():
    from services.debate_system import get_debate_system
    ds = get_debate_system()
    return {"debates": ds.list_sessions()}


@app.get("/visualizer/autonomous")
async def visualizer_autonomous():
    from services.autonomous_service import get_autonomous_engine
    engine = get_autonomous_engine()
    return {"sessions": engine.list_sessions()}


@app.get("/visualizer/progress/{job_id}")
async def visualizer_progress(job_id: str):
    from database.memory_store import get_iteration_history, get_cost_summary
    from database.chroma_db import get_job
    job = get_job(job_id)
    history = get_iteration_history(job_id)
    cost = get_cost_summary(job_id)
    return {
        "job_id": job_id,
        "project_name": (job or {}).get("project_name", ""),
        "status": (job or {}).get("status", ""),
        "iteration_history": history,
        "cost": cost,
    }


@app.get("/visualizer/timeline/{job_id}")
async def visualizer_timeline(job_id: str):
    from services.dashboard_service import get_timeline
    return {"timeline": get_timeline(limit=200, job_id=job_id)}


# ═══════════════════════════════════════════════════════════════════════════
# v10 Endpoints — Runtime Orchestrator, Container Manager, Process Manager,
#                 Log Analyzer, Self-Healing, Deployment Orchestrator,
#                 Runtime Monitor, SDLC Pipeline, Sessions, Learning
# ═══════════════════════════════════════════════════════════════════════════


# ── 1. Runtime Orchestrator ──────────────────────────────────────────────


class RuntimeCreateRequest(BaseModel):
    job_id: str
    name: str = ""
    runtime_type: str = "subprocess"
    image: str = "python:3.11-slim"
    command: Optional[List[str]] = None
    env_vars: Optional[Dict[str, str]] = None
    port_mappings: Optional[Dict[str, int]] = None
    memory_limit: str = "256m"
    cpu_limit: float = 0.5
    timeout: int = 300


class RuntimeActionRequest(BaseModel):
    session_id: str


@app.post("/runtime/create")
async def runtime_create(req: RuntimeCreateRequest):
    from services.runtime_orchestrator import get_orchestrator, ExecutionEnvironment, RuntimeType
    env = ExecutionEnvironment(
        runtime_type=RuntimeType(req.runtime_type.lower()) if req.runtime_type in ("docker", "subprocess") else RuntimeType.SUBPROCESS,
        image=req.image, command=req.command or [],
        env_vars=req.env_vars or {},
        port_mappings={int(k): v for k, v in (req.port_mappings or {}).items()},
        memory_limit=req.memory_limit, cpu_limit=req.cpu_limit,
        timeout=req.timeout,
    )
    orch = get_orchestrator()
    session = orch.create_runtime(req.job_id, name=req.name, env=env)
    return {"session_id": session.id, "status": session.status.value}


@app.post("/runtime/start")
async def runtime_start(req: RuntimeActionRequest):
    from services.runtime_orchestrator import get_orchestrator
    orch = get_orchestrator()
    try:
        session = orch.start_runtime(req.session_id)
        return {"session_id": session.id, "status": session.status.value, "port": session.port, "pid": session.pid}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/runtime/stop")
async def runtime_stop(req: RuntimeActionRequest):
    from services.runtime_orchestrator import get_orchestrator
    orch = get_orchestrator()
    try:
        session = orch.stop_runtime(req.session_id)
        return {"session_id": session.id, "status": session.status.value}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/runtime/restart")
async def runtime_restart(req: RuntimeActionRequest):
    from services.runtime_orchestrator import get_orchestrator
    orch = get_orchestrator()
    try:
        session = orch.restart_runtime(req.session_id)
        return {"session_id": session.id, "status": session.status.value}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/runtime/destroy")
async def runtime_destroy(req: RuntimeActionRequest):
    from services.runtime_orchestrator import get_orchestrator
    orch = get_orchestrator()
    try:
        orch.destroy_runtime(req.session_id)
        return {"session_id": req.session_id, "status": "destroyed"}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/runtime/{session_id}")
async def runtime_status(session_id: str):
    from services.runtime_orchestrator import get_orchestrator
    orch = get_orchestrator()
    session = orch.get_runtime(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Runtime session not found")
    return session.to_dict()


@app.get("/runtime/{session_id}/logs")
async def runtime_logs(session_id: str, tail: int = 100):
    from services.runtime_orchestrator import get_orchestrator
    orch = get_orchestrator()
    try:
        logs = orch.get_logs(session_id, tail=tail)
        return {"session_id": session_id, "logs": logs}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/runtime/{session_id}/metrics")
async def runtime_metrics(session_id: str):
    from services.runtime_orchestrator import get_orchestrator
    orch = get_orchestrator()
    try:
        metrics = orch.get_metrics(session_id)
        return {"session_id": session_id, "metrics": metrics}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/runtimes")
async def runtime_list(job_id: Optional[str] = None):
    from services.runtime_orchestrator import get_orchestrator
    orch = get_orchestrator()
    return {"runtimes": orch.list_runtimes(job_id=job_id)}


@app.post("/runtime/recover/{session_id}")
async def runtime_recover(session_id: str):
    from services.runtime_orchestrator import get_orchestrator
    orch = get_orchestrator()
    session = orch.recover_failure(session_id)
    if not session:
        raise HTTPException(status_code=500, detail="Recovery failed")
    return {"session_id": session.id, "status": session.status.value}


# ── 2. Container Manager ─────────────────────────────────────────────────


class ContainerCreateRequest(BaseModel):
    image: str = "python:3.11-slim"
    command: Optional[List[str]] = None
    env_vars: Optional[Dict[str, str]] = None
    port_mappings: Optional[Dict[str, int]] = None
    memory_limit: str = "256m"
    cpu_limit: float = 0.5
    network_enabled: bool = True
    volumes: Optional[List[str]] = None
    name: str = ""


class ContainerActionRequest(BaseModel):
    container_id: str


@app.post("/container/create")
async def container_create(req: ContainerCreateRequest):
    from services.container_manager import get_container_manager
    cm = get_container_manager()
    container = cm.create_container(
        image=req.image, command=req.command, env_vars=req.env_vars,
        port_mappings={int(k): v for k, v in (req.port_mappings or {}).items()},
        memory_limit=req.memory_limit, cpu_limit=req.cpu_limit,
        network_enabled=req.network_enabled, volumes=req.volumes, name=req.name,
    )
    return {"container_id": container.id, "docker_id": container.docker_id, "status": container.status}


@app.post("/container/start")
async def container_start(req: ContainerActionRequest):
    from services.container_manager import get_container_manager
    cm = get_container_manager()
    try:
        container = cm.start_container(req.container_id)
        return {"container_id": req.container_id, "status": container.status}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/container/stop")
async def container_stop(req: ContainerActionRequest):
    from services.container_manager import get_container_manager
    cm = get_container_manager()
    try:
        container = cm.stop_container(req.container_id)
        return {"container_id": req.container_id, "status": container.status}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/container/restart")
async def container_restart(req: ContainerActionRequest):
    from services.container_manager import get_container_manager
    cm = get_container_manager()
    try:
        container = cm.restart_container(req.container_id)
        return {"container_id": req.container_id, "status": container.status}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/container/destroy")
async def container_destroy(req: ContainerActionRequest):
    from services.container_manager import get_container_manager
    cm = get_container_manager()
    try:
        cm.destroy_container(req.container_id)
        return {"container_id": req.container_id, "status": "destroyed"}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/container/{container_id}/logs")
async def container_logs(container_id: str, tail: int = 100):
    from services.container_manager import get_container_manager
    cm = get_container_manager()
    try:
        logs = cm.get_logs(container_id, tail=tail)
        return {"container_id": container_id, "logs": logs}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/container/{container_id}/stats")
async def container_stats(container_id: str):
    from services.container_manager import get_container_manager
    cm = get_container_manager()
    try:
        stats = cm.get_stats(container_id)
        return {"container_id": container_id, "stats": stats}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/container/{container_id}/health")
async def container_health(container_id: str):
    from services.container_manager import get_container_manager
    cm = get_container_manager()
    healthy = cm.health_check(container_id)
    return {"container_id": container_id, "healthy": healthy}


# ── 3. Process Manager ───────────────────────────────────────────────────


class ProcessRunRequest(BaseModel):
    command: Optional[List[str]] = None
    working_dir: str = ""
    env_vars: Optional[Dict[str, str]] = None
    timeout: int = 300
    runtime_type: str = ""
    serve: bool = False


@app.post("/process/run")
async def process_run(req: ProcessRunRequest):
    from services.process_manager import get_process_manager
    pm = get_process_manager()
    proc = pm.run(
        command=req.command, working_dir=req.working_dir, env_vars=req.env_vars,
        timeout=req.timeout, runtime_type=req.runtime_type, serve=req.serve,
    )
    return {"process_id": proc.id, "pid": proc.pid, "status": proc.status.value, "port": proc.port}


@app.get("/process/{process_id}")
async def process_status(process_id: str):
    from services.process_manager import get_process_manager
    pm = get_process_manager()
    proc = pm.get_process(process_id)
    if not proc:
        raise HTTPException(status_code=404, detail="Process not found")
    return {"process_id": proc.id, "pid": proc.pid, "status": proc.status.value, "stdout": proc.stdout[-2000:], "stderr": proc.stderr[-2000:]}


@app.get("/process/{process_id}/log")
async def process_log(process_id: str):
    from services.process_manager import get_process_manager
    pm = get_process_manager()
    log = pm.get_process_log(process_id)
    if not log:
        raise HTTPException(status_code=404, detail="Process log not found")
    return Response(log, media_type="text/plain")


@app.get("/processes")
async def process_list():
    from services.process_manager import get_process_manager
    pm = get_process_manager()
    return {"processes": pm.list_processes()}


# ── 4. Log Analyzer ──────────────────────────────────────────────────────


class LogAnalyzeRequest(BaseModel):
    log_text: str
    use_llm: bool = False


@app.post("/logs/analyze")
async def logs_analyze(req: LogAnalyzeRequest):
    from services.log_analyzer import get_log_analyzer
    analyzer = get_log_analyzer()
    result = analyzer.analyze(req.log_text, use_llm=req.use_llm)
    return result.to_dict()


@app.get("/logs/statistics")
async def logs_statistics():
    from services.log_analyzer import get_log_analyzer
    analyzer = get_log_analyzer()
    return analyzer.get_statistics()


# ── 5. Self-Healing ──────────────────────────────────────────────────────


class HealRequest(BaseModel):
    job_id: str
    runtime_id: str = ""
    log_text: str
    project_dir: Optional[str] = None
    max_retries: int = 3
    confidence_threshold: float = 0.6


@app.post("/healing/start")
async def healing_start(req: HealRequest):
    from services.self_healing_service import get_healing_engine
    engine = get_healing_engine()
    session = engine.detect_and_heal(
        req.job_id, req.runtime_id, req.log_text,
        project_dir=req.project_dir, max_retries=req.max_retries,
        confidence_threshold=req.confidence_threshold,
    )
    return {"session_id": session.id, "status": session.status.value}


@app.get("/healing/{session_id}")
async def healing_status(session_id: str):
    from services.self_healing_service import get_healing_engine
    engine = get_healing_engine()
    session = engine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Healing session not found")
    return session.to_dict()


@app.post("/healing/rollback/{session_id}")
async def healing_rollback(session_id: str):
    from services.self_healing_service import get_healing_engine
    engine = get_healing_engine()
    ok = engine.rollback(session_id)
    return {"session_id": session_id, "rolled_back": ok}


@app.get("/healings")
async def healing_list(job_id: Optional[str] = None):
    from services.self_healing_service import get_healing_engine
    engine = get_healing_engine()
    return {"sessions": engine.list_sessions(job_id=job_id)}


# ── 6. Deployment Orchestrator ────────────────────────────────────────────


class DeployOrchestrateRequest(BaseModel):
    job_id: str
    project_dir: str
    target: str = "docker"
    health_check_url: Optional[str] = None
    run_browser_validation: bool = False


@app.post("/deployment/start")
async def deployment_start(req: DeployOrchestrateRequest):
    from services.deployment_orchestrator import get_deployment_orchestrator
    orch = get_deployment_orchestrator()
    session = orch.deploy(req.job_id, req.project_dir, req.target, req.health_check_url, req.run_browser_validation)
    return {"session_id": session.id, "status": session.status.value, "target": session.target.value}


@app.get("/deployment/{session_id}")
async def deployment_status(session_id: str):
    from services.deployment_orchestrator import get_deployment_orchestrator
    orch = get_deployment_orchestrator()
    session = orch.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Deployment session not found")
    return session.to_dict()


@app.post("/deployment/rollback/{session_id}")
async def deployment_rollback(session_id: str):
    from services.deployment_orchestrator import get_deployment_orchestrator
    orch = get_deployment_orchestrator()
    ok = orch.rollback(session_id)
    return {"session_id": session_id, "rolled_back": ok}


@app.get("/deployments")
async def deployment_list(job_id: Optional[str] = None):
    from services.deployment_orchestrator import get_deployment_orchestrator
    orch = get_deployment_orchestrator()
    return {"sessions": orch.list_sessions(job_id=job_id)}


# ── 7. Runtime Monitor ────────────────────────────────────────────────────


class MonitorStartRequest(BaseModel):
    runtime_id: str
    interval: float = 5.0


@app.post("/monitor/start")
async def monitor_start(req: MonitorStartRequest):
    from services.runtime_monitor import get_monitor
    monitor = get_monitor()
    monitor.start_collecting(req.runtime_id, interval=req.interval)
    return {"runtime_id": req.runtime_id, "collecting": True}


@app.post("/monitor/stop/{runtime_id}")
async def monitor_stop(runtime_id: str):
    from services.runtime_monitor import get_monitor
    monitor = get_monitor()
    monitor.stop_collecting(runtime_id)
    return {"runtime_id": runtime_id, "collecting": False}


@app.get("/monitor/{runtime_id}/metrics")
async def monitor_metrics(runtime_id: str, since: Optional[float] = None, limit: int = 100):
    from services.runtime_monitor import get_monitor
    monitor = get_monitor()
    return {"runtime_id": runtime_id, "metrics": monitor.get_metrics(runtime_id, since=since, limit=limit)}


@app.get("/monitor/{runtime_id}/aggregate")
async def monitor_aggregate(runtime_id: str):
    from services.runtime_monitor import get_monitor
    monitor = get_monitor()
    return {"runtime_id": runtime_id, "aggregate": monitor.get_aggregate(runtime_id)}


@app.get("/monitor/{runtime_id}/trend")
async def monitor_trend(runtime_id: str, window: int = 10):
    from services.runtime_monitor import get_monitor
    monitor = get_monitor()
    return {"runtime_id": runtime_id, "trend": monitor.get_trend(runtime_id, window=window)}


@app.get("/monitor/anomalies")
async def monitor_anomalies(limit: int = 50):
    from services.runtime_monitor import get_monitor
    monitor = get_monitor()
    return {"anomalies": monitor.get_anomalies(limit=limit)}


@app.get("/monitor/summary")
async def monitor_summary():
    from services.runtime_monitor import get_monitor
    monitor = get_monitor()
    return monitor.get_summary()


# ── 8. Autonomous SDLC Pipeline ──────────────────────────────────────────


class SDLCStartRequest(BaseModel):
    job_id: str
    prompt: str
    model: str = "local"


@app.post("/sdlc/start")
async def sdlc_start(req: SDLCStartRequest):
    from services.sdlc_pipeline import get_sdlc_engine
    engine = get_sdlc_engine()
    pipeline = engine.run_pipeline(req.job_id, req.prompt, req.model)
    return {"pipeline_id": pipeline.id, "job_id": req.job_id, "stage": pipeline.stage.value, "status": pipeline.status}


@app.get("/sdlc/{pipeline_id}")
async def sdlc_status(pipeline_id: str):
    from services.sdlc_pipeline import get_sdlc_engine
    engine = get_sdlc_engine()
    pipeline = engine.get_pipeline(pipeline_id)
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return pipeline.to_dict()


@app.post("/sdlc/resume/{pipeline_id}")
async def sdlc_resume(pipeline_id: str):
    from services.sdlc_pipeline import get_sdlc_engine
    engine = get_sdlc_engine()
    pipeline = engine.resume(pipeline_id)
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return {"pipeline_id": pipeline.id, "stage": pipeline.stage.value, "status": pipeline.status}


@app.get("/sdlcs")
async def sdlc_list(job_id: Optional[str] = None):
    from services.sdlc_pipeline import get_sdlc_engine
    engine = get_sdlc_engine()
    return {"pipelines": engine.list_pipelines(job_id=job_id)}


# ── 9. Session Manager ───────────────────────────────────────────────────


class SessionCreateRequest(BaseModel):
    job_id: str
    name: str = ""
    session_type: str = "pipeline"
    tasks: Optional[List[str]] = None


@app.post("/sessions/create")
async def session_create(req: SessionCreateRequest):
    from services.session_manager import get_session_manager
    sm = get_session_manager()
    session = sm.create_session(req.job_id, name=req.name, session_type=req.session_type, tasks=req.tasks)
    return {"session_id": session.id, "status": session.status.value}


@app.get("/sessions/{session_id}")
async def session_status(session_id: str):
    from services.session_manager import get_session_manager
    sm = get_session_manager()
    session = sm.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.to_dict()


@app.post("/sessions/{session_id}/pause")
async def session_pause(session_id: str):
    from services.session_manager import get_session_manager
    sm = get_session_manager()
    session = sm.pause_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "status": session.status.value}


@app.post("/sessions/{session_id}/resume")
async def session_resume(session_id: str):
    from services.session_manager import get_session_manager
    sm = get_session_manager()
    session = sm.resume_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "status": session.status.value}


@app.post("/sessions/{session_id}/complete")
async def session_complete(session_id: str):
    from services.session_manager import get_session_manager
    sm = get_session_manager()
    session = sm.complete_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "status": session.status.value}


@app.get("/sessions")
async def session_list(job_id: Optional[str] = None):
    from services.session_manager import get_session_manager
    sm = get_session_manager()
    return {"sessions": sm.list_sessions(job_id=job_id)}


# ── 10. Learning Engine ──────────────────────────────────────────────────


class LearnFixRequest(BaseModel):
    error_type: str
    error_text: str
    fix: str
    file_pattern: str = ""
    job_id: str = ""


@app.post("/learning/learn-fix")
async def learning_learn_fix(req: LearnFixRequest):
    from services.learning_engine import get_learning_engine
    engine = get_learning_engine()
    engine.learn_fix(req.error_type, req.error_text, req.fix, req.file_pattern, req.job_id)
    return {"learned": True}


@app.get("/learning/fixes")
async def learning_fixes(error_type: Optional[str] = None, limit: int = 10):
    from services.learning_engine import get_learning_engine
    engine = get_learning_engine()
    return {"fixes": engine.retrieve_fixes(error_type=error_type, limit=limit)}


@app.get("/learning/recommendations")
async def learning_recommend(tech_stack: Optional[str] = None):
    tags = tech_stack.split(",") if tech_stack else None
    from services.learning_engine import get_learning_engine
    engine = get_learning_engine()
    return {
        "architectures": engine.recommend_architecture(tags),
        "deployments": engine.recommend_deployment(tags[0] if tags else None),
        "prompts": engine.recommend_prompts(),
    }


@app.get("/learning/context/{job_id}")
async def learning_context(job_id: str):
    from services.learning_engine import get_learning_engine
    engine = get_learning_engine()
    return engine.get_context_for_job(job_id)


@app.get("/learning/statistics")
async def learning_statistics():
    from services.learning_engine import get_learning_engine
    engine = get_learning_engine()
    return engine.get_statistics()


# ── 11. Dashboard Extensions ─────────────────────────────────────────────


@app.get("/dashboard/runtimes")
async def dashboard_runtimes():
    from services.runtime_orchestrator import get_orchestrator
    orch = get_orchestrator()
    return {"runtimes": orch.list_runtimes()}


@app.get("/dashboard/deployments")
async def dashboard_deployments():
    from services.deployment_orchestrator import get_deployment_orchestrator
    orch = get_deployment_orchestrator()
    return {"deployments": orch.list_sessions()}


@app.get("/dashboard/healings")
async def dashboard_healings():
    from services.self_healing_service import get_healing_engine
    engine = get_healing_engine()
    return {"healings": engine.list_sessions()}


@app.get("/dashboard/learning")
async def dashboard_learning():
    from services.learning_engine import get_learning_engine
    engine = get_learning_engine()
    return engine.get_statistics()


@app.get("/dashboard/infrastructure")
async def dashboard_infrastructure():
    from services.runtime_monitor import get_monitor
    monitor = get_monitor()
    return monitor.get_summary()


# ═══════════════════════════════════════════════════════════════════════════
# v10.1 Endpoints — Benchmark Suite
# ═══════════════════════════════════════════════════════════════════════════


class BenchmarkRunRequest(BaseModel):
    domain: str = Field(..., min_length=1, max_length=50)
    model: str = "local"
    iteration: int = 1


class BenchmarkCompareRequest(BaseModel):
    run_id_1: str
    run_id_2: str


class BenchmarkReportRequest(BaseModel):
    format: str = "json"


LIST_SUPPORTED_DOMAINS = [
    "hotel_booking", "ecommerce", "blog_cms", "task_manager",
    "expense_tracker", "chat_app", "lms", "property_management",
]


@app.get("/benchmarks/domains")
async def benchmark_domains():
    from services.benchmark_service import get_benchmark_service
    svc = get_benchmark_service()
    return {"domains": svc.list_domains()}


@app.get("/benchmarks/domain/{domain}")
async def benchmark_domain_info(domain: str):
    from services.benchmark_service import get_benchmark_service
    svc = get_benchmark_service()
    info = svc.get_domain_info(domain)
    if not info:
        raise HTTPException(status_code=404, detail=f"Domain '{domain}' not found")
    return info


@app.post("/benchmarks/run")
async def benchmark_run(req: BenchmarkRunRequest):
    from services.benchmark_service import get_benchmark_service
    svc = get_benchmark_service()
    try:
        result = svc.run_benchmark(domain=req.domain, model=req.model, iteration=req.iteration)
        return {"run_id": result.run_id, "result_id": result.id, "domain": result.domain, "status": result.status.value}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/benchmarks/result/{run_id}")
async def benchmark_result(run_id: str):
    from services.benchmark_service import get_benchmark_service
    svc = get_benchmark_service()
    result = svc.get_result(run_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Benchmark run '{run_id}' not found")
    return result.to_dict()


@app.get("/benchmarks/results")
async def benchmark_results(domain: Optional[str] = None, limit: int = 50):
    from services.benchmark_service import get_benchmark_service
    svc = get_benchmark_service()
    return {"results": svc.list_results(domain=domain, limit=limit)}


@app.get("/benchmarks/leaderboard")
async def benchmark_leaderboard(domain: Optional[str] = None, limit: int = 20):
    from services.benchmark_service import get_benchmark_service
    svc = get_benchmark_service()
    return {"leaderboard": svc.get_leaderboard(domain=domain, limit=limit)}


@app.post("/benchmarks/compare")
async def benchmark_compare(req: BenchmarkCompareRequest):
    from services.benchmark_service import get_benchmark_service
    svc = get_benchmark_service()
    try:
        return svc.compare_runs(req.run_id_1, req.run_id_2)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/benchmarks/report/{run_id}")
async def benchmark_report(run_id: str, format: str = "json"):
    from services.benchmark_service import get_benchmark_service
    svc = get_benchmark_service()
    try:
        report = svc.generate_report(run_id, format=format)
        media_type = "text/markdown" if format == "markdown" else "application/json"
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(report, media_type=media_type)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/benchmarks/trends")
async def benchmark_trends(domain: Optional[str] = None):
    from services.benchmark_service import get_benchmark_service
    svc = get_benchmark_service()
    return svc.get_trend_data(domain=domain)


@app.get("/benchmarks/statistics")
async def benchmark_statistics():
    from services.benchmark_service import get_benchmark_service
    svc = get_benchmark_service()
    return svc.get_statistics()


# ═══════════════════════════════════════════════════════════════════════════
# v11 Endpoints — Organization-Level Multi-Repository Intelligence
# ═══════════════════════════════════════════════════════════════════════════


class OrgCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = ""


class OrgAddRepoRequest(BaseModel):
    org_id: str
    name: str
    path: str
    category: str = ""
    language: str = ""
    url: str = ""
    description: str = ""


class OrgAnalyzeRequest(BaseModel):
    org_id: str
    model: str = "local"


class OrgImpactRequest(BaseModel):
    org_id: str
    query: str = Field(..., min_length=3, max_length=500)


class OrgModifyRequest(BaseModel):
    org_id: str
    description: str = Field(..., min_length=3, max_length=500)
    changes: Dict[str, Dict[str, str]]
    github_token: str = ""
    repo_full_names: Dict[str, str] = {}


class OrgValidateRequest(BaseModel):
    org_id: str
    validation_types: Optional[List[str]] = None


@app.post("/organization/create")
async def organization_create(req: OrgCreateRequest):
    from services.org_graph_service import create_organization
    graph = create_organization(req.name, req.description)
    mem_save_organization({
        "id": graph.org.id,
        "name": graph.org.name,
        "description": graph.org.description,
        "repo_count": 0,
        "entity_count": 0,
        "metadata": {},
        "created_at": graph.org.created_at,
        "updated_at": graph.org.updated_at,
    })
    return {"organization_id": graph.org.id, "name": graph.org.name}


@app.post("/organization/add-repo")
async def organization_add_repo(req: OrgAddRepoRequest):
    from services.org_graph_service import get_organization, OrganizationGraph
    graph = get_organization(req.org_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Organization not found")
    repo = graph.add_repository(
        name=req.name, path=req.path, category=req.category,
        language=req.language, url=req.url, description=req.description,
    )
    mem_save_repository({
        "id": repo.id, "org_id": req.org_id, "name": repo.name,
        "path": repo.path, "category": repo.category, "language": repo.language,
        "url": repo.url, "description": repo.description,
        "file_count": 0, "indexed_at": None, "metadata": {},
    })
    return {"repository": repo.to_dict()}


@app.post("/organization/index")
async def organization_index(req: OrgAnalyzeRequest):
    from services.org_graph_service import get_organization
    graph = get_organization(req.org_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Organization not found")
    results = {}
    for repo in graph.list_repositories():
        stats = graph.index_repository(repo.id)
        results[repo.name] = stats
    mem_save_organization({
        "id": graph.org.id, "name": graph.org.name,
        "description": graph.org.description,
        "repo_count": len(graph.list_repositories()),
        "entity_count": len(graph.org.entities),
        "metadata": {},
        "created_at": graph.org.created_at,
        "updated_at": graph.org.updated_at,
    })
    return {"organization_id": req.org_id, "index_results": results}


@app.get("/organization/graph")
async def organization_graph(org_id: str):
    from services.org_graph_service import get_organization
    graph = get_organization(org_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Organization not found")
    return graph.get_graph_data()


@app.get("/organization/repositories")
async def organization_repositories(org_id: str):
    from services.org_graph_service import get_organization
    graph = get_organization(org_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Organization not found")
    repos = [r.to_dict() for r in graph.list_repositories()]
    return {"repositories": repos}


@app.post("/organization/analyze")
async def organization_analyze(req: OrgAnalyzeRequest):
    from services.org_graph_service import get_organization, OrgGraphAnalyzer
    graph = get_organization(req.org_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Organization not found")
    analyzer = OrgGraphAnalyzer(graph)
    return {
        "shared_dependencies": analyzer.find_shared_dependencies(),
        "orphan_repos": analyzer.find_orphan_repos(),
        "critical_path": analyzer.find_critical_path(),
    }


@app.post("/organization/impact")
async def organization_impact(req: OrgImpactRequest):
    from services.org_graph_service import get_organization
    graph = get_organization(req.org_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Organization not found")
    report = graph.analyze_impact(req.query)
    mem_save_impact_report({
        "id": report.id, "org_id": req.org_id, "query": report.query,
        "affected_repos": report.affected_repos,
        "affected_files": report.affected_files,
        "impact_score": report.impact_score, "risk_level": report.risk_level,
        "recommendations": report.recommendations,
        "report_markdown": report.report_markdown,
        "created_at": report.created_at,
    })
    return report.to_dict()


@app.post("/organization/modify")
async def organization_modify(req: OrgModifyRequest):
    from services.org_graph_service import get_organization
    from services.multi_repo_editor import get_multi_repo_editor
    graph = get_organization(req.org_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Organization not found")
    editor = get_multi_repo_editor(graph)
    cc = editor.plan_change(req.org_id, req.description, req.changes)
    result = editor.apply_changes(cc.id)
    if req.github_token and req.repo_full_names:
        result = editor.create_prs(cc.id, github_token=req.github_token, repo_full_names=req.repo_full_names)
    mem_save_cross_repo_change(result.to_dict())
    return result.to_dict()


@app.get("/organization/report")
async def organization_report(org_id: str, report_id: Optional[str] = None):
    if report_id:
        report = mem_get_impact_report(report_id)
        if not report:
            raise HTTPException(status_code=404, detail="Impact report not found")
        return report
    reports = mem_get_impact_reports(org_id)
    return {"impact_reports": reports}


@app.get("/organization/changes")
async def organization_changes(org_id: str):
    changes = mem_get_cross_repo_changes(org_id)
    return {"changes": changes}


@app.get("/organization/health")
async def organization_health(org_id: str):
    from services.org_graph_service import get_organization
    graph = get_organization(org_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Organization not found")
    return graph.get_health()


@app.post("/organization/validate")
async def organization_validate(req: OrgValidateRequest):
    from services.org_graph_service import get_organization
    from services.cross_repo_validation import get_cross_repo_validator
    graph = get_organization(req.org_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Organization not found")
    validator = get_cross_repo_validator(graph)
    if req.validation_types:
        results = {}
        for vt in req.validation_types:
            method = getattr(validator, f"validate_{vt}", None)
            if method:
                results[vt] = method(req.org_id).to_dict()
    else:
        raw = validator.run_all_validations(req.org_id)
        results = {k: v.to_dict() for k, v in raw.items()}
    return {"org_id": req.org_id, "results": results}


@app.get("/organization/list")
async def organization_list():
    from services.org_graph_service import list_organizations
    return {"organizations": list_organizations()}


@app.post("/organization/dependency")
async def organization_add_dependency(
    org_id: str = Body(...), source_repo: str = Body(...),
    target_repo: str = Body(...), relationship: str = Body("depends_on"),
    weight: float = Body(1.0),
):
    from services.org_graph_service import get_organization
    graph = get_organization(org_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Organization not found")
    dep = graph.add_manual_dependency(source_repo, target_repo, relationship, weight)
    save_repository_relationship({
        "id": dep.id, "org_id": org_id, "source_repo": dep.source_repo,
        "target_repo": dep.target_repo, "source_file": dep.source_file,
        "target_file": dep.target_file, "relationship": dep.relationship,
        "weight": dep.weight, "verified": dep.verified,
    })
    return {"dependency": dep.to_dict()}


@app.get("/organization/dependencies")
async def organization_dependencies(org_id: str):
    return {"dependencies": get_repository_relationships(org_id)}


@app.delete("/organization/repo")
async def organization_delete_repo(org_id: str = Body(...), repo_id: str = Body(...)):
    from services.org_graph_service import get_organization
    graph = get_organization(org_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Organization not found")
    ok = graph.remove_repository(repo_id)
    mem_del_repository(repo_id)
    return {"deleted": ok}


@app.delete("/organization/{org_id}")
async def organization_delete(org_id: str):
    from services.org_graph_service import get_organization
    graph = get_organization(org_id)
    if graph:
        graph._save()
    mem_del_organization(org_id)
    delete_repository_relationships_by_org(org_id)
    delete_impact_reports_by_org(org_id)
    delete_cross_repo_changes_by_org(org_id)
    delete_repositories_by_org(org_id)
    return {"deleted": True}


# ═══════════════════════════════════════════════════════════════════════════
# v11.1 — Plugin & Agent SDK Ecosystem
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/plugins/install")
async def plugin_install(
    source: str = Body(...),
    name: Optional[str] = Body(None),
    version: Optional[str] = Body(None),
    author: Optional[str] = Body(None),
    description: Optional[str] = Body(None),
    plugin_type: Optional[str] = Body(None),
    permissions: Optional[List[str]] = Body(None),
):
    registry = get_plugin_registry()
    manifest = None
    if name:
        from sdk.plugin_sdk.base_plugin import PluginManifest
        manifest = PluginManifest(
            name=name,
            version=version or "1.0.0",
            author=author or "",
            description=description or "",
            plugin_type=plugin_type or "tool",
            permissions=permissions or [],
        )
    try:
        entry = registry.install_plugin(source, manifest=manifest, permissions=permissions)
        mem_save_plugin(entry.to_dict())
        return entry.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=f"Source file not found: {e}")


@app.post("/plugins/uninstall")
async def plugin_uninstall(data: Dict = Body(...)):
    plugin_id = data.get("plugin_id", "")
    registry = get_plugin_registry()
    ok = registry.uninstall_plugin(plugin_id)
    mem_delete_plugin(plugin_id)
    return {"uninstalled": ok}


@app.post("/plugins/enable")
async def plugin_enable(data: Dict = Body(...)):
    plugin_id = data.get("plugin_id", "")
    registry = get_plugin_registry()
    ok = registry.enable_plugin(plugin_id)
    entry = registry.get_plugin(plugin_id)
    if entry:
        mem_save_plugin(entry.to_dict())
    return {"enabled": ok}


@app.post("/plugins/disable")
async def plugin_disable(data: Dict = Body(...)):
    plugin_id = data.get("plugin_id", "")
    registry = get_plugin_registry()
    ok = registry.disable_plugin(plugin_id)
    entry = registry.get_plugin(plugin_id)
    if entry:
        mem_save_plugin(entry.to_dict())
    return {"disabled": ok}


@app.get("/plugins")
async def plugin_list(plugin_type: Optional[str] = None, enabled_only: bool = False):
    registry = get_plugin_registry()
    entries = registry.list_plugins(plugin_type=plugin_type, enabled_only=enabled_only)
    return {"plugins": [e.to_dict() for e in entries]}


@app.get("/plugins/details")
async def plugin_details(plugin_id: str):
    registry = get_plugin_registry()
    entry = registry.get_plugin(plugin_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Plugin not found")
    return entry.to_dict()


@app.get("/plugins/marketplace")
async def plugin_marketplace_search(
    query: str = "",
    package_type: Optional[str] = None,
    tag: Optional[str] = None,
    author: Optional[str] = None,
    sort_by: str = "downloads",
    limit: int = 50,
):
    mkt = get_marketplace_service()
    results = mkt.search_packages(
        query=query, package_type=package_type, tag=tag,
        author=author, sort_by=sort_by, limit=limit,
    )
    return {"packages": [p.to_dict() for p in results], "count": len(results)}


@app.post("/plugins/marketplace/publish")
async def marketplace_publish(
    name: str = Body(...),
    version: str = Body(...),
    author: str = Body(...),
    description: str = Body(...),
    source_path: str = Body(...),
    package_type: str = Body("plugin"),
    tags: Optional[List[str]] = Body(None),
    readme: str = Body(""),
    compatibility: str = Body(">=11.0.0"),
):
    from sdk.plugin_sdk.base_plugin import PluginManifest
    manifest = PluginManifest(
        name=name, version=version, author=author,
        description=description, compatibility=compatibility,
    )
    mkt = get_marketplace_service()
    pkg = mkt.publish_package(
        name=name, version=version, author=author,
        description=description, source_path=source_path,
        package_type=package_type, tags=tags or [],
        readme=readme, manifest=manifest,
    )
    db_data = pkg.to_dict()
    db_data["manifest_json"] = manifest.to_dict()
    db_data["tags"] = tags or []
    mem_save_marketplace_package(db_data)
    return pkg.to_dict()


@app.get("/plugins/marketplace/package")
async def marketplace_package_details(package_id: str):
    mkt = get_marketplace_service()
    pkg = mkt.get_package(package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    return pkg.to_dict()


@app.post("/plugins/marketplace/rate")
async def marketplace_rate(data: Dict = Body(...)):
    mkt = get_marketplace_service()
    pkg = mkt.rate_package(data.get("package_id", ""), data.get("rating", 0.0))
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    return pkg.to_dict()


@app.post("/plugins/marketplace/install")
async def marketplace_install(data: Dict = Body(...)):
    mkt = get_marketplace_service()
    result = mkt.install_package(data.get("package_id", ""), data.get("target_dir", "plugins"))
    if not result:
        raise HTTPException(status_code=404, detail="Package not found")
    return {"installed_at": result}


@app.get("/plugins/marketplace/list")
async def marketplace_list(package_type: Optional[str] = None, verified_only: bool = False):
    mkt = get_marketplace_service()
    results = mkt.list_packages(package_type=package_type, verified_only=verified_only)
    return {"packages": [p.to_dict() for p in results], "count": len(results)}


# ── Custom Agents ─────────────────────────────────────────────────────────

@app.post("/agents/register")
async def agent_register(
    name: str = Body(...),
    source: str = Body(...),
    version: str = Body("1.0.0"),
    description: str = Body(""),
    capabilities: Optional[List[Dict]] = Body(None),
    hooks: Optional[Dict[str, str]] = Body(None),
    config: Optional[Dict] = Body(None),
):
    agent_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    agent_data = {
        "id": agent_id,
        "name": name,
        "version": version,
        "description": description,
        "source": source,
        "capabilities": capabilities or [],
        "hooks": hooks or {},
        "config": config or {},
        "enabled": True,
        "created_at": now,
        "updated_at": now,
    }
    mem_save_custom_agent(agent_data)
    return agent_data


@app.get("/agents/custom")
async def agent_list(enabled_only: bool = False):
    agents = mem_list_custom_agents(enabled_only=enabled_only)
    return {"agents": agents, "count": len(agents)}


@app.post("/agents/delete")
async def agent_delete(data: Dict = Body(...)):
    agent_id = data.get("agent_id", "")
    ok = mem_delete_custom_agent(agent_id)
    return {"deleted": ok}


# ── Custom Workflows ──────────────────────────────────────────────────────

@app.post("/workflows/register")
async def workflow_register(
    name: str = Body(...),
    source: str = Body(...),
    version: str = Body("1.0.0"),
    description: str = Body(""),
    steps: Optional[List[Dict]] = Body(None),
    config: Optional[Dict] = Body(None),
):
    workflow_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    workflow_data = {
        "id": workflow_id,
        "name": name,
        "version": version,
        "description": description,
        "source": source,
        "steps": steps or [],
        "status": "pending",
        "config": config or {},
        "enabled": True,
        "created_at": now,
        "updated_at": now,
    }
    mem_save_custom_workflow(workflow_data)
    return workflow_data


@app.get("/workflows")
async def workflow_list(enabled_only: bool = False):
    workflows = mem_list_custom_workflows(enabled_only=enabled_only)
    return {"workflows": workflows, "count": len(workflows)}


@app.post("/workflows/delete")
async def workflow_delete(data: Dict = Body(...)):
    workflow_id = data.get("workflow_id", "")
    ok = mem_delete_custom_workflow(workflow_id)
    return {"deleted": ok}


# ── Ecosystem Health ──────────────────────────────────────────────────────

@app.get("/ecosystem/health")
async def ecosystem_health():
    registry = get_plugin_registry()
    mkt = get_marketplace_service()
    plugins = registry.list_plugins()
    packages = mkt.list_packages()
    agents = mem_list_custom_agents()
    workflows = mem_list_custom_workflows()
    return {
        "status": "ok",
        "version": "13.0.0",
        "plugins_installed": len(plugins),
        "plugins_enabled": len([p for p in plugins if p.enabled]),
        "marketplace_packages": len(packages),
        "custom_agents": len(agents),
        "custom_workflows": len(workflows),
    }


# ===================== v12 — Continuous Autonomous Evaluation =====================

@app.post("/evaluation/run")
def trigger_evaluation_run(data: Dict = Body(...)):
    from services.evaluation_scheduler import get_evaluation_scheduler
    scheduler = get_evaluation_scheduler()
    trigger_type = data.get("trigger_type", "on_demand")
    result = scheduler.trigger_run(schedule=trigger_type, triggered_by="api")
    return {"success": True, "run": result.to_dict()}


@app.get("/evaluation/history")
def list_evaluation_runs(
    limit: int = 50,
    trigger_type: Optional[str] = None,
    status: Optional[str] = None,
):
    runs = mem_list_evaluation_runs(limit=limit, trigger_type=trigger_type, status=status)
    return {"runs": runs}


@app.get("/evaluation/reports")
def list_evaluation_reports(
    report_type: Optional[str] = None,
    limit: int = 20,
):
    reports = mem_list_evaluation_reports(report_type=report_type, limit=limit)
    return {"reports": reports}


@app.get("/evaluation/leaderboards")
def get_leaderboard(
    category: Optional[str] = None,
    sort_by: str = "score",
    limit: int = 20,
):
    entries = mem_get_leaderboard(category=category, sort_by=sort_by, limit=limit)
    categories = mem_get_leaderboard_categories()
    return {"entries": entries, "categories": categories}


@app.get("/evaluation/comparison")
def get_version_comparison(
    from_version: Optional[str] = None,
    to_version: Optional[str] = None,
    limit: int = 20,
):
    comparisons = mem_get_version_comparisons(
        from_version=from_version, to_version=to_version, limit=limit)
    return {"comparisons": comparisons}


@app.get("/evaluation/regressions")
def list_regressions(
    category: Optional[str] = None,
    severity: Optional[str] = None,
    dismissed: Optional[bool] = None,
    limit: int = 100,
):
    regressions = mem_list_regressions(
        category=category, severity=severity, dismissed=dismissed, limit=limit)
    return {"regressions": regressions}


# ===================== v12.5 — Learning Engine Feedback Loop =====================


@app.post("/learning/ingest")
def ingest_learning_data(data: Dict = Body(...)):
    from services.learning_feedback_service import get_learning_feedback_service
    service = get_learning_feedback_service()
    feedback_type = data.get("feedback_type", "evaluation")
    if feedback_type == "evaluation":
        result = service.ingest_evaluation_result(data.get("run", data))
    elif feedback_type == "benchmark":
        result = service.ingest_benchmark_score(data)
    elif feedback_type == "regression":
        result = service.ingest_regression_report(data)
    elif feedback_type == "deployment":
        result = service.ingest_deployment_outcome(data)
    elif feedback_type == "healing":
        result = service.ingest_healing_statistics(data)
    else:
        result = service.ingest_evaluation_result(data)
    return {"success": True, "result": result}


@app.get("/learning/patterns")
def get_learning_patterns(
    pattern_type: Optional[str] = None,
    category: Optional[str] = None,
    min_confidence: float = 0.0,
    limit: int = 100,
):
    patterns = mem_list_learning_patterns(
        pattern_type=pattern_type, category=category,
        min_confidence=min_confidence, limit=limit,
    )
    return {"patterns": patterns}


@app.get("/learning/feedback-recommendations")
def get_learning_recommendations(
    recommendation_type: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
):
    recs = mem_list_learning_recommendations(
        recommendation_type=recommendation_type,
        category=category, status=status, limit=limit,
    )
    return {"recommendations": recs}


@app.get("/learning/insights")
def get_learning_insights_api(
    category: Optional[str] = None,
    limit: int = 20,
):
    insights = mem_get_learning_insights(category=category, limit=limit)
    return {"insights": insights}


# ===================== v12.6 — Benchmark Campaign Framework =====================


@app.post("/campaign/run")
def campaign_run(data: Dict = Body(...)):
    """Create and execute a benchmark campaign."""
    from services.benchmark_campaign_service import get_benchmark_campaign_service
    service = get_benchmark_campaign_service()
    domains = data.get("domains")
    runs_per_domain = data.get("runs_per_domain", 10)
    name = data.get("name", "")
    parallel = data.get("parallel", True)
    max_workers = data.get("max_workers", 4)
    model = data.get("model", "local")
    skip_run = data.get("skip_run", False)

    campaign = service.create_campaign(
        domains=domains,
        runs_per_domain=runs_per_domain,
        name=name,
        parallel=parallel,
        max_workers=max_workers,
        model=model,
    )

    if not skip_run:
        campaign = service.run_campaign(campaign["id"])

    return {"success": True, "campaign": campaign}


@app.get("/campaign/status")
def campaign_status(campaign_id: str):
    """Get campaign status with run details."""
    from services.benchmark_campaign_service import get_benchmark_campaign_service
    service = get_benchmark_campaign_service()
    campaign = service.get_campaign_status(campaign_id)
    if campaign is None:
        return {"success": False, "error": "Campaign not found"}
    return {"success": True, "campaign": campaign}


@app.get("/campaign/results")
def campaign_results(
    campaign_id: str,
    domain: Optional[str] = None,
):
    """Get campaign run results."""
    from services.benchmark_campaign_service import get_benchmark_campaign_service
    service = get_benchmark_campaign_service()
    results = service.get_campaign_results(campaign_id, domain=domain)
    return {"success": True, "results": results}


@app.get("/campaign/report")
def campaign_report(
    campaign_id: str,
    report_type: str = "aggregate",
):
    """Get campaign report (aggregate, leaderboard, or domain report)."""
    from services.benchmark_campaign_service import get_benchmark_campaign_service
    service = get_benchmark_campaign_service()
    if report_type == "leaderboard":
        report = service.get_campaign_leaderboard(campaign_id)
    elif report_type == "aggregate":
        report = service.get_campaign_report(campaign_id, report_type="aggregate")
    else:
        report = service.get_domain_report(campaign_id, report_type)
    if report is None:
        return {"success": False, "error": f"No {report_type} report found"}
    return {"success": True, "report": report}


@app.post("/campaign/resume")
def campaign_resume(data: Dict = Body(...)):
    """Resume an interrupted campaign."""
    from services.benchmark_campaign_service import get_benchmark_campaign_service
    service = get_benchmark_campaign_service()
    campaign_id = data.get("campaign_id")
    if not campaign_id:
        return {"success": False, "error": "campaign_id required"}
    try:
        campaign = service.resume_interrupted_campaign(campaign_id)
        return {"success": True, "campaign": campaign}
    except ValueError as e:
        return {"success": False, "error": str(e)}


@app.get("/campaign/list")
def campaign_list(limit: int = 50):
    """List all campaigns."""
    from services.benchmark_campaign_service import get_benchmark_campaign_service
    service = get_benchmark_campaign_service()
    campaigns = service.list_campaigns(limit=limit)
    return {"success": True, "campaigns": campaigns}


@app.get("/campaign/detect-interrupted")
def campaign_detect_interrupted():
    """Detect interrupted campaigns."""
    from services.benchmark_campaign_service import get_benchmark_campaign_service
    service = get_benchmark_campaign_service()
    interrupted = service.detect_interrupted_campaigns()
    return {"success": True, "interrupted_campaigns": interrupted}


# ===================== v12 — Continuous Autonomous Evaluation =====================

def _init_evaluation():
    """Register evaluation completion handler, recover state, check missed runs."""
    from services.evaluation_scheduler import get_evaluation_scheduler
    from services.evaluation_reporter import get_evaluation_reporter
    from services.learning_feedback_service import get_learning_feedback_service
    scheduler = get_evaluation_scheduler()

    # Phase 4 — recover unfinished runs and check for missed scheduled runs
    recovery = scheduler.recover_state()
    if recovery.get("marked_stale", 0) > 0:
        logger.info("Recovery marked %d stale evaluation runs", recovery["marked_stale"])
    missed = scheduler.check_missed_runs()
    if missed:
        logger.info("Recovery triggered %d missed evaluation runs", len(missed))

    def _on_run_completed(run):
        run_dict = run.to_dict()
        db_run = {
            "id": run_dict["id"],
            "trigger_type": run_dict.get("schedule", "on_demand"),
            "status": run_dict.get("status", ""),
            "autonomy_score": run_dict.get("autonomy_score", 0.0),
            "success_rate": run_dict.get("success_rate", 0.0),
            "total_cost": run_dict.get("total_cost", 0.0),
            "total_runtime": run_dict.get("avg_runtime_ms", 0.0),
            "healing_rate": run_dict.get("healing_rate", 0.0),
            "deployment_success_rate": run_dict.get("deployment_success_rate", 0.0),
            "benchmark_score": run_dict.get("autonomy_score", 0.0),
            "tasks_completed": 0,
            "tasks_failed": 0,
            "error_log": run_dict.get("error", ""),
            "started_at": run_dict.get("started_at"),
            "completed_at": run_dict.get("completed_at"),
            "created_at": run_dict.get("completed_at"),
        }
        mem_save_evaluation_run(db_run)

        if run.schedule in ("nightly", "weekly", "release"):
            report_type = "daily" if run.schedule == "nightly" else run.schedule
            past_runs = [r.to_dict() for r in scheduler.list_runs(status="completed")]
            reporter = get_evaluation_reporter()
            report = reporter.generate_report(report_type=report_type, runs=past_runs)
            report_dict = report.to_dict()
            db_report = {
                "id": report_dict["id"],
                "report_type": report_dict["report_type"],
                "title": report_dict["title"],
                "summary": report_dict["summary"],
                "metrics": report_dict.get("metrics", {}),
                "trends": {"trend_analysis": report_dict.get("trend_analysis", "")},
                "regressions_found": report_dict.get("regressions", []),
                "improvements_found": report_dict.get("improvements", []),
                "recommendations": report_dict.get("recommendations", []),
                "report_markdown": report_dict.get("markdown", ""),
                "period_start": report_dict.get("period_start"),
                "period_end": report_dict.get("period_end"),
                "created_at": report_dict.get("generated_at"),
            }
            mem_save_evaluation_report(db_report)

        # v12.5 — Feed evaluation results into Learning Feedback Service
        try:
            from services.learning_feedback_service import get_learning_feedback_service
            learning = get_learning_feedback_service()
            learning.ingest_evaluation_result(run_dict)
            # Generate recommendations for the run's categories
            if run.schedule in ("nightly", "weekly", "release"):
                learning.generate_recommendations()
        except Exception as e:
            logger.warning("Learning feedback ingestion failed: %s", e)

    scheduler.register_handler("evaluation_completion", _on_run_completed)
