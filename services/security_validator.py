"""Security Validator — detect hardcoded secrets, wildcard CORS, dangerous patterns."""

import logging
import re
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)

# Patterns that indicate hardcoded secrets
SECRET_PATTERNS: List[re.Pattern] = [
    re.compile(r'(?i)(api[_-]?key|secret|password|token|credential)\s*[=:]\s*["\'][^"\']+["\']'),
    re.compile(r'(?i)aws_access_key_id\s*[=:]\s*["\'][^"\']+["\']'),
    re.compile(r'(?i)aws_secret_access_key\s*[=:]\s*["\'][^"\']+["\']'),
    re.compile(r'(?i)sk-[a-zA-Z0-9]{20,}'),       # OpenAI-style keys
    re.compile(r'(?i)ghp_[a-zA-Z0-9]{36}'),          # GitHub PAT
]

# Danger patterns that should never appear in generated code
DANGEROUS_PATTERNS: List[re.Pattern] = [
    re.compile(r'\beval\s*\('),
    re.compile(r'\bexec\s*\('),
    re.compile(r'__import__\s*\('),
    re.compile(r'(?i)subprocess\.(call|popen|run)\s*\(.*shell\s*=\s*True'),
    re.compile(r'(?i)os\.system\s*\('),
    re.compile(r'(?i)pickle\.loads?\s*\('),
]

# Wildcard CORS patterns
CORS_PATTERNS: List[re.Pattern] = [
    re.compile(r'allow_origins\s*=\s*\[?\s*["\']\*["\']'),
    re.compile(r'Access-Control-Allow-Origin:\s*\*'),
]

# Files to skip (auto-generated or third-party)
SKIP_DIRS = {"__pycache__", ".venv", "venv", "node_modules", ".git", "migrations"}


def validate(job_dir: Path) -> Dict:
    """Scan generated project for security issues.

    Returns:
        {"passed": bool, "issues": [...], "files_scanned": int}
    """
    issues: List[str] = []
    files_scanned = 0

    for py_file in sorted(job_dir.rglob("*.py")):
        if any(part in SKIP_DIRS for part in py_file.parts):
            continue
        files_scanned += 1
        rel = str(py_file.relative_to(job_dir))
        text = py_file.read_text(encoding="utf-8", errors="ignore")

        for pattern in SECRET_PATTERNS:
            for m in pattern.finditer(text):
                issues.append(f"[{rel}] Hardcoded secret: `{m.group()[:60]}...`")

        for pattern in DANGEROUS_PATTERNS:
            for m in pattern.finditer(text):
                snippet = text[max(0, m.start()-20):m.end()+20]
                issues.append(f"[{rel}] Dangerous pattern: `{pattern.pattern}`  —  `{snippet.strip()}`")

        for pattern in CORS_PATTERNS:
            for m in pattern.finditer(text):
                issues.append(f"[{rel}] Wildcard CORS: `{m.group()}`")

    # Check requirements.txt for dangerous packages
    req_file = job_dir / "requirements.txt"
    if req_file.exists():
        for line in req_file.read_text().splitlines():
            stripped = line.strip().lower()
            if stripped and not stripped.startswith("#"):
                for dangerous in _DANGEROUS_PACKAGES:
                    if dangerous in stripped:
                        issues.append(f"[requirements.txt] Dangerous package reference: `{line.strip()}`")

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "files_scanned": files_scanned,
    }


_DANGEROUS_PACKAGES = {
    "weasyprint", "selenium", "playwright", "scrapy",
}
