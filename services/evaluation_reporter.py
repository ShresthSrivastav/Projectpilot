"""Evaluation Reporter — generate daily, weekly, and release reports with trend analysis, regressions, improvements, and recommendations."""
import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPORT_TYPE_DAILY = "daily"
REPORT_TYPE_WEEKLY = "weekly"
REPORT_TYPE_RELEASE = "release"


@dataclass
class EvaluationReport:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    report_type: str = "daily"
    title: str = ""
    summary: str = ""
    trend_analysis: str = ""
    regressions: list[dict[str, Any]] = field(default_factory=list)
    improvements: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    generated_at: str = ""
    period_start: str = ""
    period_end: str = ""
    markdown: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EvaluationReporter:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._reports: dict[str, EvaluationReport] = {}
        self._logger = logging.getLogger("EvaluationReporter")
        self._storage_dir = Path("evaluation_data/reports")
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._load_reports()

    def _reports_path(self) -> Path:
        return self._storage_dir.parent / "reports_index.json"

    def _load_reports(self) -> None:
        path = self._reports_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                for item in data:
                    report = EvaluationReport(**{k: v for k, v in item.items() if k in EvaluationReport.__dataclass_fields__})
                    self._reports[report.id] = report
            except Exception as e:
                self._logger.warning("Failed to load reports: %s", e)

    def _save_reports(self) -> None:
        data = [r.to_dict() for r in self._reports.values()]
        self._reports_path().write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def _compute_trend(self, values: list[float]) -> str:
        if len(values) < 2:
            return "insufficient data"
        recent = values[-1]
        previous = values[-2]
        if recent > previous * 1.05:
            return "improving"
        elif recent < previous * 0.95:
            return "declining"
        return "stable"

    def _detect_regressions(self, runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results = []
        if len(runs) < 2:
            return results
        latest = runs[0]
        previous = runs[1]
        checks = [
            ("autonomy_score", "Autonomy score", False),
            ("success_rate", "Success rate", False),
            ("deployment_success_rate", "Deployment success rate", False),
            ("healing_rate", "Healing rate", False),
            ("total_cost", "Total cost", True),
            ("avg_runtime_ms", "Average runtime", True),
        ]
        for key, label, invert in checks:
            prev_val = previous.get(key, 0)
            curr_val = latest.get(key, 0)
            if prev_val <= 0:
                continue
            change_pct = ((curr_val - prev_val) / prev_val) * 100
            if (invert and change_pct > 5) or (not invert and change_pct < -5):
                results.append({
                    "metric": label,
                    "previous": prev_val,
                    "current": curr_val,
                    "change_pct": round(change_pct, 1),
                    "direction": "increased" if change_pct > 0 else "decreased",
                })
        return results

    def _detect_improvements(self, runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results = []
        if len(runs) < 2:
            return results
        latest = runs[0]
        previous = runs[1]
        checks = [
            ("autonomy_score", "Autonomy score", False),
            ("success_rate", "Success rate", False),
            ("deployment_success_rate", "Deployment success rate", False),
            ("healing_rate", "Healing rate", False),
        ]
        for key, label, invert in checks:
            prev_val = previous.get(key, 0)
            curr_val = latest.get(key, 0)
            if prev_val <= 0:
                continue
            change_pct = ((curr_val - prev_val) / prev_val) * 100
            if not invert and change_pct > 5:
                results.append({
                    "metric": label,
                    "previous": prev_val,
                    "current": curr_val,
                    "improvement_pct": round(change_pct, 1),
                })
        return results

    def _generate_recommendations(self, runs: list[dict[str, Any]]) -> list[str]:
        recs = []
        if not runs:
            return recs
        latest = runs[0]
        if latest.get("autonomy_score", 0) < 0.7:
            recs.append("Improve autonomy score — review agent planning and execution pipelines")
        if latest.get("success_rate", 0) < 0.8:
            recs.append("Increase success rate — investigate failing benchmark domains")
        if latest.get("deployment_success_rate", 0) < 0.9:
            recs.append("Strengthen deployment pipeline — review rollback and verification steps")
        if latest.get("healing_rate", 0) < 0.8:
            recs.append("Enhance self-healing — review recovery strategies and retry logic")
        if latest.get("total_cost", 0) > 500:
            recs.append("Optimize cost — review LLM token usage and caching strategies")
        if latest.get("avg_runtime_ms", 0) > 30000:
            recs.append("Reduce execution time — parallelize independent benchmark domains")
        if not recs:
            recs.append("All metrics healthy — continue monitoring")
        return recs

    def generate_report(
        self,
        report_type: str = REPORT_TYPE_DAILY,
        runs: list[dict[str, Any]] | None = None,
        period_start: str | None = None,
        period_end: str | None = None,
    ) -> EvaluationReport:
        runs = runs or []
        now = datetime.now(UTC)
        if not period_end:
            period_end = now.isoformat()
        if not period_start:
            if report_type == REPORT_TYPE_DAILY:
                period_start = (now - timedelta(days=1)).isoformat()
            elif report_type == REPORT_TYPE_WEEKLY:
                period_start = (now - timedelta(days=7)).isoformat()
            else:
                period_start = (now - timedelta(days=30)).isoformat()

        autonomy_trend = self._compute_trend([r.get("autonomy_score", 0) for r in runs])
        success_trend = self._compute_trend([r.get("success_rate", 0) for r in runs])
        cost_trend = self._compute_trend([r.get("total_cost", 0) for r in reversed(runs)])

        trend_text = (
            f"Autonomy: {autonomy_trend}. Success rate: {success_trend}. "
            f"Cost: {cost_trend}. "
            f"{len(runs)} evaluation run(s) in this period."
        )
        regressions = self._detect_regressions(runs)
        improvements = self._detect_improvements(runs)
        recommendations = self._generate_recommendations(runs)
        latest = runs[0] if runs else {}
        latest_autonomy = latest.get("autonomy_score", 0)
        latest_success = latest.get("success_rate", 0)

        title = f"{report_type.capitalize()} Evaluation Report — {now.strftime('%Y-%m-%d')}"
        summary = (
            f"Autonomy score: {latest_autonomy:.2f}. "
            f"Success rate: {latest_success:.2f}. "
            f"Regressions: {len(regressions)}. "
            f"Improvements: {len(improvements)}."
        )

        metrics = latest if latest else {}

        report = EvaluationReport(
            report_type=report_type,
            title=title,
            summary=summary,
            trend_analysis=trend_text,
            regressions=regressions,
            improvements=improvements,
            recommendations=recommendations,
            metrics=metrics,
            generated_at=now.isoformat(),
            period_start=period_start,
            period_end=period_end,
            markdown=self._generate_markdown(title, summary, trend_text, regressions, improvements, recommendations, metrics),
        )
        self._reports[report.id] = report
        self._save_reports()
        return report

    def _generate_markdown(
        self, title: str, summary: str, trends: str,
        regressions: list[dict], improvements: list[dict],
        recommendations: list[str], metrics: dict[str, float],
    ) -> str:
        lines = [
            f"# {title}",
            "",
            f"**Summary:** {summary}",
            "",
            "## Trend Analysis",
            trends,
            "",
            "## Regressions",
        ]
        if regressions:
            for r in regressions:
                lines.append(f"- {r['metric']}: {r['direction']} by {r['change_pct']}% ({r['previous']:.2f} → {r['current']:.2f})")
        else:
            lines.append("- No regressions detected")
        lines.extend(["", "## Improvements"])
        if improvements:
            for imp in improvements:
                lines.append(f"- {imp['metric']}: improved by {imp['improvement_pct']}% ({imp['previous']:.2f} → {imp['current']:.2f})")
        else:
            lines.append("- No significant improvements")
        lines.extend(["", "## Recommendations"])
        for rec in recommendations:
            lines.append(f"- {rec}")
        lines.extend(["", "## Key Metrics"])
        for key, val in sorted(metrics.items()):
            if isinstance(val, (int, float)):
                lines.append(f"- {key}: {val:.4f}" if isinstance(val, float) else f"- {key}: {val}")
        return "\n".join(lines)

    def get_report(self, report_id: str) -> EvaluationReport | None:
        return self._reports.get(report_id)

    def list_reports(
        self, report_type: str | None = None, limit: int = 20
    ) -> list[EvaluationReport]:
        results = list(self._reports.values())
        if report_type:
            results = [r for r in results if r.report_type == report_type]
        results.sort(key=lambda r: r.generated_at, reverse=True)
        return results[:limit]


def get_evaluation_reporter() -> EvaluationReporter:
    return EvaluationReporter()
