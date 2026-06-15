"""Process Manager — run, monitor, capture output, timeout handling, multi-runtime support."""
import asyncio
import json
import logging
import os
import re
import select
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ProcessStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    TERMINATED = "terminated"


SUPPORTED_RUNTIMES = {
    "python": {"ext": ".py", "run": ["python"], "serve": ["python", "-m", "uvicorn", "main:app"]},
    "node": {"ext": ".js", "run": ["node"], "serve": ["node", "server.js"]},
    "fastapi": {"ext": ".py", "run": ["uvicorn", "main:app", "--host", "0.0.0.0"], "serve": ["uvicorn", "main:app", "--host", "0.0.0.0"]},
    "flask": {"ext": ".py", "run": ["python", "app.py"], "serve": ["python", "app.py"]},
    "react": {"ext": ".js", "run": ["npx", "react-scripts", "start"], "serve": ["npx", "serve", "-s", "build"]},
    "nextjs": {"ext": ".js", "run": ["npx", "next", "dev"], "serve": ["npx", "next", "start"]},
    "streamlit": {"ext": ".py", "run": ["streamlit", "run", "app.py"], "serve": ["streamlit", "run", "app.py"]},
}


@dataclass
class ProcessResult:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    pid: Optional[int] = None
    port: Optional[int] = None
    status: ProcessStatus = ProcessStatus.PENDING
    stdout: str = ""
    stderr: str = ""
    exit_code: Optional[int] = None
    duration_ms: float = 0.0
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None
    runtime_type: str = "python"


class ProcessManager:
    def __init__(self):
        self.processes: Dict[str, ProcessResult] = {}
        self._subprocesses: Dict[int, subprocess.Popen] = {}
        self._lock = threading.Lock()
        self._port_counter = 8000

    def _next_port(self) -> int:
        with self._lock:
            port = self._port_counter
            self._port_counter += 1
            return port

    def _detect_runtime(self, working_dir: str) -> str:
        project_dir = Path(working_dir)
        if (project_dir / "package.json").exists():
            pkg = json.loads((project_dir / "package.json").read_text()) if (project_dir / "package.json").exists() else {}
            if "next" in str(pkg.get("dependencies", {})) or "next" in str(pkg.get("devDependencies", {})):
                return "nextjs"
            if "react-scripts" in str(pkg.get("dependencies", {})) or "react-scripts" in str(pkg.get("devDependencies", {})):
                return "react"
            return "node"
        py_files = list(project_dir.rglob("*.py"))
        if py_files:
            content = " ".join(f.read_text(encoding="utf-8", errors="replace") for f in py_files[:10])
            if "streamlit" in content:
                return "streamlit"
            if "fastapi" in content or "uvicorn" in content:
                return "fastapi"
            if "flask" in content:
                return "flask"
            return "python"
        return "python"

    def run(
        self,
        command: Optional[List[str]] = None,
        working_dir: str = "",
        env_vars: Optional[Dict[str, str]] = None,
        timeout: int = 300,
        runtime_type: str = "",
        serve: bool = False,
    ) -> ProcessResult:
        proc = ProcessResult(runtime_type=runtime_type or self._detect_runtime(working_dir))

        if not command:
            runtime_key = runtime_type or proc.runtime_type
            runtime_config = SUPPORTED_RUNTIMES.get(runtime_key, SUPPORTED_RUNTIMES["python"])
            cmd_key = "serve" if serve else "run"
            command = list(runtime_config[cmd_key])

        env = os.environ.copy()
        if env_vars:
            env.update(env_vars)
        if serve:
            port = self._next_port()
            env.setdefault("PORT", str(port))
            proc.port = port

        proc.status = ProcessStatus.RUNNING
        proc.started_at = time.time()

        try:
            p = subprocess.Popen(
                command,
                cwd=working_dir or None,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            proc.pid = p.pid
            with self._lock:
                self._subprocesses[p.pid] = p
                self.processes[proc.id] = proc

            stdout_lines, stderr_lines = [], []
            try:
                stdout_data, stderr_data = p.communicate(timeout=timeout)
                stdout_lines.append(stdout_data)
                stderr_lines.append(stderr_data)
            except subprocess.TimeoutExpired:
                p.kill()
                p.communicate()
                proc.status = ProcessStatus.TIMEOUT
                proc.error = f"Process timed out after {timeout}s"

            proc.stdout = "".join(stdout_lines)
            proc.stderr = "".join(stderr_lines)
            proc.exit_code = p.returncode
            proc.completed_at = time.time()
            proc.duration_ms = (proc.completed_at - proc.started_at) * 1000

            if proc.status != ProcessStatus.TIMEOUT:
                proc.status = ProcessStatus.COMPLETED if p.returncode == 0 else ProcessStatus.FAILED
                if p.returncode != 0:
                    proc.error = f"Exit code {p.returncode}"

            self._log_output(proc)

        except Exception as exc:
            proc.status = ProcessStatus.FAILED
            proc.error = str(exc)
            proc.completed_at = time.time()

        with self._lock:
            self.processes[proc.id] = proc
        return proc

    def run_detached(
        self,
        command: Optional[List[str]] = None,
        working_dir: str = "",
        env_vars: Optional[Dict[str, str]] = None,
        timeout: int = 300,
        runtime_type: str = "",
    ) -> ProcessResult:
        proc = ProcessResult(runtime_type=runtime_type or self._detect_runtime(working_dir))

        if not command:
            runtime_key = runtime_type or proc.runtime_type
            runtime_config = SUPPORTED_RUNTIMES.get(runtime_key, SUPPORTED_RUNTIMES["python"])
            command = list(runtime_config.get("serve", runtime_config["run"]))

        env = os.environ.copy()
        if env_vars:
            env.update(env_vars)

        proc.status = ProcessStatus.RUNNING
        proc.started_at = time.time()

        try:
            p = subprocess.Popen(
                command,
                cwd=working_dir or None,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            proc.pid = p.pid
            with self._lock:
                self._subprocesses[p.pid] = p
                self.processes[proc.id] = proc

            def _reader(pid: int, popen: subprocess.Popen, proc_id: str, tm: int):
                import select as sel
                import errno
                stdout_chunks, stderr_chunks = [], []
                start = time.time()
                try:
                    remaining = tm
                    while remaining > 0 and popen.poll() is None:
                        rlist, _, _ = sel.select([popen.stdout, popen.stderr], [], [], min(1.0, remaining))
                        for fh in rlist:
                            try:
                                data = os.read(fh.fileno(), 4096)
                                if data:
                                    if fh is popen.stdout:
                                        stdout_chunks.append(data.decode("utf-8", errors="replace"))
                                    else:
                                        stderr_chunks.append(data.decode("utf-8", errors="replace"))
                            except OSError as e:
                                if e.errno != errno.EAGAIN:
                                    break
                        remaining = tm - (time.time() - start)
                    if popen.poll() is None:
                        popen.kill()
                        popen.communicate()
                except Exception:
                    pass
                finally:
                    with self._lock:
                        p_result = self.processes.get(proc_id)
                        if p_result:
                            p_result.stdout = "".join(stdout_chunks)
                            p_result.stderr = "".join(stderr_chunks)
                            p_result.exit_code = popen.returncode
                            p_result.completed_at = time.time()
                            p_result.duration_ms = (p_result.completed_at - p_result.started_at) * 1000
                            if popen.returncode is not None:
                                if popen.returncode == 0:
                                    p_result.status = ProcessStatus.COMPLETED
                                else:
                                    p_result.status = ProcessStatus.FAILED
                                    p_result.error = f"Exit code {popen.returncode}"
                            self._log_output(p_result)

            t = threading.Thread(target=_reader, args=(p.pid, p, proc.id, timeout), daemon=True)
            t.start()

        except Exception as exc:
            proc.status = ProcessStatus.FAILED
            proc.error = str(exc)
            proc.completed_at = time.time()

        with self._lock:
            self.processes[proc.id] = proc
        return proc

    def run_async(
        self,
        command: Optional[List[str]] = None,
        working_dir: str = "",
        env_vars: Optional[Dict[str, str]] = None,
        timeout: int = 300,
        runtime_type: str = "",
    ) -> str:
        proc = self.run(command, working_dir, env_vars, timeout, runtime_type)
        return proc.id

    def get_process(self, process_id: str) -> Optional[ProcessResult]:
        return self.processes.get(process_id)

    def list_processes(self, limit: int = 50) -> List[Dict]:
        with self._lock:
            procs = sorted(self.processes.values(), key=lambda p: p.started_at or 0, reverse=True)
        return [asdict(p) for p in procs[:limit]]

    def terminate(self, pid: int) -> bool:
        with self._lock:
            proc = self._subprocesses.get(pid)
            if proc:
                proc.terminate()
                return True
        try:
            os.kill(pid, signal.SIGTERM)
            return True
        except (ProcessLookupError, PermissionError):
            return False

    def kill(self, pid: int) -> bool:
        with self._lock:
            proc = self._subprocesses.get(pid)
            if proc:
                proc.kill()
                return True
        try:
            os.kill(pid, signal.SIGKILL)
            return True
        except (ProcessLookupError, PermissionError):
            return False

    def is_running(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False

    def _log_output(self, proc: ProcessResult) -> None:
        log_dir = Path(os.getenv("PROCESS_LOG_DIR", "./process_logs"))
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{proc.id[:8]}.log"
        try:
            with open(log_path, "w") as f:
                f.write(f"=== Process {proc.id[:8]} ===\n")
                f.write(f"PID: {proc.pid}\n")
                f.write(f"Status: {proc.status.value}\n")
                f.write(f"Duration: {proc.duration_ms:.0f}ms\n")
                f.write(f"Exit Code: {proc.exit_code}\n")
                f.write(f"Error: {proc.error or 'None'}\n\n")
                f.write("=== STDOUT ===\n")
                f.write(proc.stdout[-5000:])
                f.write("\n=== STDERR ===\n")
                f.write(proc.stderr[-5000:])
        except Exception as exc:
            logger.warning("Log write failed: %s", exc)

    def get_process_log(self, process_id: str) -> Optional[str]:
        log_dir = Path(os.getenv("PROCESS_LOG_DIR", "./process_logs"))
        log_path = log_dir / f"{process_id[:8]}.log"
        if log_path.exists():
            return log_path.read_text(encoding="utf-8", errors="replace")
        proc = self.processes.get(process_id)
        if proc:
            return f"STDOUT:\n{proc.stdout[-3000:]}\n\nSTDERR:\n{proc.stderr[-3000:]}"
        return None


_process_manager = ProcessManager()


def get_process_manager() -> ProcessManager:
    return _process_manager
