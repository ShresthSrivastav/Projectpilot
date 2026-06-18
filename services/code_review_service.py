"""Code Review Service — multi-agent code review with parallel reviewers."""
import logging
import threading
from pathlib import Path
from typing import Any

from database.chroma_db import log_to_db
from services.file_service import BASE_DIR, list_files

logger = logging.getLogger(__name__)


def _quality_review(file_path: Path, content: str) -> list[dict[str, Any]]:
    findings = []
    lines = content.splitlines()

    has_docstrings = False
    has_type_hints = False
    has_error_handling = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(('"""', "'''", '"""')):
            has_docstrings = True
        if ":" in stripped and "def " in stripped and "->" in stripped:
            has_type_hints = True
        if "try:" in stripped or "except" in stripped:
            has_error_handling = True

    if not has_docstrings and len(lines) > 5:
        findings.append({
            "reviewer": "quality",
            "severity": "LOW",
            "file": str(file_path.name),
            "finding": "Missing docstrings",
            "recommendation": "Add module-level and function-level docstrings",
        })
    if not has_type_hints and len([l for l in lines if "def " in l]) > 0:
        findings.append({
            "reviewer": "quality",
            "severity": "MEDIUM",
            "file": str(file_path.name),
            "finding": "Missing type hints",
            "recommendation": "Add type hints to all function signatures",
        })
    if not has_error_handling and len(lines) > 20:
        findings.append({
            "reviewer": "quality",
            "severity": "LOW",
            "file": str(file_path.name),
            "finding": "No error handling (try/except)",
            "recommendation": "Wrap I/O and external calls in try/except blocks",
        })

    long_lines = [(i + 1, l) for i, l in enumerate(lines) if len(l) > 100]
    for line_no, line in long_lines[:3]:
        findings.append({
            "reviewer": "quality",
            "severity": "LOW",
            "file": str(file_path.name),
            "finding": f"Line too long ({len(line)} chars)",
            "recommendation": f"Break line {line_no} into multiple lines",
            "line": line_no,
        })

    if "print(" in content and file_path.name != "__init__.py":
        findings.append({
            "reviewer": "quality",
            "severity": "LOW",
            "file": str(file_path.name),
            "finding": "Using print() instead of logging",
            "recommendation": "Replace print() with logger.info()",
        })

    return findings


def _security_review(file_path: Path, content: str) -> list[dict[str, Any]]:
    findings = []
    patterns = {
        "SQL injection risk": ["execute(", "cursor.", "raw_sql"],
        "Hardcoded secret": ["API_KEY", "SECRET", "PASSWORD", "api_key"],
        "eval/exec usage": ["eval(", "exec("],
        "Pickle deserialization": ["pickle.loads", "pickle.load"],
        "Debug enabled": ["debug=True", "DEBUG=True"],
    }
    for finding, keywords in patterns.items():
        for i, line in enumerate(content.splitlines(), 1):
            for kw in keywords:
                if kw in line and not line.strip().startswith("#"):
                    findings.append({
                        "reviewer": "security",
                        "severity": "HIGH" if kw in ("execute(", "eval(", "exec(", "pickle.") else "MEDIUM",
                        "file": str(file_path.name),
                        "finding": finding,
                        "recommendation": f"Review and sanitize at line {i}",
                        "line": i,
                    })
                    break
            if len(findings) > 10:
                break
    return findings


def run(
    job_id: str,
    generated_files: list[str] | None = None,
    model: str = "local",
) -> dict[str, Any]:
    log_to_db(job_id, "CodeReviewService", "Starting multi-agent code review.")
    all_files = list_files(job_id)
    py_files = [f for f in all_files if str(f).endswith(".py")]

    all_findings: list[dict[str, Any]] = []
    lock = threading.Lock()

    def _run_reviewer(reviewer_func):
        local_findings = []
        for f in py_files:
            try:
                content = f.read_text(encoding="utf-8")
                local_findings.extend(reviewer_func(f, content))
            except Exception:
                pass
        with lock:
            all_findings.extend(local_findings)

    quality_thread = threading.Thread(target=_run_reviewer, args=(_quality_review,), daemon=True)
    security_thread = threading.Thread(target=_run_reviewer, args=(_security_review,), daemon=True)

    quality_thread.start()
    security_thread.start()
    quality_thread.join(timeout=60)
    security_thread.join(timeout=60)

    severity_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for f in all_findings:
        sev = f.get("severity", "LOW")
        if sev in severity_counts:
            severity_counts[sev] += 1

    log_to_db(job_id, "CodeReviewService",
              f"Review complete: {len(all_findings)} finding(s) "
              f"({severity_counts['HIGH']} high, {severity_counts['MEDIUM']} medium, {severity_counts['LOW']} low).")

    project_dir = (BASE_DIR / job_id).resolve()
    report_path = project_dir / "CODE_REVIEW.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Code Review Report\n\n",
             f"**Files reviewed:** {len(py_files)}\n",
             f"**Findings:** {len(all_findings)}\n\n",
             "## Severity Summary\n\n| Severity | Count |\n|----------|-------|\n"]
    for sev in ("HIGH", "MEDIUM", "LOW"):
        lines.append(f"| {sev} | {severity_counts[sev]} |\n")
    lines.append("\n## Findings\n\n")
    for idx, f in enumerate(all_findings, 1):
        lines.append(f"### {idx}. [{f.get('reviewer','').upper()}] {f['finding']} ({f['severity']})\n")
        lines.append(f"- **File:** `{f['file']}`")
        if f.get("line"):
            lines.append(f":{f['line']}")
        lines.append("\n")
        lines.append(f"- **Recommendation:** {f['recommendation']}\n\n")

    report_path.write_text("".join(lines), encoding="utf-8")
    log_to_db(job_id, "CodeReviewService", "Report written: CODE_REVIEW.md")

    return {
        "report_file": "CODE_REVIEW.md",
        "findings": all_findings,
        "high": severity_counts["HIGH"],
        "medium": severity_counts["MEDIUM"],
        "low": severity_counts["LOW"],
        "total": len(all_findings),
    }
