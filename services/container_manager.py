"""Container Manager — Docker container lifecycle, resource limits, monitoring."""

import logging
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Container:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    docker_id: str | None = None
    image: str = ""
    name: str = ""
    status: str = "created"
    host_port: int | None = None
    container_port: int = 0
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    error: str | None = None


class ContainerManager:
    def __init__(self):
        self.containers: dict[str, Container] = {}
        self._lock = threading.Lock()
        self._port_counter = 9000

    def _next_port(self) -> int:
        with self._lock:
            port = self._port_counter
            self._port_counter += 1
            return port

    def _docker_available(self) -> bool:
        try:
            r = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=5)
            return r.returncode == 0
        except Exception:
            return False

    def create_container(
        self,
        image: str = "python:3.11-slim",
        command: list[str] | None = None,
        env_vars: dict[str, str] | None = None,
        port_mappings: dict[int, int] | None = None,
        memory_limit: str = "256m",
        cpu_limit: float = 0.5,
        network_enabled: bool = True,
        volumes: list[str] | None = None,
        working_dir: str = "",
        name: str = "",
    ) -> Container:
        container = Container(
            image=image,
            name=name or f"autodev-{uuid.uuid4().hex[:8]}",
        )
        if port_mappings:
            for container_port, host_port in port_mappings.items():
                container.container_port = container_port
                container.host_port = host_port

        if not self._docker_available():
            logger.warning("Docker unavailable, creating container in mock mode")
            container.host_port = container.host_port or self._next_port()
            container.status = "created"
            with self._lock:
                self.containers[container.id] = container
            return container

        try:
            cmd = ["docker", "create"]
            if not network_enabled:
                cmd.extend(["--network", "none"])
            if memory_limit:
                cmd.extend(["--memory", memory_limit])
            if cpu_limit:
                cmd.extend(["--cpus", str(cpu_limit)])
            if env_vars:
                for k, v in env_vars.items():
                    cmd.extend(["-e", f"{k}={v}"])
            if volumes:
                for v in volumes:
                    cmd.extend(["-v", v])
            if port_mappings:
                for c_port, h_port in port_mappings.items():
                    cmd.extend(["-p", f"{h_port}:{c_port}"])
            elif not port_mappings:
                container.host_port = self._next_port()
                cmd.extend(["-p", f"{container.host_port}:{container.container_port or 8000}"])

            if working_dir:
                cmd.extend(["-w", working_dir])
            cmd.extend(["--name", container.name])
            cmd.append(image)
            if command:
                cmd.extend(command)

            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                raise RuntimeError(f"Docker create failed: {r.stderr[:500]}")
            container.docker_id = r.stdout.strip()
            container.status = "created"
            with self._lock:
                self.containers[container.id] = container
            logger.info(
                "Container %s created (docker=%s)",
                container.id[:8],
                container.docker_id[:12] if container.docker_id else "N/A",
            )
        except Exception as exc:
            container.status = "failed"
            container.error = str(exc)
            logger.error("Container creation failed: %s", exc)
        return container

    def start_container(self, container_id: str) -> Container:
        container = self._get_container(container_id)
        if not container.docker_id:
            container.status = "running"
            container.started_at = time.time()
            return container
        try:
            r = subprocess.run(["docker", "start", container.docker_id], capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                raise RuntimeError(f"Docker start failed: {r.stderr[:500]}")
            container.status = "running"
            container.started_at = time.time()
            logger.info("Container %s started", container.id[:8])
        except Exception as exc:
            container.status = "failed"
            container.error = str(exc)
            logger.error("Container start failed: %s", exc)
        return container

    def stop_container(self, container_id: str) -> Container:
        container = self._get_container(container_id)
        if not container.docker_id:
            container.status = "stopped"
            return container
        try:
            subprocess.run(["docker", "stop", container.docker_id], capture_output=True, text=True, timeout=30)
            container.status = "stopped"
            logger.info("Container %s stopped", container.id[:8])
        except Exception as exc:
            logger.warning("Container stop failed: %s", exc)
        return container

    def restart_container(self, container_id: str) -> Container:
        self.stop_container(container_id)
        time.sleep(1)
        return self.start_container(container_id)

    def destroy_container(self, container_id: str) -> None:
        container = self._get_container(container_id)
        if container.docker_id:
            try:
                subprocess.run(["docker", "rm", "-f", container.docker_id], capture_output=True, text=True, timeout=30)
            except Exception as exc:
                logger.warning("Container destroy failed: %s", exc)
        container.status = "destroyed"
        logger.info("Container %s destroyed", container.id[:8])

    def get_logs(self, container_id: str, tail: int = 100) -> list[str]:
        container = self._get_container(container_id)
        if not container.docker_id:
            return ["(mock mode - no logs)"]
        try:
            r = subprocess.run(
                ["docker", "logs", "--tail", str(tail), container.docker_id],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return (r.stdout + r.stderr).splitlines()
        except Exception as exc:
            return [f"Error fetching logs: {exc}"]

    def get_stats(self, container_id: str) -> dict[str, Any]:
        container = self._get_container(container_id)
        if not container.docker_id:
            return {"cpu_percent": 0.0, "memory_mb": 0.0, "status": container.status}
        try:
            r = subprocess.run(
                [
                    "docker",
                    "stats",
                    "--no-stream",
                    "--format",
                    "{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}",
                    container.docker_id,
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            parts = r.stdout.strip().split("\t")
            cpu = float(parts[0].replace("%", "")) if parts else 0.0
            mem_str = parts[1].split("/")[0].strip() if len(parts) > 1 else "0MiB"
            mem_mb = self._parse_memory(mem_str)
            return {"cpu_percent": cpu, "memory_mb": mem_mb, "status": container.status}
        except Exception:
            return {"cpu_percent": 0.0, "memory_mb": 0.0, "status": container.status}

    def health_check(self, container_id: str) -> bool:
        container = self._get_container(container_id)
        if not container.docker_id:
            return container.status == "running"
        try:
            r = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Status}}", container.docker_id],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return r.stdout.strip() == "running"
        except Exception:
            return False

    def _get_container(self, container_id: str) -> Container:
        container = self.containers.get(container_id)
        if not container:
            # Check by docker_id
            for c in self.containers.values():
                if c.docker_id == container_id:
                    return c
            raise ValueError(f"Container {container_id} not found")
        return container

    def _parse_memory(self, mem_str: str) -> float:
        mem_str = mem_str.strip()
        if mem_str.endswith("GiB"):
            return float(mem_str.replace("GiB", "")) * 1024
        elif mem_str.endswith("MiB"):
            return float(mem_str.replace("MiB", ""))
        elif mem_str.endswith("KiB"):
            return float(mem_str.replace("KiB", "")) / 1024
        elif mem_str.endswith("B"):
            return float(mem_str.replace("B", "")) / 1024 / 1024
        return 0.0


_container_manager = ContainerManager()


def get_container_manager() -> ContainerManager:
    return _container_manager
