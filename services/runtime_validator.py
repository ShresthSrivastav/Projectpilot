"""Runtime Validator — start generated app and verify health endpoint."""

import logging
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


def validate(job_dir: Path, timeout: int = 30) -> dict:
    """Start the generated application, wait for it, and hit /health.

    Installs dependencies first if requirements.txt exists.

    Returns:
        {"passed": bool, "error": Optional[str], "health": Optional[Dict],
         "port": Optional[int], "command": str}
    """
    port = _find_free_port()

    # 1. Install dependencies
    install_err = _install_deps(job_dir)
    if install_err:
        return {"passed": False, "error": install_err, "health": None, "port": None, "command": ""}

    # 2. Find entry point
    entry = _find_entry(job_dir)
    if entry is None:
        return {"passed": False, "error": "No entry point found (backend/main.py or app.py or main.py)", "health": None, "port": None, "command": ""}

    # 3. Start the app
    cmd = [sys.executable, str(entry)]
    env = {**{k: v for k, v in _parent_env().items() if k in {"PATH", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "SYSTEMROOT", "TEMP", "TMP", "PYTHONDONTWRITEBYTECODE"}}, "PORT": str(port), "HOST": "127.0.0.1"}
    try:
        proc = subprocess.Popen(
            cmd, cwd=str(job_dir), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, text=True,
        )
    except FileNotFoundError as exc:
        return {"passed": False, "error": f"Cannot start app: {exc}", "health": None, "port": port, "command": str(cmd)}

    # 4. Wait for health endpoint
    health_url = f"http://127.0.0.1:{port}/health"
    health_result = None
    started = False
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        try:
            req = Request(health_url)
            resp = urlopen(req, timeout=3)
            if resp.status == 200:
                import json
                health_result = json.loads(resp.read().decode())
                started = True
                break
        except URLError:
            pass
        except ConnectionResetError:
            pass
        except Exception:
            pass
        time.sleep(1)

    # 5. Kill the process
    _kill(proc)

    if not started:
        stdout, stderr = proc.communicate(timeout=5)
        error_text = (stderr or "")[:2000] or (stdout or "")[:2000]
        return {"passed": False, "error": f"App did not start within {timeout}s. Output: {error_text}", "health": None, "port": port, "command": str(cmd)}

    return {"passed": True, "error": None, "health": health_result, "port": port, "command": str(cmd)}


def _install_deps(job_dir: Path) -> str | None:
    req_file = job_dir / "requirements.txt"
    if not req_file.exists():
        return None

    # Try batch install first
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(req_file)],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode == 0:
        return None

    # If batch fails, install each dep individually so partial installs work
    lines = [l.strip() for l in req_file.read_text().splitlines() if l.strip() and not l.strip().startswith("#")]
    failures = []
    for dep in lines:
        dep_name = dep.split("==")[0].split(">")[0].split("<")[0].split("[")[0].strip()
        if not dep_name:
            continue
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", dep],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode != 0:
            failures.append(dep_name)

    if failures:
        return f"pip partial failures: {', '.join(failures)}"
    return None


def _find_entry(job_dir: Path) -> Path | None:
    candidates = ["backend/main.py", "app.py", "main.py", "run.py"]
    for c in candidates:
        p = (job_dir / c).resolve()
        if p.exists():
            return p
    return None


def _find_free_port() -> int:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _parent_env() -> dict:
    import os
    return dict(os.environ)


def _kill(proc):
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
            proc.wait(timeout=3)
        except Exception:
            pass
