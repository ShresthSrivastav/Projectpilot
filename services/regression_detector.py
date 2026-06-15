"""Regression Detector — detect regressions in autonomy scores, success rate, costs, runtime, deployment, and benchmarks."""
import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"


@dataclass
class RegressionAlert:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    category: str = ""
    metric: str = ""
    previous_value: float = 0.0
    current_value: float = 0.0
    threshold: float = 0.0
    severity: str = "medium"
    message: str = ""
    run_id: str = ""
    detected_at: str = ""
    dismissed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RegressionDetector:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._alerts: Dict[str, RegressionAlert] = {}
        self._logger = logging.getLogger("RegressionDetector")
        self._storage_dir = Path("evaluation_data")
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._load_alerts()

    def _alerts_path(self) -> Path:
        return self._storage_dir / "regressions.json"

    def _load_alerts(self) -> None:
        path = self._alerts_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                for item in data:
                    alert = RegressionAlert(**{k: v for k, v in item.items() if k in RegressionAlert.__dataclass_fields__})
                    self._alerts[alert.id] = alert
            except Exception as e:
                self._logger.warning("Failed to load regressions: %s", e)

    def _save_alerts(self) -> None:
        data = [a.to_dict() for a in self._alerts.values()]
        self._alerts_path().write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def _severity(self, drop_pct: float) -> str:
        if drop_pct > 20:
            return SEVERITY_HIGH
        elif drop_pct > 10:
            return SEVERITY_MEDIUM
        return SEVERITY_LOW

    def check_autonomy_score(self, previous: float, current: float, run_id: str = "") -> Optional[RegressionAlert]:
        if previous <= 0:
            return None
        drop_pct = ((previous - current) / previous) * 100
        if drop_pct > 5:
            alert = RegressionAlert(
                category="autonomy",
                metric="autonomy_score",
                previous_value=previous,
                current_value=current,
                threshold=drop_pct,
                severity=self._severity(drop_pct),
                message=f"Autonomy score dropped {drop_pct:.1f}% ({previous:.2f} → {current:.2f})",
                run_id=run_id,
                detected_at=datetime.now(timezone.utc).isoformat(),
            )
            self._alerts[alert.id] = alert
            self._save_alerts()
            return alert
        return None

    def check_success_rate(self, previous: float, current: float, run_id: str = "") -> Optional[RegressionAlert]:
        if previous <= 0:
            return None
        drop_pct = ((previous - current) / previous) * 100
        if drop_pct > 5:
            alert = RegressionAlert(
                category="success_rate",
                metric="success_rate",
                previous_value=previous,
                current_value=current,
                threshold=drop_pct,
                severity=self._severity(drop_pct),
                message=f"Success rate dropped {drop_pct:.1f}% ({previous:.2f} → {current:.2f})",
                run_id=run_id,
                detected_at=datetime.now(timezone.utc).isoformat(),
            )
            self._alerts[alert.id] = alert
            self._save_alerts()
            return alert
        return None

    def check_cost_increase(self, previous: float, current: float, run_id: str = "") -> Optional[RegressionAlert]:
        if previous <= 0:
            return None
        increase_pct = ((current - previous) / previous) * 100
        if increase_pct > 10:
            alert = RegressionAlert(
                category="cost",
                metric="total_cost",
                previous_value=previous,
                current_value=current,
                threshold=increase_pct,
                severity=self._severity(increase_pct),
                message=f"Cost increased {increase_pct:.1f}% ({previous:.2f} → {current:.2f})",
                run_id=run_id,
                detected_at=datetime.now(timezone.utc).isoformat(),
            )
            self._alerts[alert.id] = alert
            self._save_alerts()
            return alert
        return None

    def check_runtime_increase(self, previous: float, current: float, run_id: str = "") -> Optional[RegressionAlert]:
        if previous <= 0:
            return None
        increase_pct = ((current - previous) / previous) * 100
        if increase_pct > 15:
            alert = RegressionAlert(
                category="runtime",
                metric="avg_runtime_ms",
                previous_value=previous,
                current_value=current,
                threshold=increase_pct,
                severity=self._severity(increase_pct),
                message=f"Runtime increased {increase_pct:.1f}% ({previous:.0f}ms → {current:.0f}ms)",
                run_id=run_id,
                detected_at=datetime.now(timezone.utc).isoformat(),
            )
            self._alerts[alert.id] = alert
            self._save_alerts()
            return alert
        return None

    def check_deployment_failures(self, previous: float, current: float, run_id: str = "") -> Optional[RegressionAlert]:
        drop_pct = ((previous - current) / max(previous, 0.01)) * 100
        if drop_pct > 5:
            alert = RegressionAlert(
                category="deployment",
                metric="deployment_success_rate",
                previous_value=previous,
                current_value=current,
                threshold=drop_pct,
                severity=self._severity(drop_pct),
                message=f"Deployment success rate dropped {drop_pct:.1f}% ({previous:.2f} → {current:.2f})",
                run_id=run_id,
                detected_at=datetime.now(timezone.utc).isoformat(),
            )
            self._alerts[alert.id] = alert
            self._save_alerts()
            return alert
        return None

    def check_benchmark_regression(self, previous: float, current: float, domain: str = "", run_id: str = "") -> Optional[RegressionAlert]:
        if previous <= 0:
            return None
        drop_pct = ((previous - current) / previous) * 100
        if drop_pct > 5:
            alert = RegressionAlert(
                category="benchmark",
                metric=f"benchmark_{domain}" if domain else "benchmark_score",
                previous_value=previous,
                current_value=current,
                threshold=drop_pct,
                severity=self._severity(drop_pct),
                message=f"Benchmark {domain or 'score'} dropped {drop_pct:.1f}% ({previous:.2f} → {current:.2f})",
                run_id=run_id,
                detected_at=datetime.now(timezone.utc).isoformat(),
            )
            self._alerts[alert.id] = alert
            self._save_alerts()
            return alert
        return None

    def run_all_checks(
        self, previous: Dict[str, float], current: Dict[str, float], run_id: str = ""
    ) -> List[RegressionAlert]:
        alerts = []
        check = self.check_autonomy_score(previous.get("autonomy_score", 0), current.get("autonomy_score", 0), run_id)
        if check:
            alerts.append(check)
        check = self.check_success_rate(previous.get("success_rate", 0), current.get("success_rate", 0), run_id)
        if check:
            alerts.append(check)
        check = self.check_cost_increase(previous.get("total_cost", 0), current.get("total_cost", 0), run_id)
        if check:
            alerts.append(check)
        check = self.check_runtime_increase(previous.get("avg_runtime_ms", 0), current.get("avg_runtime_ms", 0), run_id)
        if check:
            alerts.append(check)
        check = self.check_deployment_failures(previous.get("deployment_success_rate", 1.0), current.get("deployment_success_rate", 1.0), run_id)
        if check:
            alerts.append(check)
        return alerts

    def get_alerts(
        self, category: Optional[str] = None, severity: Optional[str] = None, limit: int = 50
    ) -> List[RegressionAlert]:
        results = list(self._alerts.values())
        if category:
            results = [a for a in results if a.category == category]
        if severity:
            results = [a for a in results if a.severity == severity]
        results.sort(key=lambda a: a.detected_at, reverse=True)
        return results[:limit]

    def get_alert(self, alert_id: str) -> Optional[RegressionAlert]:
        return self._alerts.get(alert_id)

    def dismiss_alert(self, alert_id: str) -> bool:
        alert = self._alerts.get(alert_id)
        if alert:
            alert.dismissed = True
            self._save_alerts()
            return True
        return False

    def clear_alerts(self) -> int:
        count = len(self._alerts)
        self._alerts.clear()
        self._save_alerts()
        return count


def get_regression_detector() -> RegressionDetector:
    return RegressionDetector()
