"""Runtime Monitor — metrics collection, aggregation, trend analysis, anomaly detection."""

import logging
import os
import statistics
import threading
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MONITOR_DIR = Path(os.getenv("MONITOR_DIR", "./monitor_data"))


@dataclass
class MetricPoint:
    timestamp: float = field(default_factory=time.time)
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    disk_mb: float = 0.0
    network_rx_bytes: int = 0
    network_tx_bytes: int = 0
    response_time_ms: float = 0.0
    error_count: int = 0
    restart_count: int = 0
    uptime: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Anomaly:
    metric: str = ""
    value: float = 0.0
    mean: float = 0.0
    stddev: float = 0.0
    z_score: float = 0.0
    severity: str = "info"
    timestamp: float = field(default_factory=time.time)


class RuntimeMonitor:
    def __init__(self):
        self.metrics: dict[str, list[MetricPoint]] = defaultdict(list)
        self.anomalies: list[Anomaly] = []
        self._lock = threading.Lock()
        self._collectors: dict[str, threading.Thread] = {}
        self._running = False
        MONITOR_DIR.mkdir(parents=True, exist_ok=True)

    def start_collecting(self, runtime_id: str, interval: float = 5.0) -> None:
        if runtime_id in self._collectors:
            return

        def _collect():
            while self._running and runtime_id in self._collectors:
                try:
                    point = self._collect_metrics(runtime_id)
                    with self._lock:
                        self.metrics[runtime_id].append(point)
                        if len(self.metrics[runtime_id]) > 10000:
                            self.metrics[runtime_id] = self.metrics[runtime_id][-5000:]
                    self._detect_anomalies(runtime_id)
                except Exception as exc:
                    logger.warning("Metrics collection for %s failed: %s", runtime_id[:8], exc)
                time.sleep(interval)

        self._running = True
        t = threading.Thread(target=_collect, daemon=True)
        self._collectors[runtime_id] = t
        t.start()
        logger.info("Metrics collection started for %s (interval=%ds)", runtime_id[:8], interval)

    def stop_collecting(self, runtime_id: str) -> None:
        self._collectors.pop(runtime_id, None)

    def _collect_metrics(self, runtime_id: str) -> MetricPoint:
        point = MetricPoint()
        try:
            from services.runtime_orchestrator import get_orchestrator

            orch = get_orchestrator()
            session = orch.get_runtime(runtime_id)
            if session:
                if session.started_at:
                    point.uptime = time.time() - session.started_at
                if session.container_id:
                    from services.container_manager import get_container_manager

                    stats = get_container_manager().get_stats(session.container_id)
                    point.cpu_percent = stats.get("cpu_percent", 0.0)
                    point.memory_mb = stats.get("memory_mb", 0.0)
                elif session.pid:
                    try:
                        import psutil

                        proc = psutil.Process(session.pid)
                        point.cpu_percent = proc.cpu_percent()
                        point.memory_mb = proc.memory_info().rss / 1024 / 1024
                    except Exception:
                        pass
        except Exception as exc:
            logger.debug("Metrics collection error: %s", exc)
        return point

    def get_metrics(self, runtime_id: str, since: float | None = None, limit: int = 100) -> list[dict]:
        with self._lock:
            points = list(self.metrics.get(runtime_id, []))
        if since:
            points = [p for p in points if p.timestamp >= since]
        return [p.to_dict() for p in points[-limit:]]

    def get_aggregate(self, runtime_id: str) -> dict[str, Any]:
        points = self.metrics.get(runtime_id, [])
        if not points:
            return {}
        cpus = [p.cpu_percent for p in points]
        mems = [p.memory_mb for p in points]
        return {
            "avg_cpu": round(statistics.mean(cpus), 2),
            "max_cpu": round(max(cpus), 2),
            "avg_memory_mb": round(statistics.mean(mems), 2),
            "max_memory_mb": round(max(mems), 2),
            "current_cpu": round(cpus[-1], 2),
            "current_memory_mb": round(mems[-1], 2),
            "sample_count": len(points),
            "uptime_seconds": points[-1].uptime if points else 0,
        }

    def get_trend(self, runtime_id: str, window: int = 10) -> dict[str, float]:
        points = self.metrics.get(runtime_id, [])
        if len(points) < window:
            return {"trend": "insufficient_data", "slope": 0.0}
        recent = points[-window:]
        cpu_values = [p.cpu_percent for p in recent]
        slope = (cpu_values[-1] - cpu_values[0]) / max(len(cpu_values), 1)
        return {
            "trend": "increasing" if slope > 5 else "decreasing" if slope < -5 else "stable",
            "slope": round(slope, 2),
            "window": window,
        }

    def _detect_anomalies(self, runtime_id: str) -> None:
        points = self.metrics.get(runtime_id, [])
        if len(points) < 10:
            return
        recent = points[-10:]
        cpus = [p.cpu_percent for p in recent]
        mems = [p.memory_mb for p in recent]
        mean_cpu = statistics.mean(cpus)
        std_cpu = statistics.stdev(cpus) if len(cpus) > 1 else 0
        latest_cpu = cpus[-1]
        if std_cpu > 0 and abs(latest_cpu - mean_cpu) / std_cpu > 3:
            self.anomalies.append(
                Anomaly(
                    metric="cpu_percent",
                    value=latest_cpu,
                    mean=mean_cpu,
                    stddev=std_cpu,
                    z_score=abs(latest_cpu - mean_cpu) / std_cpu,
                    severity="warning",
                )
            )
        mean_mem = statistics.mean(mems)
        std_mem = statistics.stdev(mems) if len(mems) > 1 else 0
        latest_mem = mems[-1]
        if std_mem > 0 and abs(latest_mem - mean_mem) / std_mem > 3:
            self.anomalies.append(
                Anomaly(
                    metric="memory_mb",
                    value=latest_mem,
                    mean=mean_mem,
                    stddev=std_mem,
                    z_score=abs(latest_mem - mean_mem) / std_mem,
                    severity="warning",
                )
            )

    def get_anomalies(self, runtime_id: str | None = None, limit: int = 50) -> list[dict]:
        return [asdict(a) for a in self.anomalies[-limit:]]

    def get_summary(self) -> dict[str, Any]:
        total_points = sum(len(pts) for pts in self.metrics.values())
        return {
            "active_runtimes": len(self._collectors),
            "total_metrics": total_points,
            "total_anomalies": len(self.anomalies),
            "stored_runtimes": len(self.metrics),
        }


_monitor = RuntimeMonitor()


def get_monitor() -> RuntimeMonitor:
    return _monitor
