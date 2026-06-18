"""Auto-Fix Service — iterative test-and-repair loop.

On each iteration:
1. Run pytest on the project
2. If all pass, done
3. If failures, collect test output + source files
4. Send to LLM with instructions to fix the SOURCE code (not tests)
5. Apply fixes
6. Re-run tests
7. Repeat until pass or max_attempts

Records fix patterns for future learning.
"""
import logging
import os
import re
from pathlib import Path
from typing import Any

from database.chroma_db import update_job_status
from services.file_service import BASE_DIR
from services.llm_service import call_model
from services.memory_service import record_successful_fix
from services.test_service import run_pytest, run_syntax_check

logger = logging.getLogger(__name__)

MAX_AUTOFIX_ATTEMPTS = int(os.getenv("MAX_AUTOFIX_ATTEMPTS", "5"))


def run_autofix(
    job_id: str,
    model: str = "local",
    max_attempts: int = MAX_AUTOFIX_ATTEMPTS,
    on_progress=None,
) -> dict[str, Any]:
    job_dir = BASE_DIR / job_id
    if not job_dir.exists():
        return {"job_id": job_id, "status": "error", "error": "Project directory not found."}

    history = []
    test_dir = job_dir / "tests"

    for attempt in range(1, max_attempts + 1):
        if on_progress:
            on_progress(attempt, max_attempts)

        pr = run_pytest(job_id, timeout=120)
        output = pr.get("output", "")
        passed = pr.get("passed", False)
        failures = pr.get("failures", [])
        collected = pr.get("collected", 0)
        history.append({
            "attempt": attempt,
            "passed": passed,
            "collected": collected,
            "failures": len(failures),
            "output_preview": output[:500],
        })

        update_job_status(job_id, "running", current_agent="AutoFixAgent",
                          progress_pct=min(100, int(attempt / max_attempts * 100)),
                          test_total=collected,
                          test_passed=collected - len(failures),
                          test_failed=len(failures),
                          test_summary=f"Auto-fix attempt {attempt}/{max_attempts}: "
                                       f"{collected - len(failures)} passed, {len(failures)} failed.")

        if passed:
            logger.info("Auto-fix succeeded on attempt %d/%d", attempt, max_attempts)
            update_job_status(job_id, "complete", current_agent="AutoFixAgent",
                              progress_pct=100,
                              test_total=collected, test_passed=collected,
                              test_failed=0,
                              test_summary=f"All tests pass after {attempt} attempt(s).")
            return {
                "job_id": job_id,
                "status": "passed",
                "attempts": attempt,
                "history": history,
            }

        if attempt >= max_attempts:
            break

        files_changed = _fix_failing_tests(job_id, job_dir, test_dir, output, attempt, model)

        if not files_changed:
            logger.warning("Auto-fix attempt %d: LLM made no changes, stopping.", attempt)
            break

    update_job_status(job_id, "complete", current_agent="AutoFixAgent",
                      progress_pct=100,
                      test_total=history[-1].get("collected", 0),
                      test_passed=history[-1].get("collected", 0) - history[-1].get("failures", 0),
                      test_failed=history[-1].get("failures", 0),
                      test_summary=f"Auto-fix exhausted after {len(history)} attempt(s).")
    return {
        "job_id": job_id,
        "status": "failed",
        "attempts": len(history),
        "history": history,
    }


def _fix_failing_tests(
    job_id: str,
    job_dir: Path,
    test_dir: Path,
    test_output: str,
    attempt: int,
    model: str,
) -> list[str]:
    source_file_map = {}
    for fp in sorted(job_dir.rglob("*.py")):
        if "__pycache__" in str(fp) or fp.parent == test_dir:
            continue
        rel = str(fp.relative_to(job_dir))
        source_file_map[rel] = fp.read_text(encoding="utf-8")

    test_files = {}
    if test_dir.exists():
        for fp in sorted(test_dir.rglob("*.py")):
            if "__pycache__" in str(fp):
                continue
            rel = str(fp.relative_to(test_dir))
            test_files[rel] = fp.read_text(encoding="utf-8")

    source_block = "\n\n".join(
        f"--- {k} ---\n{v}\n--- END {k}" for k, v in sorted(source_file_map.items())
    )
    test_block = "\n\n".join(
        f"--- tests/{k} ---\n{v}\n--- END tests/{k}" for k, v in sorted(test_files.items())
    )

    prompt = (
        f"The project at {job_id} has failing tests.\n\n"
        f"## Test output (attempt {attempt}):\n{test_output[:3000]}\n\n"
        f"## Source files:\n{source_block}\n\n"
        f"## Test files:\n{test_block}\n\n"
        "Fix the SOURCE code so that all tests pass. Output changes in this format:\n"
        "--- FILE: relative/path/to/file.py\n"
        "--- ACTION: MODIFY\n"
        "--- CONTENT:\n[complete updated file content]\n"
        "--- END\n\n"
        "Include COMPLETE file contents for each changed file.\n"
        "If no changes needed, output exactly: --- NO CHANGES ---"
    )

    system = (
        "You are an expert Python debugger. Fix failing tests by repairing the "
        "application source code. Preserve existing functionality. "
        "Output one --- FILE: ... block per changed file with full content."
    )

    try:
        result = call_model(prompt, system_prompt=system, model=model,
                            job_id=job_id, agent="AutoFixAgent")
    except RuntimeError as exc:
        logger.error("Auto-fix LLM call failed: %s", exc)
        return []

    result = re.sub(r"```\w*\n?", "", result)
    if "NO CHANGES" in result.upper():
        return []

    modified = []
    blocks = re.split(r"---\s*FILE\s*:\s*", result)
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.split("\n")
        fpath = lines[0].strip().rstrip("-").strip()
        if not fpath:
            continue
        block_text = "\n".join(lines[1:])
        content_match = re.search(
            r"---\s*CONTENT\s*:\s*\n?(.*?)(?:\n---\s*END|$)",
            block_text, re.DOTALL,
        )
        content = content_match.group(1).strip() if content_match else ""
        if not content:
            continue
        full_path = (job_dir / fpath).resolve()
        try:
            full_path.relative_to(job_dir.resolve())
        except ValueError:
            logger.warning("Path traversal blocked in autofix: %s", fpath)
            continue
        if full_path.exists():
            full_path.write_text(content, encoding="utf-8")
            modified.append(fpath)
            logger.info("Auto-fix modified: %s", fpath)

    for fp in modified:
        full = job_dir / fp
        if full.suffix == ".py":
            sr = run_syntax_check(full)
            if not sr["valid"]:
                logger.warning("Auto-fix introduced syntax error in %s: %s", fp, sr.get("error"))

    if modified:
        record_successful_fix(test_output[:500], ", ".join(modified),
                              f"Auto-fix attempt {attempt}")

    return modified
