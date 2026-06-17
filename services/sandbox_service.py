"""Docker Sandbox Service — safe code execution in isolated containers.

Supports:
- Running Python scripts with resource limits (CPU, memory, timeout)
- Installing dependencies before execution
- Capturing stdout/stderr
- Cleanup after execution
"""
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SANDBOX_IMAGE = os.getenv("SANDBOX_IMAGE", "python:3.11-slim")
SANDBOX_TIMEOUT = int(os.getenv("SANDBOX_TIMEOUT", "60"))
SANDBOX_MEMORY = os.getenv("SANDBOX_MEMORY", "256m")
SANDBOX_CPU = os.getenv("SANDBOX_CPU", "0.5")
DOCKER_AVAILABLE = None


def _check_docker() -> bool:
    global DOCKER_AVAILABLE
    if DOCKER_AVAILABLE is not None:
        return DOCKER_AVAILABLE
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True, text=True, timeout=10,
        )
        DOCKER_AVAILABLE = result.returncode == 0
    except Exception:
        DOCKER_AVAILABLE = False
    if not DOCKER_AVAILABLE:
        logger.warning("Docker is not available. Sandbox will use subprocess fallback.")
    return DOCKER_AVAILABLE


def is_available() -> bool:
    return _check_docker()


def run_python(
    code: str,
    requirements: Optional[List[str]] = None,
    timeout: int = SANDBOX_TIMEOUT,
    memory: str = SANDBOX_MEMORY,
    cpus: str = SANDBOX_CPU,
) -> Dict[str, Any]:
    if _check_docker():
        return _run_docker(code, requirements, timeout, memory, cpus)
    return _run_subprocess(code, requirements, timeout)


def _run_docker(
    code: str,
    requirements: Optional[List[str]],
    timeout: int,
    memory: str,
    cpus: str,
) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="sandbox_") as tmpdir:
        tmp_path = Path(tmpdir)

        script_path = tmp_path / "script.py"
        script_path.write_text(code, encoding="utf-8")

        dockerfile_lines = [f"FROM {SANDBOX_IMAGE}", "WORKDIR /app"]
        if requirements:
            req_path = tmp_path / "requirements.txt"
            req_path.write_text("\n".join(requirements), encoding="utf-8")
            dockerfile_lines.append("COPY requirements.txt .")
            dockerfile_lines.append("RUN pip install --no-cache-dir -r requirements.txt")
        dockerfile_lines.append("COPY script.py .")
        dockerfile_lines.append("CMD [\"python\", \"script.py\"]")
        dockerfile_path = tmp_path / "Dockerfile"
        dockerfile_path.write_text("\n".join(dockerfile_lines), encoding="utf-8")

        import uuid
        container_tag = f"sandbox_{uuid.uuid4().hex[:12]}"

        try:
            build = subprocess.run(
                ["docker", "build", "-t", container_tag, "."],
                capture_output=True, text=True, timeout=timeout + 30,
                cwd=tmpdir,
            )
            if build.returncode != 0:
                return {
                    "success": False,
                    "stdout": build.stdout[-2000:],
                    "stderr": build.stderr[-2000:],
                    "duration_ms": int((time.monotonic() - t0) * 1000),
                    "error": f"Build failed: {build.stderr[-500:]}",
                }

            run = subprocess.run(
                ["docker", "run", "--rm",
                 f"--memory={memory}",
                 f"--cpus={cpus}",
                 "--network=none",
                 "--pids-limit=50",
                 "--read-only",
                 container_tag],
                capture_output=True, text=True, timeout=timeout,
            )

            return {
                "success": run.returncode == 0,
                "stdout": run.stdout[-5000:],
                "stderr": run.stderr[-5000:],
                "returncode": run.returncode,
                "duration_ms": int((time.monotonic() - t0) * 1000),
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Execution timed out after {timeout}s",
                "duration_ms": int((time.monotonic() - t0) * 1000),
                "error": "timeout",
            }
        except FileNotFoundError:
            return {
                "success": False,
                "error": "docker command not found",
                "duration_ms": int((time.monotonic() - t0) * 1000),
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc)[:500],
                "duration_ms": int((time.monotonic() - t0) * 1000),
            }
        finally:
            try:
                subprocess.run(
                    ["docker", "rmi", "-f", container_tag],
                    capture_output=True, text=True, timeout=30,
                )
            except Exception:
                pass


def _run_subprocess(
    code: str,
    requirements: Optional[List[str]],
    timeout: int,
) -> Dict[str, Any]:
    t0 = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="sandbox_") as tmpdir:
        tmp_path = Path(tmpdir)
        script_path = tmp_path / "script.py"
        script_path.write_text(code, encoding="utf-8")

        if requirements:
            req_path = tmp_path / "requirements.txt"
            req_path.write_text("\n".join(requirements), encoding="utf-8")
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r", str(req_path)],
                    capture_output=True, text=True, timeout=timeout,
                    cwd=tmpdir,
                )
            except Exception as exc:
                logger.warning("pip install in sandbox failed: %s", exc)

        try:
            run = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True, text=True, timeout=timeout,
                cwd=tmpdir,
                env={**os.environ, "PYTHONPATH": tmpdir},
            )
            return {
                "success": run.returncode == 0,
                "stdout": run.stdout[-5000:],
                "stderr": run.stderr[-5000:],
                "returncode": run.returncode,
                "duration_ms": int((time.monotonic() - t0) * 1000),
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Execution timed out after {timeout}s",
                "duration_ms": int((time.monotonic() - t0) * 1000),
                "error": "timeout",
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc)[:500],
                "duration_ms": int((time.monotonic() - t0) * 1000),
            }
