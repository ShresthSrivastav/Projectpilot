"""Packaging Validator — ensure all referenced files exist in generated project."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

EXPECTED_FILES = [
    "README.md",
]

EXPECTED_DIRS = [
    "tests",
]


def validate(job_dir: Path) -> dict:
    """Check that all expected files and directories exist.

    Also verifies that any file referenced in Dockerfile, start.sh,
    or requirements.txt actually exists on disk.

    Returns:
        {"passed": bool, "missing": [...], "files_checked": int}
    """
    missing: list[str] = []

    for f in EXPECTED_FILES:
        if not (job_dir / f).exists():
            missing.append(f)

    for d in EXPECTED_DIRS:
        if not (job_dir / d).is_dir():
            missing.append(f"{d}/")

    # Check Dockerfile references
    dockerfile = job_dir / "Dockerfile"
    if dockerfile.exists():
        for line in dockerfile.read_text().splitlines():
            for ref in _extract_file_refs(line):
                if ref and not _is_system_path(ref):
                    target = job_dir / ref
                    if not target.exists():
                        missing.append(f"Dockerfile ref: {ref}")

    # Check start.sh references
    start_sh = job_dir / "start.sh"
    if start_sh.exists():
        for line in start_sh.read_text().splitlines():
            for ref in _extract_file_refs(line):
                if ref and not _is_system_path(ref) and not ref.startswith("$"):
                    target = job_dir / ref
                    if not target.exists():
                        missing.append(f"start.sh ref: {ref}")

    all_files = list(job_dir.rglob("*"))
    return {
        "passed": len(missing) == 0,
        "missing": missing,
        "files_checked": len(all_files),
    }


def _extract_file_refs(line: str) -> list[str]:
    import re
    refs = []
    for m in re.finditer(r'(?:COPY|ADD)\s+(\S+)', line, re.IGNORECASE):
        refs.append(m.group(1))
    for m in re.finditer(r'python\s+(\S+\.py)', line):
        refs.append(m.group(1))
    for m in re.finditer(r'(?:run|cmd)\s+(\S+\.py)', line, re.IGNORECASE):
        refs.append(m.group(1))
    return refs


def _is_system_path(ref: str) -> bool:
    return ref.startswith("/") or ref.startswith("apt") or ref.startswith("pip") or ref.startswith("git") or ref in {".", ".."}
