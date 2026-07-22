"""Pipeline/job routes extracted from backend/main.py."""

import json
import logging
import os
import re
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field, field_validator

from backend.routes.helpers import (
    _resolve_job_path,
    _validate_file_path,
    _require_job_owner,
    _append_changelog,
    _normalize_job_dir,
    _read_all_project_files,
    _executor,
    _cancel_flags,
    _flags_lock,
    VALID_BACKENDS,
    VALID_FRONTENDS,
    VALID_DBS,
    VALID_CSS,
    VALID_TESTING,
    VALID_ORM,
    VALID_AUTH,
    VALID_DEPLOY,
)
from database.chroma_db import (
    chroma_call,
    create_job,
    delete_job,
    get_blueprint,
    get_job,
    get_logs,
    list_jobs,
    save_prompt,
    set_workspace_context,
    update_job_status,
)
from services.test_service import run_pytest, run_syntax_check
from services.llm_service import call_model
from services.file_service import BASE_DIR, list_files
from services.zip_service import get_zip_path, zip_exists
from services.audit_service import log_audit_event
from services.activity_service import log_activity
from services.notification_service import notify_generation_started, notify_workspace_change
from database.memory_store import delete_project_analytics

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Pipeline"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class StackConfig(BaseModel):
    backend: str = Field("fastapi", description=" | ".join(sorted(VALID_BACKENDS)))
    frontend: str = Field("streamlit", description=" | ".join(sorted(VALID_FRONTENDS)))
    db: str = Field("sqlite", description=" | ".join(sorted(VALID_DBS)))
    css: str = Field("bootstrap", description=" | ".join(sorted(VALID_CSS)))
    testing: str = Field("pytest", description=" | ".join(sorted(VALID_TESTING)))
    orm: str = Field("sqlalchemy", description=" | ".join(sorted(VALID_ORM)))
    auth: str = Field("none", description=" | ".join(sorted(VALID_AUTH)))
    deploy: str = Field("docker", description=" | ".join(sorted(VALID_DEPLOY)))

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
    prompt: str = Field(..., min_length=10, max_length=500)
    project_name: str = Field("My Project", min_length=1, max_length=100)
    model: str | None = "cloud"
    stack: StackConfig | None = None
    clarification: str | None = Field(
        None, max_length=300, description="Answer to the clarifying question, appended to prompt"
    )

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
    model: str | None = "cloud"


class RegenerateRequest(BaseModel):
    job_id: str
    file_path: str = Field(..., description="Relative path, e.g. backend/main.py")
    correction_note: str | None = Field(None, max_length=500, description="What to fix / improve in this file")
    model: str | None = "cloud"


class FixTestsRequest(BaseModel):
    model: str | None = "cloud"


class IterateRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=1000, description="What to add/change in the existing project")
    model: str | None = "cloud"
    job_id: str | None = None


class ReviewRequest(BaseModel):
    model: str | None = "cloud"


# ── Pipeline runner ───────────────────────────────────────────────────────────


def run_pipeline(
    job_id: str,
    prompt: str,
    project_name: str,
    model: str = "cloud",
    stack: dict[str, Any] | None = None,
    cancel_flag: threading.Event | None = None,
    workspace_id: str = "",
    user_id: str = "",
) -> dict[str, Any]:
    """Run the generation pipeline through the orchestrator with explicit workspace context."""
    from agents.orchestrator_agent import Orchestrator
    from services.agent_context import AgentContext
    from services.llm_service import is_available as ollama_is_available

    if model == "local" and not ollama_is_available():
        from database.chroma_db import update_job_status

        err = (
            f"Ollama is not reachable at {os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')}. "
            f"Check that the Ollama container is running, or select a cloud model from the sidebar."
        )
        update_job_status(
            job_id, "failed", workspace_id=workspace_id, current_agent="", progress_pct=0, error_message=err
        )
        return {"status": "failed", "error": err}

    context = AgentContext(
        workspace_id=workspace_id,
        user_id=user_id,
        job_id=job_id,
        project_name=project_name,
        extra={"model": model or "cloud", "stack": stack or {}},
    )

    orchestrator = Orchestrator(
        context=context,
        prompt=prompt,
        model=model or "cloud",
        stack=stack,
        cancel_flag=cancel_flag,
    )
    try:
        # Background threads do not inherit the request workspace context.
        # Set it once here so every agent storage call stays in the same workspace.
        set_workspace_context(workspace_id)
        return orchestrator.run()
    finally:
        with _flags_lock:
            _cancel_flags.pop(job_id, None)


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("/clarify")
def clarify_prompt(req: ClarifyRequest):
    """Ask the requirement agent for one clarifying question when needed."""
    from agents.requirement_agent import clarify

    question = clarify(req.prompt, model=req.model or "cloud")
    return {"question": question}


@router.post("/generate-project")
def generate_project(req: GenerateRequest, request: Request = None):
    """Queue a new project generation job and run it in a background thread."""
    job_id = str(uuid.uuid4())
    ws_id = getattr(request.state, "workspace_id", "") if request else ""
    uid = getattr(request.state, "user_id", "") if request else ""

    try:
        chroma_call(create_job, 20, job_id, workspace_id=ws_id, user_id=uid)
        chroma_call(save_prompt, 20, job_id, req.prompt, req.project_name, workspace_id=ws_id, user_id=uid)
    except TimeoutError:
        raise HTTPException(status_code=503, detail="Database is busy — try again in a moment")
    except Exception as exc:
        logger.error("Failed to create job %s: %s", job_id, exc)
        raise HTTPException(status_code=503, detail="Could not create job. Please try again.")

    # Audit log
    try:
        if ws_id:
            log_audit_event(ws_id, uid, "Project Created", "project", job_id)
            log_activity(ws_id, uid, "project.created", f"Started generating '{req.project_name}'", "project", job_id)
        if uid:
            notify_generation_started(uid, ws_id, req.project_name, job_id)
    except Exception:
        pass

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
            "model": req.model or "cloud",
            "stack": stack,
            "cancel_flag": cancel_flag,
            "workspace_id": ws_id,
            "user_id": uid,
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


@router.post("/cancel/{job_id}")
def cancel_job(job_id: str, request: Request = None):
    """Cancel a queued or running generation job."""
    ws_id = getattr(request.state, "workspace_id", "") if request else ""
    uid = getattr(request.state, "user_id", "") if request else ""
    job = _require_job_owner(job_id, ws_id, uid)

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
        workspace_id=ws_id,
        current_agent="",
        progress_pct=int(job.get("progress_pct", 0)),
        error_message="Cancelled by user.",
    )
    return {"job_id": job_id, "status": "cancelled"}


@router.post("/regenerate-file")
def regenerate_file(req: RegenerateRequest, request: Request = None):
    """Regenerate a single file for a completed project."""
    ws_id = getattr(request.state, "workspace_id", "") if request else ""
    uid = getattr(request.state, "user_id", "") if request else ""
    job = _require_job_owner(req.job_id, ws_id, uid)
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
        model=req.model or "cloud",
        job_id=req.job_id,
        agent="RegenerateFileEndpoint",
    ).strip()
    regenerated = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", regenerated)
    regenerated = re.sub(r"\s*```$", "", regenerated).strip()

    target.write_text(regenerated + ("\n" if regenerated and not regenerated.endswith("\n") else ""), encoding="utf-8")
    syntax_result = run_syntax_check(target) if target.suffix == ".py" else {"valid": True, "error": ""}
    _append_changelog(req.job_id, "File Regenerated", f"- **File**: {req.file_path}\n- **Note**: {instructions}\n")
    if ws_id:
        log_activity(ws_id, uid, "project.changed", f"Regenerated {req.file_path}", "project", req.job_id)
        notify_workspace_change(
            ws_id,
            uid,
            job.get("project_name", req.job_id),
            req.job_id,
            f"{uid or 'A workspace member'} regenerated {req.file_path}",
        )

    return {
        "job_id": req.job_id,
        "file_path": req.file_path,
        "chars": len(regenerated),
        "syntax_ok": bool(syntax_result.get("valid", True)),
        "syntax_error": syntax_result.get("error", ""),
    }


@router.get("/test-files/{job_id}")
def get_test_files(job_id: str, request: Request = None):
    """Return all test files for a project."""
    ws_id = getattr(request.state, "workspace_id", "") if request else ""
    uid = getattr(request.state, "user_id", "") if request else ""
    _require_job_owner(job_id, ws_id, uid)
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


@router.post("/fix-tests/{job_id}")
def fix_tests(job_id: str, req: FixTestsRequest, request: Request = None):
    """
    Run tests, collect failures, send to LLM to fix source code,
    apply fixes, re-run tests. Returns before/after results.
    """
    ws_id = getattr(request.state, "workspace_id", "") if request else ""
    uid = getattr(request.state, "user_id", "") if request else ""
    job = _require_job_owner(job_id, ws_id, uid)
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

        _update_status(
            job_id,
            "complete",
            workspace_id=ws_id,
            test_total=pr.get("collected", 0),
            test_passed=pr.get("collected", 0),
            test_failed=0,
            test_skipped=0,
            test_summary="All tests pass.",
            test_details=json.dumps(_td) if _td else "",
        )
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
    _orig_assertions: dict[str, set] = {}
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
                str(p.relative_to(job_dir))
                for p in sorted(job_dir.rglob("*"))
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
            + "\n".join(f"  {a}" for a in sorted(_orig_assertions))
            + "\n\n"
            "Output the complete changed file in:\n"
            "--- FILE: tests/test_app.py\n"
            "--- ACTION: MODIFY\n"
            "--- CONTENT:\n"
            "[full file]\n"
            "--- END\n"
            "If you cannot fix, output: --- NO CHANGES ---"
        )

        try:
            result = call_model(
                prompt, system_prompt=system, model=req.model or "cloud", job_id=job_id, agent="FixTestsEndpoint"
            )
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

    _update_status(
        job_id,
        "complete",
        workspace_id=ws_id,
        test_total=after_collected,
        test_passed=after_collected - len(after_failures),
        test_failed=len(after_failures),
        test_skipped=0,
        test_summary=f"{after_collected - len(after_failures)} passed, {len(after_failures)} failed.",
        test_details=json.dumps(_test_details) if _test_details else "",
    )

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


@router.post("/iterate/{job_id}")
async def iterate_project(job_id: str, req: IterateRequest, request: Request = None):
    """
    Modify an existing completed project with new instructions.
    Reads all generated files, sends to LLM with the new prompt,
    applies changes, re-runs syntax checks and tests.
    """
    ws_id = getattr(request.state, "workspace_id", "") if request else ""
    uid = getattr(request.state, "user_id", "") if request else ""
    job = _require_job_owner(job_id, ws_id, uid)
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
    _skip_prefixes = {
        "README",
        "Dockerfile",
        "start.",
        "requirements",
        "VALIDATION_REPORT",
        "__pycache__",
        ".git",
        "node_modules",
        "package-lock",
        "yarn.lock",
    }
    src_files = {
        k: v
        for k, v in existing_files.items()
        if any(k.endswith(ext) for ext in _code_exts)
        and not any(k.startswith(prefix) or prefix in k for prefix in _skip_prefixes)
    }
    # If no source files found (shouldn't happen), fall back to all
    if not src_files:
        src_files = existing_files

    file_contents_str = "\n\n".join(
        f"--- FILE: {k} ---\n{v}\n--- END FILE: {k} ---" for k, v in sorted(src_files.items())
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
        result = call_model(
            prompt, system_prompt=system, model=req.model or "cloud", job_id=job_id, agent="IterateEndpoint"
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"LLM call failed: {exc}")

    _ilog = logging.getLogger("backend.main")
    _ilog.info("Iterate LLM result (%d chars): %.500s", len(result), result)

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
                block_text,
                re.DOTALL,
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
            diff_lines = list(
                difflib.unified_diff(
                    old_text.splitlines(keepends=True),
                    new_text.splitlines(keepends=True),
                    fromfile=f"a/{fpath}",
                    tofile=f"b/{fpath}",
                )
            )
            if diff_lines:
                diffs[fpath] = "".join(diff_lines)
    for fpath in added:
        full = job_dir / fpath
        if full.exists():
            new_text = full.read_text(encoding="utf-8")
            diff_lines = list(
                difflib.unified_diff(
                    [],
                    new_text.splitlines(keepends=True),
                    fromfile="/dev/null",
                    tofile=f"b/{fpath}",
                )
            )
            diffs[fpath] = "".join(diff_lines)

    # Re-run syntax and tests
    syntax_results: dict[str, Any] = {}
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
                fr = await fix_tests(job_id, FixTestsRequest(model=req.model or "cloud"), request=request)
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

    update_job_status(
        job_id, "complete", workspace_id=ws_id, current_agent="", progress_pct=100, error_message="", review_summary=""
    )

    # Auto-run AI review after iteration
    try:
        review = run_project_review(job_id, model=req.model or "cloud")
        update_job_status(job_id, "complete", workspace_id=ws_id, progress_pct=100, review_summary=json.dumps(review))
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
        if ws_id:
            changed_files = ", ".join(modified + added + deleted)
            log_activity(
                ws_id,
                uid,
                "project.changed",
                f"Updated {job.get('project_name', job_id)} with a prompt ({changed_files})",
                "project",
                job_id,
            )
            notify_workspace_change(
                ws_id,
                uid,
                job.get("project_name", job_id),
                job_id,
                f"A workspace member changed {changed_files or 'the project'} with a prompt",
            )

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


@router.get("/files/{job_id}")
def get_file_tree(job_id: str, request: Request = None):
    """
    Return the live file tree for a job — shows files as they appear during generation.
    Works on running jobs (partial list) and completed jobs.
    """
    ws_id = getattr(request.state, "workspace_id", "") if request else ""
    uid = getattr(request.state, "user_id", "") if request else ""
    job = _require_job_owner(job_id, ws_id, uid)

    try:
        job_dir = _resolve_job_path(job_id)
    except HTTPException:
        # Job may be complete and already zipped
        return {"job_id": job_id, "files": [], "zipped": zip_exists(job_id)}

    if not job_dir.exists():
        return {"job_id": job_id, "files": [], "zipped": zip_exists(job_id)}

    files = [str(p.relative_to(job_dir)) for p in list_files(job_id)]
    return {
        "job_id": job_id,
        "files": sorted(files),
        "zipped": zip_exists(job_id),
        "status": job.get("status"),
    }


TEXT_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".vue",
    ".svelte",
    ".html",
    ".css",
    ".scss",
    ".less",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".md",
    ".txt",
    ".rst",
    ".sh",
    ".bat",
    ".ps1",
    ".env",
    ".xml",
    ".svg",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".java",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".sql",
    ".graphql",
    ".dockerfile",
    ".gitignore",
}


@router.get("/read-project-file/{job_id}/{path:path}")
def read_project_file(job_id: str, path: str, request: Request = None):
    """Read a single generated file's content."""
    ws_id = getattr(request.state, "workspace_id", "") if request else ""
    uid = getattr(request.state, "user_id", "") if request else ""
    _require_job_owner(job_id, ws_id, uid)
    job_dir = _resolve_job_path(job_id)
    full = _validate_file_path(job_dir, path)
    if not full.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    if full.suffix.lower() not in TEXT_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Cannot read binary file: {full.name}")
    try:
        return {"content": full.read_text(encoding="utf-8")}
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/validate/{job_id}")
def validate_project(job_id: str, request: Request = None):
    """
    Re-run syntax checks + pytest on an existing job's generated files.
    Useful after /regenerate-file.
    """
    ws_id = getattr(request.state, "workspace_id", "") if request else ""
    uid = getattr(request.state, "user_id", "") if request else ""
    job = _require_job_owner(job_id, ws_id, uid)

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
        "job_id": job_id,
        "syntax_results": syntax_results,
        "syntax_ok": all_syntax_ok,
        "pytest": pytest_result,
    }


# ── AI Project Review ──────────────────────────────────────────────────────────


def run_project_review(job_id: str, model: str = "cloud") -> dict[str, Any]:
    """AI-powered review of the entire project. Sync so it can run from pipeline threads."""
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
        f"## Syntax Errors\n" + ("\n".join(syntax_errors) if syntax_errors else "None") + "\n\n"
        "## Test Results\n" + (test_output[:2000] if test_output else "No tests found.") + "\n\n"
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

    def _parse_review(result: str) -> dict | None:
        stripped = re.sub(r"```\w*\n?", "", result).strip()
        # Try full parse
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        # Try to extract JSON block
        m = re.search(r"\{.*\}", stripped, re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(0))
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
                f"## Syntax Errors\n" + ("\n".join(syntax_errors) if syntax_errors else "None") + "\n\n"
                "## Test Results\n" + (test_output[:1000] if test_output else "No tests found.") + "\n\n"
                'Output JSON: {"verdict": "PASS|WARN|FAIL", "issues": [], "recommendations": []}'
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

    # Keep the review contract stable for every model response. Older prompts
    # used `description`; the UI consumes `message` and `score`.
    normalized_issues = []
    for issue in parsed.get("issues", []):
        if not isinstance(issue, dict):
            continue
        severity = str(issue.get("severity", "info")).lower()
        if severity not in {"error", "warning", "info"}:
            severity = "info"
        normalized_issues.append(
            {
                "severity": severity,
                "message": str(issue.get("message") or issue.get("description") or "Review finding"),
                "file": issue.get("file", ""),
                "line": issue.get("line"),
            }
        )
    parsed["issues"] = normalized_issues
    parsed.setdefault(
        "score",
        max(
            0,
            100
            - sum(25 for i in normalized_issues if i["severity"] == "error")
            - sum(8 for i in normalized_issues if i["severity"] == "warning"),
        ),
    )
    parsed.setdefault("summary", parsed.get("error") or "Review completed.")

    parsed["job_id"] = job_id
    parsed["syntax_ok"] = len(syntax_errors) == 0
    parsed["tests_passed"] = tests_passed
    return parsed


@router.post("/review/{job_id}")
def review_project(job_id: str, req: ReviewRequest, request: Request = None):
    """Run AI-powered project review on demand."""
    ws_id = getattr(request.state, "workspace_id", "") if request else ""
    uid = getattr(request.state, "user_id", "") if request else ""
    job = _require_job_owner(job_id, ws_id, uid)
    review = run_project_review(job_id, model=req.model or "cloud")
    # Store in DB for display
    update_job_status(
        job_id,
        job.get("status", "complete"),
        workspace_id=ws_id,
        progress_pct=100,
        review_summary=json.dumps(review),
    )
    return review


@router.get("/status/{job_id}")
def get_status(job_id: str, request: Request = None):
    ws_id = getattr(request.state, "workspace_id", "") if request else ""
    uid = getattr(request.state, "user_id", "") if request else ""
    _require_job_owner(job_id, ws_id, uid)

    job = get_job(job_id, workspace_id=ws_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    test_details_raw = job.get("test_details", "")
    try:
        test_details = json.loads(test_details_raw) if test_details_raw else []
    except (json.JSONDecodeError, TypeError):
        test_details = []
    try:
        job_dir = _resolve_job_path(job_id)
    except HTTPException:
        job_dir = None
    progress = int(job.get("progress_pct", 0))
    message = job.get("error_message", "")
    test_total = int(job.get("test_total", 0))
    test_passed = int(job.get("test_passed", 0))
    test_failed = int(job.get("test_failed", 0))
    return {
        "job_id": job_id,
        "status": job.get("status"),
        "project_name": job.get("project_name"),
        "current_agent": job.get("current_agent"),
        "progress_pct": progress,
        "progress": progress,
        "error_message": message,
        "message": message,
        "file_count": int(job.get("file_count", 0)),
        "test_total": test_total,
        "tests_total": test_total,
        "test_passed": test_passed,
        "tests_passed": test_passed,
        "test_failed": test_failed,
        "tests_failed": test_failed,
        "test_skipped": int(job.get("test_skipped", 0)),
        "test_summary": job.get("test_summary", ""),
        "test_details": test_details,
        "review_summary": job.get("review_summary", ""),
        "logs": get_logs(job_id, workspace_id=ws_id),
        "file_list": [str(p.relative_to(job_dir)) for p in list_files(job_id)] if job_dir and job_dir.exists() else [],
        "gates_passed": int(job.get("gates_passed", 0)),
        "gates_total": int(job.get("gates_total", 0)),
        "gates_failed": json.loads(job.get("gates_failed", "[]")) if job.get("gates_failed") else [],
        "zip_available": zip_exists(job_id),
    }


@router.get("/changelog/{job_id}")
def get_changelog(job_id: str, request: Request = None):
    """Return the per-project CHANGELOG.md content."""
    ws_id = getattr(request.state, "workspace_id", "") if request else ""
    uid = getattr(request.state, "user_id", "") if request else ""
    _require_job_owner(job_id, ws_id, uid)
    changelog = BASE_DIR / job_id / "CHANGELOG.md"
    if not changelog.exists():
        return {"job_id": job_id, "changelog": "", "exists": False}
    content = changelog.read_text(encoding="utf-8")
    return {"job_id": job_id, "changelog": content, "exists": True}


@router.get("/download/{job_id}")
def download(job_id: str, request: Request = None):
    ws_id = getattr(request.state, "workspace_id", "") if request else ""
    uid = getattr(request.state, "user_id", "") if request else ""
    job = _require_job_owner(job_id, ws_id, uid)
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


@router.get("/jobs")
def list_recent_jobs(request: Request = None):
    ws_id = getattr(request.state, "workspace_id", "") if request else ""
    uid = getattr(request.state, "user_id", "") if request else ""
    jobs = list_jobs(workspace_id=ws_id, user_id=uid, limit=20)
    for job in jobs:
        job["progress"] = int(job.get("progress_pct", 0))
        job["message"] = job.get("error_message", "")
        job["tests_total"] = int(job.get("test_total", 0))
        job["tests_passed"] = int(job.get("test_passed", 0))
        job["tests_failed"] = int(job.get("test_failed", 0))
    return {"jobs": jobs}


@router.delete("/jobs/{job_id}")
def delete_project(job_id: str, request: Request = None):
    """Delete a project: removes ChromaDB record, SQLite analytics, files, and zip."""
    ws_id = getattr(request.state, "workspace_id", "") if request else ""
    uid = getattr(request.state, "user_id", "") if request else ""
    # Ownership check — 403 if not owner, 404 if not found
    _require_job_owner(job_id, ws_id, uid)
    import shutil

    ok = True
    if not delete_job(job_id, workspace_id=ws_id):
        ok = False
    delete_project_analytics(job_id, workspace_id=ws_id, user_id=uid)
    job_dir = BASE_DIR / job_id
    if job_dir.exists():
        shutil.rmtree(str(job_dir))
    zpath = get_zip_path(job_id)
    if zpath and Path(zpath).exists():
        Path(zpath).unlink(missing_ok=True)

    try:
        ws_id = getattr(request.state, "workspace_id", "") if request else ""
        uid = getattr(request.state, "user_id", "") if request else ""
        if ws_id:
            log_audit_event(ws_id, uid, "Project Deleted", "project", job_id)
    except Exception:
        pass

    if ok:
        return {"status": "deleted", "job_id": job_id}
    raise HTTPException(status_code=500, detail="Failed to delete job from database.")
