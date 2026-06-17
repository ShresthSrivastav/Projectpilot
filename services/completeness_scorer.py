"""Project Completeness Scorer — scores generated projects on 6 dimensions.

Each dimension scores 0-100.  Overall score is weighted average:
  Architecture  (15%)
  Features      (20%)
  Tests         (25%)
  Runtime       (20%)
  Docs          (10%)
  Deployment    (10%)
"""
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from services.file_service import BASE_DIR, write_file
from services.import_validator import validate as validate_imports
from services.packaging_validator import validate as validate_packaging
from services.security_validator import validate as validate_security

logger = logging.getLogger(__name__)

WEIGHTS = {
    "architecture": 0.15,
    "features": 0.20,
    "tests": 0.25,
    "runtime": 0.20,
    "docs": 0.10,
    "deployment": 0.10,
}


def score_project(job_id: str, gate_results: Optional[Dict] = None) -> Dict[str, Any]:
    """Score a generated project on all 6 completeness dimensions."""
    job_dir = (BASE_DIR / job_id).resolve()
    if not job_dir.exists():
        return {"overall": 0, "dimensions": {}, "error": "Job directory not found"}

    dims = {
        "architecture": _score_architecture(job_dir),
        "features": _score_features(job_dir, gate_results),
        "tests": _score_tests(job_dir, gate_results),
        "runtime": _score_runtime(job_dir, gate_results),
        "docs": _score_docs(job_dir),
        "deployment": _score_deployment(job_dir),
    }

    overall = sum(dims[k]["score"] * WEIGHTS[k] for k in dims)
    report = _build_report(job_id, overall, dims)
    write_file(job_id, "COMPLETENESS_REPORT.md", report)
    return {"overall": round(overall, 1), "dimensions": dims}


def _score_architecture(job_dir: Path) -> Dict:
    """Architecture: proper package structure, separation of concerns, imports resolve."""
    score = 0
    details = []

    has_backend = (job_dir / "backend").is_dir()
    has_database = (job_dir / "database").is_dir()
    has_frontend = (job_dir / "frontend").is_dir()
    has_tests = (job_dir / "tests").is_dir()
    has_main = (job_dir / "backend" / "main.py").exists()
    has_models = (job_dir / "database" / "models.py").exists()
    has_crud = (job_dir / "backend" / "crud.py").exists()
    has_init_backend = (job_dir / "backend" / "__init__.py").exists()
    has_init_database = (job_dir / "database" / "__init__.py").exists()

    score += 15 if has_backend else 0
    score += 10 if has_database else 0
    score += 10 if has_frontend else 0
    score += 10 if has_tests else 0
    score += 15 if has_main else 0
    score += 10 if has_models else 0
    score += 10 if has_crud else 0
    score += 10 if has_init_backend else 0
    score += 10 if has_init_database else 0

    details.append(f"backend/: {'yes' if has_backend else 'no'}")
    details.append(f"database/: {'yes' if has_database else 'no'}")
    details.append(f"frontend/: {'yes' if has_frontend else 'no'}")
    details.append(f"tests/: {'yes' if has_tests else 'no'}")
    details.append(f"backend/main.py: {'yes' if has_main else 'no'}")

    return {"score": score, "details": details}


def _score_features(job_dir: Path, gate_results: Optional[Dict]) -> Dict:
    """Features: import validation, security gate, packaging gate results."""
    score = 0
    details = []

    imp = validate_imports(job_dir)
    if imp["passed"]:
        score += 40
    details.append(f"imports: {'pass' if imp['passed'] else 'fail'} ({len(imp['errors'])} errors)")

    sec = validate_security(job_dir)
    if sec["passed"]:
        score += 30
    details.append(f"security: {'pass' if sec['passed'] else 'fail'} ({len(sec['issues'])} issues)")

    pkg = validate_packaging(job_dir)
    if pkg["passed"]:
        score += 30
    details.append(f"packaging: {'pass' if pkg['passed'] else 'fail'} ({len(pkg['missing'])} missing)")

    return {"score": score, "details": details}


def _score_tests(job_dir: Path, gate_results: Optional[Dict]) -> Dict:
    """Test coverage: tests exist, pass, cover real project."""
    score = 0
    details = []
    test_dir = job_dir / "tests"

    if not test_dir.exists() or not any(test_dir.rglob("test_*.py")):
        return {"score": 0, "details": ["No test files found"]}

    score += 20  # tests exist

    test_files = list(test_dir.rglob("test_*.py"))
    score += min(20, len(test_files) * 5)

    test_gate = (gate_results or {}).get("test_validation", {})
    if test_gate.get("passed"):
        score += 40
        details.append("tests pass")
    else:
        failures = test_gate.get("details", {}).get("failures", [])
        details.append(f"tests fail: {len(failures)} failures")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(test_dir), "--co", "-q"],
            capture_output=True, text=True, timeout=30, cwd=str(job_dir),
        )
        collected = sum(1 for line in result.stdout.splitlines() if "test_" in line)
        score += min(20, collected * 2)
        details.append(f"{collected} test(s) collected")
    except Exception:
        details.append("could not collect test count")

    return {"score": min(100, score), "details": details}


def _score_runtime(job_dir: Path, gate_results: Optional[Dict]) -> Dict:
    """Runtime: app starts, health endpoint responds."""
    runtime_gate = (gate_results or {}).get("runtime_validation", {})
    if runtime_gate.get("passed"):
        return {"score": 100, "details": ["App starts, health endpoint responds"]}

    entry_points = ["backend/main.py", "app.py", "main.py", "run.py"]
    for ep in entry_points:
        if (job_dir / ep).exists():
            return {"score": 40, "details": [f"Entry point exists ({ep}) but runtime validation not run or failed"]}

    return {"score": 0, "details": ["No entry point found"]}


def _score_docs(job_dir: Path) -> Dict:
    """Documentation: README, API docs, inline docstrings, project-level docs."""
    score = 0
    details = []

    if (job_dir / "README.md").exists():
        score += 40
        readme_size = (job_dir / "README.md").stat().st_size
        if readme_size > 500:
            score += 10
        details.append(f"README.md ({readme_size} chars)")

    docstring_count = 0
    for py_file in sorted(job_dir.rglob("*.py")):
        text = py_file.read_bytes()
        docstring_count += text.count(b'"""') // 3

    if docstring_count > 0:
        score += min(50, docstring_count * 5)
        details.append(f"{docstring_count} docstrings found")

    return {"score": min(100, score), "details": details}


def _score_deployment(job_dir: Path) -> Dict:
    """Deployment: Dockerfile, start.sh, requirements.txt."""
    score = 0
    details = []

    has_docker = (job_dir / "Dockerfile").exists()
    has_start = (job_dir / "start.sh").exists()
    has_reqs = (job_dir / "requirements.txt").exists()

    if has_docker:
        score += 40
        details.append("Dockerfile present")
    if has_start:
        score += 30
        details.append("start.sh present")
    if has_reqs:
        score += 30
        details.append("requirements.txt present")

    return {"score": score, "details": details}


def _build_report(job_id: str, overall: float, dims: Dict[str, Dict]) -> str:
    now = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    lines = [
        "# Project Completeness Report",
        "",
        f"> ProjectPilot · {now} · Job `{job_id}`",
        "",
        f"## Overall Score: {overall:.1f}/100",
        "",
        "| Dimension | Score | Weight | Weighted |",
        "|-----------|-------|--------|----------|",
    ]
    for dim, data in dims.items():
        w = WEIGHTS[dim]
        ws = round(data["score"] * w, 1)
        lines.append(f"| {dim.title()} | {data['score']}/100 | {w*100:.0f}% | {ws} |")

    lines += ["", "### Details", ""]
    for dim, data in dims.items():
        if data["details"]:
            lines.append(f"**{dim.title()}:** " + "; ".join(data["details"]))

    lines += [
        "",
        "---",
        "*ProjectPilot — Completeness Scorer*",
    ]
    return "\n".join(lines)
