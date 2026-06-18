"""Version Comparator — compare evaluation metrics across platform versions."""
import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class VersionSnapshot:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    version: str = ""
    autonomy_score: float = 0.0
    execution_time_ms: float = 0.0
    healing_effectiveness: float = 0.0
    deployment_success_rate: float = 0.0
    cost_efficiency: float = 0.0
    success_rate: float = 0.0
    benchmark_score: float = 0.0
    recorded_at: str = ""
    run_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VersionComparison:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    from_version: str = ""
    to_version: str = ""
    autonomy_delta: float = 0.0
    execution_time_delta: float = 0.0
    healing_delta: float = 0.0
    deployment_delta: float = 0.0
    cost_efficiency_delta: float = 0.0
    success_rate_delta: float = 0.0
    benchmark_delta: float = 0.0
    summary: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class VersionComparator:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._snapshots: dict[str, VersionSnapshot] = {}
        self._comparisons: dict[str, VersionComparison] = {}
        self._logger = logging.getLogger("VersionComparator")
        self._storage_dir = Path("evaluation_data")
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._load_data()

    def _snapshots_path(self) -> Path:
        return self._storage_dir / "version_snapshots.json"

    def _comparisons_path(self) -> Path:
        return self._storage_dir / "version_comparisons.json"

    def _load_data(self) -> None:
        for sp in [self._snapshots_path(), self._comparisons_path()]:
            if sp.exists():
                key = "snapshots" if "snapshot" in sp.name else "comparisons"
                try:
                    data = json.loads(sp.read_text(encoding="utf-8"))
                    for item in data:
                        if key == "snapshots":
                            obj = VersionSnapshot(**{k: v for k, v in item.items() if k in VersionSnapshot.__dataclass_fields__})
                            self._snapshots[obj.id] = obj
                        else:
                            obj = VersionComparison(**{k: v for k, v in item.items() if k in VersionComparison.__dataclass_fields__})
                            self._comparisons[obj.id] = obj
                except Exception as e:
                    self._logger.warning("Failed to load %s: %s", sp.name, e)

    def _save_snapshots(self) -> None:
        data = [s.to_dict() for s in self._snapshots.values()]
        self._snapshots_path().write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def _save_comparisons(self) -> None:
        data = [c.to_dict() for c in self._comparisons.values()]
        self._comparisons_path().write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def record_snapshot(self, version: str, metrics: dict[str, Any], run_id: str = "") -> VersionSnapshot:
        snapshot = VersionSnapshot(
            version=version,
            autonomy_score=metrics.get("autonomy_score", 0.0),
            execution_time_ms=metrics.get("avg_runtime_ms", 0.0),
            healing_effectiveness=metrics.get("healing_rate", 0.0),
            deployment_success_rate=metrics.get("deployment_success_rate", 0.0),
            cost_efficiency=metrics.get("cost_efficiency", 0.0),
            success_rate=metrics.get("success_rate", 0.0),
            benchmark_score=metrics.get("benchmark_score", 0.0),
            recorded_at=datetime.now(UTC).isoformat(),
            run_id=run_id,
        )
        self._snapshots[snapshot.id] = snapshot
        self._save_snapshots()
        return snapshot

    def get_snapshots(self, version: str | None = None, limit: int = 20) -> list[VersionSnapshot]:
        results = list(self._snapshots.values())
        if version:
            results = [s for s in results if s.version == version]
        results.sort(key=lambda s: s.recorded_at, reverse=True)
        return results[:limit]

    def compare_versions(self, from_version: str, to_version: str) -> VersionComparison | None:
        from_snaps = [s for s in self._snapshots.values() if s.version == from_version]
        to_snaps = [s for s in self._snapshots.values() if s.version == to_version]

        if not from_snaps or not to_snaps:
            return None

        avg_from = self._average_snapshot(from_snaps)
        avg_to = self._average_snapshot(to_snaps)

        def pct(a, b):
            return ((b - a) / max(a, 0.001)) * 100

        comparison = VersionComparison(
            from_version=from_version,
            to_version=to_version,
            autonomy_delta=pct(avg_from.autonomy_score, avg_to.autonomy_score),
            execution_time_delta=pct(avg_from.execution_time_ms, avg_to.execution_time_ms),
            healing_delta=pct(avg_from.healing_effectiveness, avg_to.healing_effectiveness),
            deployment_delta=pct(avg_from.deployment_success_rate, avg_to.deployment_success_rate),
            cost_efficiency_delta=pct(avg_from.cost_efficiency, avg_to.cost_efficiency),
            success_rate_delta=pct(avg_from.success_rate, avg_to.success_rate),
            benchmark_delta=pct(avg_from.benchmark_score, avg_to.benchmark_score),
            summary=self._generate_summary(from_version, to_version, avg_from, avg_to),
            created_at=datetime.now(UTC).isoformat(),
        )
        self._comparisons[comparison.id] = comparison
        self._save_comparisons()
        return comparison

    def _average_snapshot(self, snapshots: list[VersionSnapshot]) -> VersionSnapshot:
        n = len(snapshots)
        if n == 0:
            return VersionSnapshot()
        return VersionSnapshot(
            autonomy_score=sum(s.autonomy_score for s in snapshots) / n,
            execution_time_ms=sum(s.execution_time_ms for s in snapshots) / n,
            healing_effectiveness=sum(s.healing_effectiveness for s in snapshots) / n,
            deployment_success_rate=sum(s.deployment_success_rate for s in snapshots) / n,
            cost_efficiency=sum(s.cost_efficiency for s in snapshots) / n,
            success_rate=sum(s.success_rate for s in snapshots) / n,
            benchmark_score=sum(s.benchmark_score for s in snapshots) / n,
        )

    def _generate_summary(self, from_v: str, to_v: str, f: VersionSnapshot, t: VersionSnapshot) -> str:
        parts = [f"Comparison: {from_v} → {to_v}"]
        if t.autonomy_score > f.autonomy_score:
            parts.append(f"Autonomy improved {((t.autonomy_score - f.autonomy_score) / max(f.autonomy_score, 0.001)) * 100:.1f}%")
        else:
            parts.append(f"Autonomy declined {((f.autonomy_score - t.autonomy_score) / max(f.autonomy_score, 0.001)) * 100:.1f}%")
        if t.cost_efficiency > f.cost_efficiency:
            parts.append("Cost efficiency improved")
        else:
            parts.append("Cost efficiency declined")
        overall = "improved" if t.autonomy_score + t.deployment_success_rate + t.cost_efficiency > f.autonomy_score + f.deployment_success_rate + f.cost_efficiency else "declined"
        parts.append(f"Overall performance {overall}")
        return ". ".join(parts)

    def list_comparisons(self, limit: int = 20) -> list[VersionComparison]:
        results = sorted(self._comparisons.values(), key=lambda c: c.created_at, reverse=True)
        return results[:limit]


def get_version_comparator() -> VersionComparator:
    return VersionComparator()
