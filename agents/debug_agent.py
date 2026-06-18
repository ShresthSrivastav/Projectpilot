"""
Debug / Testing Agent — syntax checks, auto-fix via LLM, pytest runner.

New in v4:
  - Parallel syntax checks + fixes via ThreadPoolExecutor
  - Blueprint reflection: verifies generated routes match blueprint
  - job_id / agent forwarded to call_model for structured logging
"""
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from database.chroma_db import log_to_db
from services.file_service import BASE_DIR
from services.llm_service import call_model, clean_code_response
from services.test_service import run_pytest, run_syntax_check

logger = logging.getLogger(__name__)

MAX_RETRIES = int(os.getenv("DEBUG_MAX_RETRIES", "5"))
PARALLEL_FIX_WORKERS = int(os.getenv("DEBUG_PARALLEL_WORKERS", "2"))

_FIX_SYS = (
    "You are a Python debugging expert. "
    "Return the COMPLETE corrected Python source file ONLY — "
    "no markdown fences, no explanations. Fix only the described error."
)


def _attempt_fix(file_path: Path, error: str, job_id: str, model: str) -> bool:
    models_to_try = [model]
    if model == "cloud":
        models_to_try.append("local")
    elif model == "local":
        models_to_try.append("cloud")

    for current_model in models_to_try:
        try:
            code = file_path.read_text(encoding="utf-8")
        except OSError as exc:
            log_to_db(job_id, "DebugAgent", f"Cannot read {file_path.name}: {exc}", "ERROR")
            return False

        try:
            fixed = clean_code_response(
                call_model(
                    f"File: {file_path.name}\nError:\n{error}\n\nSource:\n{code}\n\n"
                    "Return the complete corrected file:",
                    system_prompt=_FIX_SYS,
                    model=current_model,
                    job_id=job_id, agent="DebugAgent",
                )
            )
        except RuntimeError as exc:
            log_to_db(job_id, "DebugAgent", f"LLM fix call failed ({current_model}): {exc}", "ERROR")
            continue

        if not fixed.strip():
            continue

        file_path.write_text(fixed, encoding="utf-8")
        check = run_syntax_check(file_path)
        if check["valid"]:
            log_to_db(job_id, "DebugAgent", f"Fixed successfully: {file_path.name} ({current_model})")
            return True
        log_to_db(job_id, "DebugAgent", f"Fix did not resolve {file_path.name}.", "WARNING")

    return False


def _check_and_fix_file(rel: str, job_dir: Path, job_id: str, fix_model: str) -> dict[str, Any]:
    """Check one file and attempt fixes. Returns error dict or None."""
    abs_path = job_dir / rel
    if not abs_path.exists():
        return None

    check = run_syntax_check(abs_path)
    if check["valid"]:
        log_to_db(job_id, "DebugAgent", f" {rel}")
        return None

    log_to_db(job_id, "DebugAgent", f"Syntax error in {rel}: {check['error']}", "WARNING")
    error_entry = {"file": rel, "error": check["error"], "type": "syntax"}

    for attempt in range(1, MAX_RETRIES + 1):
        log_to_db(job_id, "DebugAgent", f"Fix attempt {attempt}/{MAX_RETRIES}: {rel}")
        if _attempt_fix(abs_path, check["error"], job_id, fix_model):
            return None  # fixed
        check = run_syntax_check(abs_path)
        if check["valid"]:
            return None  # fixed on re-check
        if attempt < MAX_RETRIES:
            backoff = 2 ** attempt
            log_to_db(job_id, "DebugAgent", f"Backoff {backoff}s before retry {attempt+1}…")
            time.sleep(backoff)

    log_to_db(job_id, "DebugAgent", f"Could not fix {rel} after {MAX_RETRIES} attempts.", "ERROR")
    return error_entry


def _reflect_blueprint(blueprint: dict, job_dir: Path, job_id: str) -> list[dict]:
    """
    Blueprint reflection: read backend/main.py and check that routes defined
    in the blueprint actually appear in the generated code.
    Logs warnings for missing routes but does not fail the pipeline.
    """
    issues = []
    main_py = job_dir / "backend" / "main.py"
    if not main_py.exists():
        return issues

    try:
        source = main_py.read_text(encoding="utf-8")
    except OSError:
        return issues

    for route in blueprint.get("routes", []):
        path = route.get("path", "")
        if not path or path == "/health":
            continue
        # Check if the path string appears anywhere in main.py
        if path not in source:
            log_to_db(
                job_id, "DebugAgent",
                f"Blueprint reflection: route '{route.get('method')} {path}' "
                f"not found in backend/main.py", "WARNING"
            )
            issues.append({
                "file": "backend/main.py",
                "error": f"Blueprint route '{path}' missing from generated code",
                "type": "reflection",
            })

    if not issues:
        log_to_db(job_id, "DebugAgent", "Blueprint reflection passed — all routes present.")
    return issues


def run(
    generated_files: list[str],
    job_id: str,
    model: str = None,
    blueprint: dict = None,
) -> dict[str, Any]:
    log_to_db(job_id, "DebugAgent", f"Checking {len(generated_files)} files (parallel).")
    errors: list[dict[str, Any]] = []
    fixes = 0
    job_dir = BASE_DIR / job_id
    fix_model = model or "local"

    py_files = [f for f in generated_files if f.endswith(".py")]

    #  Parallel syntax check + fix 
    with ThreadPoolExecutor(max_workers=PARALLEL_FIX_WORKERS) as pool:
        futures = {
            pool.submit(_check_and_fix_file, rel, job_dir, job_id, fix_model): rel
            for rel in py_files
        }
        for future in as_completed(futures):
            result = future.result()
            if result is None:
                fixes += 1  # was either clean or got fixed
            else:
                errors.append(result)

    #  Blueprint reflection check 
    if blueprint:
        reflection_issues = _reflect_blueprint(blueprint, job_dir, job_id)
        errors.extend(reflection_issues)

    #  Run pytest if tests exist 
    test_dir = job_dir / "tests"
    if test_dir.exists() and any(test_dir.rglob("test_*.py")):
        log_to_db(job_id, "DebugAgent", "Running pytest on generated tests…")
        result = run_pytest(job_id)
        if not result["passed"]:
            for f in result["failures"]:
                errors.append({
                    "file":  f.get("file", "?"),
                    "error": f.get("error", "Test failure"),
                    "type":  "test",
                })
            log_to_db(job_id, "DebugAgent", f"pytest: {len(result['failures'])} failure(s).", "WARNING")
        else:
            log_to_db(job_id, "DebugAgent", "pytest: all tests passed.")
    else:
        log_to_db(job_id, "DebugAgent", "No generated tests found — skipping pytest.")

    status = "passed" if not errors else ("partial" if fixes > 0 else "failed")
    log_to_db(
        job_id, "DebugAgent",
        f"Done — status={status}, errors={len(errors)}, fixes={fixes}.",
    )
    return {"status": status, "errors": errors, "fixes_applied": fixes}
