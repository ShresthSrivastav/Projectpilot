"""Test service — syntax validation and pytest runner."""
import logging, os, py_compile, subprocess, re
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)
BASE_DIR = Path(os.getenv("GENERATED_PROJECTS_DIR", "./generated_projects"))

def run_syntax_check(file_path: Path) -> Dict[str, Any]:
    try:
        py_compile.compile(str(file_path), doraise=True)
        return {"valid": True, "error": None}
    except py_compile.PyCompileError as exc:
        return {"valid": False, "error": str(exc)}
    except Exception as exc:
        return {"valid": False, "error": f"Unexpected: {exc}"}

def run_pytest(job_id: str) -> Dict[str, Any]:
    project_dir = (BASE_DIR / job_id).resolve()
    if not project_dir.exists():
        return {"passed": False, "output": "Test dir not found", "failures": [], "collected": 0}
    try:
        r = subprocess.run(["python", "-m", "pytest", ".", "-v", "--tb=short", "--no-header"],
            capture_output=True, text=True, timeout=60, cwd=str(project_dir))
        out = r.stdout + r.stderr
        collected = _parse_collected(out)
        return {
            "passed": r.returncode == 0,
            "output": out,
            "failures": parse_traceback(out) if r.returncode != 0 else [],
            "collected": collected,
        }
    except subprocess.TimeoutExpired:
        return {"passed": False, "output": "pytest timed out.", "failures": [], "collected": 0}
    except Exception as exc:
        return {"passed": False, "output": str(exc), "failures": [], "collected": 0}


def _parse_collected(output: str) -> int:
    import re
    m = re.search(r"collected (\d+) items?", output)
    if m:
        return int(m.group(1))
    if "no tests ran" in output:
        return 0
    if "ERROR collecting" in output:
        return -1  # signal: import/collection error
    return 0

def parse_traceback(output: str) -> List[Dict[str, Any]]:
    failures = []
    for m in re.finditer(r"FAILED (.+?) - (.+)", output):
        failures.append({"file": m.group(1).strip(), "line": 0, "error": m.group(2).strip()})
    if not failures:
        for m in re.finditer(r'File "([^"]+)", line (\d+)', output):
            failures.append({"file": m.group(1).strip(), "line": int(m.group(2)), "error": "See traceback"})
    return failures
