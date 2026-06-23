"""Runtime Repair Service — auto-repairs startup failures in generated projects.

Strategy:
  1. Install dependencies
  2. Start app in isolated subprocess
  3. Poll /health endpoint
  4. If failed, parse error output
  5. Apply targeted fixes (missing imports, config, env vars)
  6. Re-run until passing or retry budget exhausted
"""

import logging
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from database.chroma_db import log_to_db
from services.file_service import BASE_DIR
from services.llm_service import call_model

logger = logging.getLogger(__name__)

MAX_RUNTIME_REPAIR_ATTEMPTS = 3
STARTUP_TIMEOUT = 30
HEALTH_POLL_INTERVAL = 2
HEALTH_MAX_POLLS = 15


def validate_runtime(job_dir: Path, timeout: int = 30) -> dict[str, Any]:
    """Start the generated app and verify /health endpoint responds.

    Returns:
        {"passed": bool, "error": str | None, "output": str}
    """
    # Find entry point
    main_py = job_dir / "backend" / "main.py"
    if not main_py.exists():
        return {"passed": False, "error": "backend/main.py not found", "output": ""}

    # Find available port
    port = _find_free_port()
    log_to_db("", "RuntimeRepair", f"Starting app on port {port}...")

    env = os.environ.copy()
    env["BACKEND_PORT"] = str(port)
    env["SKIP_RUNTIME_VALIDATION"] = "false"

    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.main:app",
             "--host", "127.0.0.1", "--port", str(port)],
            cwd=str(job_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
        )
    except FileNotFoundError:
        return {"passed": False, "error": "uvicorn not found", "output": ""}
    except Exception as exc:
        return {"passed": False, "error": str(exc), "output": ""}

    output_lines: list[str] = []
    t_start = time.monotonic()

    try:
        while time.monotonic() - t_start < timeout:
            ret = proc.poll()
            if ret is not None:
                # Process exited — capture remaining output
                stdout, stderr = proc.communicate(timeout=5)
                output_lines.append(stdout or "")
                output_lines.append(stderr or "")
                full_output = "\n".join(output_lines)
                error_msg = _parse_startup_error(full_output)
                return {"passed": False, "error": error_msg, "output": full_output}

            # Check health
            try:
                import urllib.request
                import json
                url = f"http://127.0.0.1:{port}/health"
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=3) as resp:
                    if resp.status == 200:
                        body = json.loads(resp.read().decode())
                        proc.terminate()
                        proc.wait(timeout=5)
                        return {"passed": True, "error": None, "output": "\n".join(output_lines), "health": body, "port": port}
            except Exception:
                pass

            time.sleep(HEALTH_POLL_INTERVAL)

        # Timeout
        proc.terminate()
        try:
            stdout, stderr = proc.communicate(timeout=5)
            output_lines.append(stdout or "")
            output_lines.append(stderr or "")
        except subprocess.TimeoutExpired:
            proc.kill()
            output_lines.append("<killed after timeout>")

        full_output = "\n".join(output_lines)
        return {"passed": False, "error": "App did not start within timeout", "output": full_output}

    except Exception as exc:
        try:
            proc.terminate()
        except Exception:
            pass
        return {"passed": False, "error": str(exc), "output": "\n".join(output_lines)}


def auto_repair_runtime(
    job_dir: Path,
    job_id: str,
    model: str = "local",
) -> dict[str, Any]:
    """Auto-repair runtime startup failures.

    Returns:
        {
            "success": bool,
            "repairs_applied": list[str],
            "attempts": int,
            "validation_result": dict,
        }
    """
    log_to_db(job_id, "RuntimeRepair", "Starting runtime repair...")
    repairs_applied: list[str] = []

    for attempt in range(1, MAX_RUNTIME_REPAIR_ATTEMPTS + 1):
        log_to_db(job_id, "RuntimeRepair", f"Runtime validation attempt {attempt}")

        # Install dependencies first
        _install_deps(job_dir, job_id)

        result = validate_runtime(job_dir)
        if result["passed"]:
            log_to_db(job_id, "RuntimeRepair", f"Runtime OK after {attempt} attempt(s)")
            return {
                "success": True,
                "repairs_applied": repairs_applied,
                "attempts": attempt,
                "validation_result": result,
            }

        error = result.get("error", "Unknown error")
        output = result.get("output", "")
        log_to_db(job_id, "RuntimeRepair", f"Attempt {attempt} failed: {error}", "WARNING")

        if attempt >= MAX_RUNTIME_REPAIR_ATTEMPTS:
            break

        # Analyze failure and apply fix
        fix = _analyze_and_fix(job_dir, error, output, job_id, model)
        if fix:
            repairs_applied.append(fix)
            log_to_db(job_id, "RuntimeRepair", f"Applied fix: {fix}")
        else:
            log_to_db(job_id, "RuntimeRepair", "No fix generated, trying pip install...", "WARNING")
            _install_deps(job_dir, job_id, force=True)

    final_result = validate_runtime(job_dir)
    log_to_db(job_id, "RuntimeRepair",
              f"Runtime repair {'succeeded' if final_result['passed'] else 'failed'} "
              f"after {MAX_RUNTIME_REPAIR_ATTEMPTS} attempt(s)")

    return {
        "success": final_result["passed"],
        "repairs_applied": repairs_applied,
        "attempts": MAX_RUNTIME_REPAIR_ATTEMPTS,
        "validation_result": final_result,
    }


def _find_free_port() -> int:
    """Find an available TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _parse_startup_error(output: str) -> str:
    """Extract the most relevant error message from startup output."""
    # Look for traceback
    tb_match = re.search(r"Traceback.*?Error[^]*?(?:\n\n|\Z)", output, re.DOTALL)
    if tb_match:
        lines = tb_match.group(0).strip().split("\n")
        # Return last few lines
        return "\n".join(lines[-3:])

    # Look for common error patterns
    for pattern in [
        r"ModuleNotFoundError:.*",
        r"ImportError:.*",
        r"SyntaxError:.*",
        r"AttributeError:.*",
        r"TypeError:.*",
        r"ValueError:.*",
        r"KeyError:.*",
        r"OSError:.*",
        r"RuntimeError:.*",
        r"ConnectionError:.*",
        r"TimeoutError:.*",
        r"Error:.*",
    ]:
        match = re.search(pattern, output)
        if match:
            return match.group(0)[:200]

    return output[-300:]


def _install_deps(job_dir: Path, job_id: str, force: bool = False) -> bool:
    """Install project dependencies."""
    req_file = job_dir / "requirements.txt"
    if not req_file.exists():
        return False

    try:
        log_to_db(job_id, "RuntimeRepair", "Installing dependencies...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(req_file)],
            capture_output=True, text=True, timeout=120,
            cwd=str(job_dir),
        )
        if result.returncode == 0:
            log_to_db(job_id, "RuntimeRepair", "Dependencies installed")
            return True
        else:
            log_to_db(job_id, "RuntimeRepair",
                      f"pip install warnings: {result.stderr[-200:]}", "WARNING")
            return False
    except subprocess.TimeoutExpired:
        log_to_db(job_id, "RuntimeRepair", "pip install timed out", "WARNING")
        return False
    except Exception as exc:
        log_to_db(job_id, "RuntimeRepair", f"pip install failed: {exc}", "WARNING")
        return False


def _analyze_and_fix(
    job_dir: Path,
    error: str,
    output: str,
    job_id: str,
    model: str,
) -> str | None:
    """Analyze startup error and apply targeted fix."""
    # Check for module import errors
    mod_match = re.search(r"(?:ModuleNotFoundError|ImportError):\s*(?:No module named\s+)?['\"]?(\w+)['\"]?", error)
    if mod_match:
        missing_mod = mod_match.group(1)
        # Try installing the missing module
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", missing_mod],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                log_to_db(job_id, "RuntimeRepair", f"Installed missing module: {missing_mod}")
                return f"pip_install:{missing_mod}"
        except Exception:
            pass

    # Check for database issues
    if "sqlite" in error.lower() or "database" in error.lower():
        # Ensure the data directory exists
        data_dir = job_dir / "data"
        data_dir.mkdir(exist_ok=True)
        return f"created:{data_dir.relative_to(job_dir)}"

    # Check for missing environment variables
    env_match = re.search(r"(?:environ|env|environment)\s+['\"]?(\w+)['\"]?", error, re.IGNORECASE)
    if env_match:
        var_name = env_match.group(1)
        # Create .env with default value
        env_file = job_dir / ".env"
        with open(env_file, "a") as f:
            f.write(f"{var_name}=default\n")
        log_to_db(job_id, "RuntimeRepair", f"Added env var: {var_name}")
        return f"env:{var_name}"

    # Try LLM-based fix for complex errors
    try:
        prompt = (
            f"The following Python project failed to start:\n\n"
            f"ERROR: {error[:500]}\n\n"
            f"OUTPUT:\n{output[-1500:]}\n\n"
            f"Analyze the error and suggest a specific fix. "
            f"Output ONLY the fix instruction, one of:\n"
            f"  - INSTALL: <package_name>\n"
            f"  - PATCH: <file_path>|<complete_new_content>\n"
            f"  - CONFIG: <variable>=<value>\n"
            f"  - IGNORE: <explanation>\n"
        )
        response = call_model(prompt, model=model, job_id=job_id, agent="RuntimeRepair")
        response = response.strip()

        if response.startswith("INSTALL:"):
            pkg = response.split(":", 1)[1].strip()
            subprocess.run([sys.executable, "-m", "pip", "install", pkg],
                           capture_output=True, text=True, timeout=60)
            return f"llm_install:{pkg}"

        elif response.startswith("PATCH:"):
            parts = response.split(":", 1)[1].strip().split("|", 1)
            if len(parts) == 2:
                file_path, content = parts
                target = job_dir / file_path.strip()
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content.strip())
                return f"llm_patch:{file_path.strip()}"

        elif response.startswith("CONFIG:"):
            config = response.split(":", 1)[1].strip()
            env_file = job_dir / ".env"
            with open(env_file, "a") as f:
                f.write(f"{config}\n")
            return f"llm_config:{config}"

    except Exception as exc:
        logger.warning("LLM runtime fix failed: %s", exc)

    return None
