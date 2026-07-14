"""Self-Healing Acceptance Gates — iteratively repair gate failures via LLM.

When any healable gate fails (import, syntax, test, runtime, packaging):

  1. Capture failure details
  2. Send failure context + project files to LLM
  3. Apply suggested fixes
  4. Re-run only the failed gates
  5. Repeat up to MAX_HEALING_ATTEMPTS (default 3)

Non-healable gates (AI review, security) always require human judgment.
"""

import json
import logging
import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from database.chroma_db import log_to_db
from services.acceptance_gates import run_gates
from services.file_service import BASE_DIR, write_file
from services.llm_service import call_model
from services.test_service import run_syntax_check

logger = logging.getLogger(__name__)

HEALABLE_GATES = {
    "dependency_validation",
    "import_validation",
    "syntax_validation",
    "static_analysis",
    "type_checking",
    "db_migration",
    "runtime_validation",
    "frontend_validation",
    "api_validation",
    "auth_validation",
    "authorization_validation",
    "crud_validation",
    "documentation_validation",
    "docker_validation",
    "deployment_validation",
    "test_validation",
}

MAX_HEALING_ATTEMPTS = int(os.getenv("MAX_HEALING_ATTEMPTS", "3"))
FIX_TIMEOUT = int(os.getenv("HEALING_FIX_TIMEOUT", "600"))
MAX_FIX_FILES = 5


def heal_gates(
    job_id: str,
    model: str = "local",
    review_fn: Callable | None = None,
    max_attempts: int = MAX_HEALING_ATTEMPTS,
) -> dict[str, Any]:
    """Run acceptance gates with self-healing repair loop.

    Returns:
        {
            "passed": bool — True if all gates eventually pass,
            "gates": final gate results,
            "repair_history": list of repair attempts,
            "report_path": path to AUTOFIX_ACCEPTANCE_REPORT.md,
            "iterations": int,
        }
    """
    log_to_db(job_id, "HealingGates", f"Starting self-healing acceptance gates (max {max_attempts} attempts)...")
    t_start = time.monotonic()
    repair_history: list[dict] = []
    gate_results: dict[str, dict] = {}
    passed = False

    for attempt in range(1, max_attempts + 1):
        log_to_db(job_id, "HealingGates", f"Attempt {attempt}/{max_attempts} — running gates...")

        result = run_gates(job_id, model=model, review_fn=review_fn)
        gate_results = result.get("gates", {})
        passed = result.get("passed", False)

        if passed:
            log_to_db(job_id, "HealingGates", f"All gates PASSED on attempt {attempt}")
            break

        if attempt >= max_attempts:
            log_to_db(job_id, "HealingGates", f"Max attempts ({max_attempts}) reached — gates still failing")
            break

        # Identify healable failures
        failed_healable = [
            name for name in HEALABLE_GATES if name in gate_results and not gate_results[name].get("passed", False)
        ]

        if not failed_healable:
            # Only non-healable gates failing (review, security) — stop healing
            log_to_db(job_id, "HealingGates", "Only non-healable gates failing — stopping repair")
            break

        log_to_db(job_id, "HealingGates", f"Attempting repair on: {failed_healable}")

        # Collect failure context
        failure_context = _collect_failure_context(job_id, gate_results, failed_healable)
        if not failure_context:
            log_to_db(job_id, "HealingGates", "No failure details captured — cannot repair")
            break

        # Read project files
        job_dir = (BASE_DIR / job_id).resolve()
        if not job_dir.exists():
            log_to_db(job_id, "HealingGates", "Job directory disappeared — cannot repair", level="ERROR")
            break

        project_files = _read_project_files(job_dir)

        # Build prompt and call LLM
        fixes = _request_fixes(model, failure_context, project_files)
        if not fixes:
            log_to_db(job_id, "HealingGates", "LLM returned no fixes — stopping repair")
            break

        # Apply fixes
        applied = _apply_fixes(job_dir, fixes)

        repair_history.append(
            {
                "attempt": attempt,
                "failed_gates": failed_healable,
                "failure_context": failure_context,
                "changes_requested": fixes,
                "changes_applied": applied,
            }
        )

        # Quick syntax check on modified files
        _syntax_check_applied(job_dir, applied)

        log_to_db(job_id, "HealingGates", f"Applied {len(applied)} fix(es), re-running gates...")

    elapsed_ms = int((time.monotonic() - t_start) * 1000)

    # Write report
    report_path = _write_report(
        job_id,
        {
            "passed": passed,
            "gates": gate_results,
            "repair_history": repair_history,
            "iterations": len(repair_history),
            "max_attempts": max_attempts,
            "elapsed_ms": elapsed_ms,
        },
    )

    if passed:
        log_to_db(job_id, "HealingGates", f"All gates PASSED after {len(repair_history)} repair(s) ({elapsed_ms}ms)")
    else:
        log_to_db(job_id, "HealingGates", f"Gates FAILED after {max_attempts} attempt(s) ({elapsed_ms}ms)")

    return {
        "passed": passed,
        "gates": gate_results,
        "repair_history": repair_history,
        "report_path": report_path,
        "iterations": len(repair_history),
    }


def _collect_failure_context(job_id: str, gate_results: dict, failed_gates: list[str]) -> list[dict]:
    """Extract structured failure details for each failed gate."""
    context = []
    for name in failed_gates:
        gate = gate_results.get(name, {})
        details = gate.get("details", {})
        entry = {"gate": name}

        if "errors" in details:
            entry["errors"] = details["errors"]
        if "issues" in details:
            entry["issues"] = details["issues"]
        if "missing" in details:
            entry["missing"] = details["missing"]
        if "failures" in details:
            entry["test_failures"] = details["failures"]
        if "error" in details and details["error"]:
            entry["error"] = details["error"]
        if "output" in details:
            entry["output"] = details["output"]

        context.append(entry)

    return context


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


def _read_project_files(job_dir: Path) -> dict[str, str]:
    """Read all source files (excluding __pycache__ and binary files)."""
    files = {}
    for path in sorted(job_dir.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        rel = str(path.relative_to(job_dir))
        try:
            files[rel] = path.read_text(encoding="utf-8")
        except Exception:
            pass
    return files


def _request_fixes(model: str, failure_context: list[dict], project_files: dict[str, str]) -> list[dict]:
    """Send failures + project to LLM, parse suggested fixes."""
    context_json = json.dumps(failure_context, indent=2)
    # Build file listing (truncated if too large)
    file_list = "\n".join(f"  {k}  ({len(v)} chars)" for k, v in sorted(project_files.items()))
    # Send truncated files (first 80k chars)
    files_section = ""
    accumulated = 0
    for rel, content in sorted(project_files.items()):
        if accumulated > 80000:
            files_section += (
                f"\n# ... ({len(project_files) - len(files_section.splitlines()) + 1} more files truncated)"
            )
            break
        files_section += f"\n# FILE: {rel}\n{content}\n"
        accumulated += len(content) + len(rel) + 20

    prompt = f"""You are a code repair assistant. The following project failed acceptance gates.

FAILURE CONTEXT:
{context_json}

PROJECT FILES:
{file_list}

PROJECT SOURCE CODE:
{files_section}

For each fix needed, output in this format:

--- FILE: relative/path/to/file.py
--- ACTION: MODIFY
--- CONTENT:
[complete updated file content]
--- END

If the file needs to be created:

--- FILE: relative/path/to/new_file.py
--- ACTION: CREATE
--- CONTENT:
[file content]
--- END

If no changes are needed, output: --- NO CHANGES ---

Rules:
- Fix ONLY the gate failures listed above.
- Every MODIFY must contain the COMPLETE file content, not just the diff.
- Do NOT change test logic — only fix the underlying code.
- Fix import statements that fail to resolve.
- Fix syntax errors.
- Fix test failures by fixing the source code (not the tests).
- Fix packaging issues by creating missing files.
- Fix runtime issues by fixing the code (add missing endpoints, fix imports, etc).
- Return changes ONLY for files that need fixing.
"""

    try:
        response = call_model(prompt, model=model, max_tokens=8192, temperature=0.1, timeout=FIX_TIMEOUT)
        text = (
            response
            if isinstance(response, str)
            else (response.get("text", "") if isinstance(response, dict) else str(response))
        )
    except Exception as exc:
        logger.error("LLM call failed during healing: %s", exc)
        return []

    return _parse_fixes(text)


def _parse_fixes(text: str) -> list[dict]:
    """Parse LLM response into structured fix list."""
    if "--- NO CHANGES ---" in text:
        return []

    fixes = []
    blocks = re.split(r"---\s*FILE\s*:\s*", text)
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.split("\n")
        file_path = lines[0].strip()
        action = "MODIFY"
        content_start = 1

        for i, line in enumerate(lines[1:], 1):
            stripped = line.strip()
            if stripped.startswith("--- ACTION:"):
                action = stripped.split(":", 1)[1].strip()
                content_start = i + 1
            elif stripped.startswith("--- CONTENT:"):
                content_start = i + 1
                break

        content = "\n".join(lines[content_start:]).strip()
        if content.endswith("--- END"):
            content = content[:-6].strip()

        if file_path and content:
            fixes.append(
                {
                    "file": file_path,
                    "action": action.upper(),
                    "content": content,
                }
            )

    return fixes[:MAX_FIX_FILES]


def _apply_fixes(job_dir: Path, fixes: list[dict]) -> list[dict]:
    """Apply parsed fixes to disk. Returns list of applied changes."""
    applied = []
    for fix in fixes:
        file_path = fix["file"]
        action = fix.get("action", "MODIFY")
        content = fix["content"]

        target = (job_dir / file_path).resolve()
        try:
            _ = target.relative_to(job_dir.resolve())
        except ValueError:
            logger.warning("Path traversal blocked: %s", file_path)
            applied.append({"file": file_path, "status": "blocked", "reason": "Path traversal"})
            continue

        if action == "CREATE":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            applied.append({"file": file_path, "status": "created"})
            logger.info("Healing created %s", file_path)
        elif action == "MODIFY":
            if not target.exists():
                logger.warning("Cannot modify non-existent file: %s", file_path)
                applied.append({"file": file_path, "status": "skipped", "reason": "File does not exist"})
                continue
            target.write_text(content, encoding="utf-8")
            applied.append({"file": file_path, "status": "modified"})
            logger.info("Healing modified %s", file_path)
        else:
            applied.append({"file": file_path, "status": "unknown_action", "action": action})

    return applied


def _syntax_check_applied(job_dir: Path, applied: list[dict]):
    """Run syntax check on modified files, log warnings."""
    for change in applied:
        if change["status"] not in ("modified", "created"):
            continue
        target = job_dir / change["file"]
        if target.suffix != ".py":
            continue
        result = run_syntax_check(target)
        if not result.get("valid", False):
            logger.warning("Healing introduced syntax error in %s: %s", change["file"], result.get("error"))
            change["syntax_error"] = result.get("error")


def _write_report(job_id: str, data: dict) -> str | None:
    """Write AUTOFIX_ACCEPTANCE_REPORT.md to project directory."""
    report = _build_report_md(job_id, data)
    path = write_file(job_id, "AUTOFIX_ACCEPTANCE_REPORT.md", report)
    return str(path) if path else None


def _build_report_md(job_id: str, data: dict) -> str:
    now = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    passed = data["passed"]
    gates = data.get("gates", {})
    history = data.get("repair_history", [])
    iterations = data.get("iterations", 0)
    max_attempts = data.get("max_attempts", 3)
    elapsed = data.get("elapsed_ms", 0)

    overall_icon = " PASSED" if passed else " FAILED"
    lines = [
        "# AutoFix Acceptance Report",
        "",
        f"> ProjectPilot · {now} · Job `{job_id}`",
        f"> Self-healing repair: {iterations} iteration(s) of {max_attempts} max",
        "",
        f"## Overall: {overall_icon}",
        "",
        "| Gate | Status | Details |",
        "|------|--------|---------|",
    ]

    for gate_name, gate in gates.items():
        label = gate_name.replace("_", " ").title()
        icon = "" if gate["passed"] else ""
        details = _summary(gate)
        lines.append(f"| {label} | {icon} | {details} |")

    lines += ["", f"**Duration:** {elapsed} ms", ""]

    # Repair history
    if history:
        lines += ["---", "", "## Repair History", ""]
        for entry in history:
            attempt = entry.get("attempt", "?")
            failed = entry.get("failed_gates", [])
            changes = entry.get("changes_applied", [])
            lines += [f"### Attempt {attempt}", ""]
            lines.append(f"**Failed gates:** {', '.join(failed)}")
            if changes:
                lines += ["", "**Changes applied:**", ""]
                for c in changes:
                    status = c.get("status", "?")
                    if status == "modified":
                        icon = ""
                    elif status == "created":
                        icon = " +"
                    elif status == "blocked":
                        icon = " !"
                    else:
                        icon = ""
                    extra = ""
                    if "syntax_error" in c:
                        extra = f" (syntax error: {c['syntax_error']})"
                    if "reason" in c:
                        extra = f" ({c['reason']})"
                    lines.append(f"- {icon} `{c['file']}`{extra}")
                lines.append("")

    # Gate failure details
    failed_gates = {k: v for k, v in gates.items() if not v.get("passed", False)}
    if failed_gates:
        lines += ["---", "", "## Remaining Failures (not auto-healed)", ""]
        for name, gate in failed_gates.items():
            label = name.replace("_", " ").title()
            lines += [f"### {label}", ""]
            details = gate.get("details", {})
            for key, value in details.items():
                if isinstance(value, list) and value:
                    lines += [f"**{key}:**", ""]
                    for item in value:
                        lines.append(f"- {_fmt(item)}")
                    lines.append("")
                elif isinstance(value, str) and value:
                    lines += [f"**{key}:** {value}", ""]

    lines += [
        "---",
        "*ProjectPilot — Self-Healing Acceptance Gates*",
    ]

    return "\n".join(lines)


def _summary(gate: dict) -> str:
    details = gate.get("details", {})
    parts = []
    if "errors" in details and details["errors"]:
        parts.append(f"{len(details['errors'])} error(s)")
    if "issues" in details and details["issues"]:
        parts.append(f"{len(details['issues'])} issue(s)")
    if "missing" in details and details["missing"]:
        parts.append(f"{len(details['missing'])} missing")
    if "verdict" in details:
        parts.append(f"Verdict: {details['verdict']}")
    if "note" in details:
        parts.append(details["note"])
    if "error" in details and details["error"]:
        parts.append(f"Error: {details['error'][:100]}")
    if "skipped" in details and details["skipped"]:
        return "Skipped"
    return "; ".join(parts) if parts else "OK"


def _fmt(item: Any) -> str:
    if isinstance(item, dict):
        return json.dumps(item)
    return str(item)
