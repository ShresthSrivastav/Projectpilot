"""Generation Verifier — validates LLM output completeness before accepting.

Detects:
  - Truncated files (calls `_gen()` but stops mid-function)
  - Placeholder code (TODO, pass, NotImplementedError, FIXME)
  - Empty or near-empty files
  - Missing imports/references to planned modules
  - Incomplete route implementations
"""

import ast
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PLACEHOLDER_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bTODO\b"),
    re.compile(r"\bFIXME\b"),
    re.compile(r"\bNotImplementedError\b"),
    re.compile(r"^\s+pass\s*$", re.MULTILINE),
    re.compile(r"^\s+return\s+None\s*$", re.MULTILINE),
    re.compile(r"^\s+return\s+''\s*$", re.MULTILINE),
    re.compile(r"^\s+return\s+\[\]\s*$", re.MULTILINE),
    re.compile(r"^\s+return\s+\{\}\s*$", re.MULTILINE),
    re.compile(r"raise\s+NotImplementedError"),
    re.compile(r"#\s+TODO"),
    re.compile(r"#\s+FIXME"),
    re.compile(r"#\s+HACK"),
    re.compile(r"#\s+XXX"),
]

TRUNCATION_PATTERNS: list[re.Pattern] = [
    re.compile(r"\.\.\.\s*$", re.MULTILINE),
    re.compile(r"#\s*(more|continued|truncated|\.\.\.)", re.IGNORECASE),
    re.compile(r"\[\s*(remaining|more|continued)\s+code", re.IGNORECASE),
    re.compile(r"```\s*\w*\s*$", re.MULTILINE),
    re.compile(r"<!--\s*(remaining|more).*-->", re.IGNORECASE),
    re.compile(r"/\*\s*(remaining|more).*\*/", re.IGNORECASE),
]

MIN_FILE_LENGTHS: dict[str, int] = {
    "backend/main.py": 200,
    "database/models.py": 150,
    "backend/crud.py": 100,
    "frontend/app.py": 100,
    "requirements.txt": 20,
    "Dockerfile": 50,
    "start.sh": 30,
    "database/db.py": 50,
}


def verify_file(
    file_path: Path,
    relative_path: str,
    planned_routes: list[dict] | None = None,
    planned_tables: list[dict] | None = None,
) -> dict[str, Any]:
    """Verify a single generated file for completeness.

    Returns:
        {
            "valid": bool,
            "truncated": bool,
            "placeholder_functions": list[str],
            "missing_routes": list[str],
            "missing_tables": list[str],
            "syntax_valid": bool,
            "syntax_error": str | None,
            "issues": list[str],
        }
    """
    issues: list[str] = []
    result: dict[str, Any] = {
        "valid": True,
        "truncated": False,
        "placeholder_functions": [],
        "missing_routes": [],
        "missing_tables": [],
        "syntax_valid": True,
        "syntax_error": None,
        "issues": issues,
    }

    if not file_path.exists():
        result["valid"] = False
        issues.append(f"File does not exist: {relative_path}")
        return result

    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        result["valid"] = False
        issues.append(f"Cannot read file: {exc}")
        return result

    # Check minimum length
    min_len = _get_min_length(relative_path)
    if len(text.strip()) < min_len:
        result["valid"] = False
        issues.append(f"File too short ({len(text.strip())} chars, min {min_len})")

    # Check truncation
    for pattern in TRUNCATION_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            result["truncated"] = True
            result["valid"] = False
            issues.append(f"Truncation pattern detected: '{pattern.pattern[:60]}'")
            break

    # Check placeholders
    for pattern in PLACEHOLDER_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            for match in matches[:3]:
                result["placeholder_functions"].append(match[:80])
            result["valid"] = False
            issues.append(f"Placeholder detected ({len(matches)} matches for '{pattern.pattern[:40]}')")
            break

    # Check syntax for .py files
    if relative_path.endswith(".py"):
        try:
            ast.parse(text, filename=relative_path)
        except SyntaxError as exc:
            result["syntax_valid"] = False
            result["valid"] = False
            result["syntax_error"] = str(exc)
            issues.append(f"Syntax error: {exc}")

    # Check route coverage for backend/main.py
    if relative_path == "backend/main.py" and planned_routes:
        missing = _check_missing_routes(text, planned_routes)
        result["missing_routes"] = missing
        if missing:
            result["valid"] = False
            issues.append(f"Missing {len(missing)} planned route(s): {missing}")

    # Check table coverage for database/models.py
    if relative_path == "database/models.py" and planned_tables:
        missing = _check_missing_tables(text, planned_tables)
        result["missing_tables"] = missing
        if missing:
            result["valid"] = False
            issues.append(f"Missing {len(missing)} planned table(s): {missing}")

    return result


def verify_all_files(
    job_dir: Path,
    generated_files: list[str],
    planned_routes: list[dict] | None = None,
    planned_tables: list[dict] | None = None,
) -> dict[str, Any]:
    """Verify all generated files. Returns aggregate result."""
    results: dict[str, dict] = {}
    all_valid = True
    total_issues = 0

    for rel_path in generated_files:
        fpath = job_dir / rel_path
        vr = verify_file(fpath, rel_path, planned_routes, planned_tables)
        results[rel_path] = vr
        if not vr["valid"]:
            all_valid = False
            total_issues += len(vr["issues"])

    return {
        "all_valid": all_valid,
        "total_issues": total_issues,
        "files_checked": len(generated_files),
        "files_invalid": sum(1 for v in results.values() if not v["valid"]),
        "results": results,
    }


def detect_truncated(text: str) -> bool:
    """Quick check if LLM response was truncated."""
    return any(p.search(text) for p in TRUNCATION_PATTERNS)


def detect_placeholder_code(text: str) -> list[str]:
    """Find placeholder patterns in generated code."""
    found = []
    for pattern in PLACEHOLDER_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            found.extend(matches[:5])
    return found


def _get_min_length(relative_path: str) -> int:
    for key, val in MIN_FILE_LENGTHS.items():
        if relative_path.endswith(key):
            return val
    return 50


def _check_missing_routes(text: str, planned_routes: list[dict]) -> list[str]:
    """Check which planned routes are missing from generated main.py."""
    missing = []
    for route in planned_routes:
        method = route.get("method", "GET").lower()
        path = route.get("path", "/")
        # Check for route decorator pattern
        route_pattern = re.compile(
            rf'@(?:app|router)\.{method}\s*\(\s*["\'].*?{re.escape(path)}["\']',
            re.IGNORECASE,
        )
        if not route_pattern.search(text):
            # Also check path in string literals
            if path not in text and path != "/health":
                missing.append(f"{method.upper()} {path}")
    return missing


def _check_missing_tables(text: str, planned_tables: list[dict]) -> list[str]:
    """Check which planned tables are missing from generated models.py."""
    missing = []
    for table in planned_tables:
        name = table.get("name", "")
        if not name:
            continue
        class_pattern = re.compile(rf"class\s+{re.escape(name)}\s*\(", re.IGNORECASE)
        if not class_pattern.search(text):
            missing.append(name)
    return missing
