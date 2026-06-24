"""Learning Feedback Service — closed-loop improvement from evaluation results.

Ingests evaluation results, benchmark scores, regression reports, deployment
outcomes, and healing statistics. Extracts patterns, generates insights, and
produces recommendations to improve future autonomous behavior.
"""

import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

LEARNING_CATEGORIES = [
    "architecture",
    "code_quality",
    "testing",
    "deployment",
    "healing",
    "benchmark_performance",
    "cost_efficiency",
    "execution_speed",
]


@dataclass
class LearningInsight:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    insight_type: str = "pattern"
    category: str = "general"
    title: str = ""
    description: str = ""
    confidence: float = 0.0
    source: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LearningFeedbackService:
    _instance = None
    _instance_lock = threading_lock = __import__("threading").Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._logger = logging.getLogger("LearningFeedbackService")

    # ── Ingestion ──────────────────────────────────────────────────────────────

    def ingest_evaluation_result(self, run: dict) -> dict[str, Any]:
        """Ingest a completed evaluation run result."""
        from database.memory_store import mem_save_learning_feedback

        now = datetime.now(UTC).timestamp()
        run_id = run.get("id", "")
        score = run.get("autonomy_score", 0.0)
        feedback = {
            "id": f"eval_{run_id}",
            "feedback_type": "evaluation",
            "source": run.get("triggered_by", "system"),
            "category": "benchmark_performance",
            "score": score,
            "metric_name": "autonomy_score",
            "metric_value": score,
            "context": {
                "schedule": run.get("schedule", "on_demand"),
                "success_rate": run.get("success_rate", 0.0),
                "total_cost": run.get("total_cost", 0.0),
                "avg_runtime_ms": run.get("avg_runtime_ms", 0.0),
                "healing_rate": run.get("healing_rate", 0.0),
                "deployment_success_rate": run.get("deployment_success_rate", 0.0),
                "status": run.get("status", ""),
            },
            "run_id": run_id,
            "version": "13.0.0",
            "created_at": now,
        }
        mem_save_learning_feedback(feedback)

        # Extract patterns from this evaluation result
        patterns = self._extract_patterns_from_run(run)
        for p in patterns:
            mem_save_learning_feedback(
                {
                    "id": p["id"],
                    "feedback_type": "pattern",
                    "source": "evaluation",
                    "category": p["category"],
                    "score": p.get("confidence", 0.0),
                    "metric_name": "pattern_extracted",
                    "metric_value": 1.0,
                    "context": {"pattern": p},
                    "run_id": run_id,
                    "version": "13.0.0",
                    "created_at": now,
                }
            )
            self.store_pattern(p)

        return {"run_id": run_id, "score": score, "patterns_extracted": len(patterns)}

    def ingest_benchmark_score(self, benchmark_data: dict) -> dict[str, Any]:
        """Ingest a benchmark score result."""
        from database.memory_store import mem_save_learning_feedback

        now = datetime.now(UTC).timestamp()
        fb_id = f"bench_{benchmark_data.get('id', str(uuid.uuid4()))}"
        feedback = {
            "id": fb_id,
            "feedback_type": "benchmark",
            "source": benchmark_data.get("source", "benchmark_service"),
            "category": "benchmark_performance",
            "score": benchmark_data.get("score", 0.0),
            "metric_name": benchmark_data.get("metric", "overall_score"),
            "metric_value": benchmark_data.get("score", 0.0),
            "context": benchmark_data.get("context", {}),
            "run_id": benchmark_data.get("run_id", ""),
            "version": "13.0.0",
            "created_at": now,
        }
        mem_save_learning_feedback(feedback)
        return {"id": fb_id, "score": feedback["score"]}

    def ingest_regression_report(self, report: dict) -> dict[str, Any]:
        """Ingest a regression detection report."""
        from database.memory_store import mem_save_learning_feedback

        now = datetime.now(UTC).timestamp()
        regressions = (
            report.get("regressions", [])
            if isinstance(report, dict)
            else report.regressions
            if hasattr(report, "regressions")
            else []
        )
        ingested = []
        for reg in regressions:
            reg_dict = reg if isinstance(reg, dict) else reg.to_dict() if hasattr(reg, "to_dict") else {}
            fb_id = f"reg_{reg_dict.get('id', str(uuid.uuid4()))}"
            feedback = {
                "id": fb_id,
                "feedback_type": "regression",
                "source": report.get("source", "regression_detector")
                if isinstance(report, dict)
                else "regression_detector",
                "category": reg_dict.get("category", "general"),
                "score": -abs(reg_dict.get("change_pct", 0.0)),
                "metric_name": reg_dict.get("metric", ""),
                "metric_value": reg_dict.get("current_value", 0.0),
                "context": {
                    "previous_value": reg_dict.get("previous_value", 0.0),
                    "change_pct": reg_dict.get("change_pct", 0.0),
                    "severity": reg_dict.get("severity", "low"),
                },
                "run_id": reg_dict.get("run_id", report.get("run_id", "") if isinstance(report, dict) else ""),
                "version": "13.0.0",
                "created_at": now,
            }
            mem_save_learning_feedback(feedback)
            ingested.append(fb_id)
        return {"ingested": len(ingested), "regression_ids": ingested}

    def ingest_deployment_outcome(self, deployment: dict) -> dict[str, Any]:
        """Ingest a deployment outcome."""
        from database.memory_store import mem_save_learning_feedback

        now = datetime.now(UTC).timestamp()
        fb_id = f"deploy_{deployment.get('id', str(uuid.uuid4()))}"
        success = deployment.get("success", False)
        feedback = {
            "id": fb_id,
            "feedback_type": "deployment",
            "source": deployment.get("source", "deployment_service"),
            "category": "deployment",
            "score": 1.0 if success else 0.0,
            "metric_name": "deployment_success",
            "metric_value": 1.0 if success else 0.0,
            "context": {
                "environment": deployment.get("environment", ""),
                "duration_seconds": deployment.get("duration_seconds", 0),
                "error": deployment.get("error", ""),
            },
            "run_id": deployment.get("run_id", ""),
            "version": "13.0.0",
            "created_at": now,
        }
        mem_save_learning_feedback(feedback)

        if not success:
            self.store_pattern(
                {
                    "pattern_type": "failed_strategy",
                    "category": "deployment",
                    "title": "Deployment failure",
                    "description": deployment.get("error", "Unknown deployment error"),
                    "strategy": deployment.get("strategy", ""),
                    "outcome": "failed",
                    "confidence": 0.3,
                    "tags": ["deployment", "failure"],
                    "source_run_ids": [deployment.get("run_id", "")],
                }
            )

        return {"id": fb_id, "success": success}

    def ingest_healing_statistics(self, healing: dict) -> dict[str, Any]:
        """Ingest healing statistics."""
        from database.memory_store import mem_save_learning_feedback

        now = datetime.now(UTC).timestamp()
        fb_id = f"heal_{healing.get('id', str(uuid.uuid4()))}"
        heal_rate = healing.get("healing_rate", 0.0)
        feedback = {
            "id": fb_id,
            "feedback_type": "healing",
            "source": healing.get("source", "evaluation_reporter"),
            "category": "healing",
            "score": heal_rate,
            "metric_name": "healing_rate",
            "metric_value": heal_rate,
            "context": {
                "total_incidents": healing.get("total_incidents", 0),
                "auto_resolved": healing.get("auto_resolved", 0),
                "mean_time_to_heal": healing.get("mean_time_to_heal", 0),
            },
            "run_id": healing.get("run_id", ""),
            "version": "13.0.0",
            "created_at": now,
        }
        mem_save_learning_feedback(feedback)
        return {"id": fb_id, "healing_rate": heal_rate}

    # ── Pattern Extraction ─────────────────────────────────────────────────────

    def _extract_patterns_from_run(self, run: dict) -> list[dict]:
        """Extract learning patterns from an evaluation run."""
        patterns = []
        run_id = run.get("id", "")
        run_dict = run if isinstance(run, dict) else run.to_dict() if hasattr(run, "to_dict") else {}

        score = run_dict.get("autonomy_score", 0.0)
        success_rate = run_dict.get("success_rate", 0.0)
        cost = run_dict.get("total_cost", 0.0)
        runtime = run_dict.get("avg_runtime_ms", 0.0)
        healing = run_dict.get("healing_rate", 0.0)
        deploy = run_dict.get("deployment_success_rate", 0.0)

        if score >= 0.85:
            patterns.append(
                {
                    "id": f"pat_high_auto_{run_id}",
                    "pattern_type": "high_performing",
                    "category": "benchmark_performance",
                    "title": "High autonomy score",
                    "description": f"Evaluation achieved autonomy score of {score:.2f}",
                    "strategy": "Current configuration produces high autonomy scores",
                    "outcome": "success",
                    "confidence": min(1.0, score),
                    "tags": ["high_performing", "autonomy"],
                    "source_run_ids": [run_id],
                }
            )
        elif score < 0.5:
            patterns.append(
                {
                    "id": f"pat_low_auto_{run_id}",
                    "pattern_type": "low_performing",
                    "category": "benchmark_performance",
                    "title": "Low autonomy score",
                    "description": f"Evaluation scored only {score:.2f} autonomy",
                    "strategy": "Review benchmark domain selection and execution parameters",
                    "outcome": "needs_improvement",
                    "confidence": min(1.0, 1.0 - score),
                    "tags": ["low_performing", "autonomy"],
                    "source_run_ids": [run_id],
                }
            )

        if success_rate >= 0.9:
            patterns.append(
                {
                    "id": f"pat_high_sr_{run_id}",
                    "pattern_type": "high_performing",
                    "category": "code_quality",
                    "title": "High success rate",
                    "description": f"Task success rate of {success_rate:.1%}",
                    "strategy": "Current task execution approach is effective",
                    "outcome": "success",
                    "confidence": min(1.0, success_rate),
                    "tags": ["high_performing", "success_rate"],
                    "source_run_ids": [run_id],
                }
            )

        if healing >= 0.85:
            patterns.append(
                {
                    "id": f"pat_high_heal_{run_id}",
                    "pattern_type": "successful_strategy",
                    "category": "healing",
                    "title": "Strong healing rate",
                    "description": f"Self-healing rate of {healing:.1%}",
                    "strategy": "Auto-healing mechanisms are performing well",
                    "outcome": "success",
                    "confidence": min(1.0, healing),
                    "tags": ["healing", "self_healing"],
                    "source_run_ids": [run_id],
                }
            )
        elif healing < 0.6:
            patterns.append(
                {
                    "id": f"pat_low_heal_{run_id}",
                    "pattern_type": "failed_strategy",
                    "category": "healing",
                    "title": "Weak healing rate",
                    "description": f"Self-healing rate only {healing:.1%}",
                    "strategy": "Improve auto-healing mechanisms and fallback strategies",
                    "outcome": "needs_improvement",
                    "confidence": min(1.0, 1.0 - healing),
                    "tags": ["healing", "needs_improvement"],
                    "source_run_ids": [run_id],
                }
            )

        if deploy >= 0.9:
            patterns.append(
                {
                    "id": f"pat_high_deploy_{run_id}",
                    "pattern_type": "successful_strategy",
                    "category": "deployment",
                    "title": "High deployment success",
                    "description": f"Deployment success rate of {deploy:.1%}",
                    "strategy": "Current deployment pipeline is reliable",
                    "outcome": "success",
                    "confidence": min(1.0, deploy),
                    "tags": ["deployment", "reliable"],
                    "source_run_ids": [run_id],
                }
            )

        if cost > 0 and runtime > 0:
            efficiency = max(0, 1.0 - (cost * runtime) / 1_000_000)
            if efficiency >= 0.8:
                patterns.append(
                    {
                        "id": f"pat_cost_eff_{run_id}",
                        "pattern_type": "successful_strategy",
                        "category": "cost_efficiency",
                        "title": "Cost-efficient execution",
                        "description": f"Cost efficiency score of {efficiency:.2f}",
                        "strategy": "Current resource allocation is cost-effective",
                        "outcome": "success",
                        "confidence": efficiency,
                        "tags": ["cost_efficiency", "optimization"],
                        "source_run_ids": [run_id],
                    }
                )

        return patterns

    # ── Pattern Storage ────────────────────────────────────────────────────────

    def store_pattern(self, pattern: dict) -> dict[str, Any]:
        """Store or update a learning pattern."""
        from database.memory_store import (
            mem_list_learning_patterns,
            mem_save_learning_pattern,
        )

        now = datetime.now(UTC).timestamp()
        pattern_id = pattern.get("id", str(uuid.uuid4()))

        existing = mem_list_learning_patterns(
            pattern_type=pattern.get("pattern_type", ""),
            category=pattern.get("category", "general"),
            limit=50,
        )
        match = None
        for ep in existing:
            if ep.get("title") == pattern.get("title"):
                match = ep
                break

        if match:
            pattern_id = match["id"]
            p = {
                "id": pattern_id,
                "pattern_type": pattern.get("pattern_type", match.get("pattern_type", "strategy")),
                "category": pattern.get("category", match.get("category", "general")),
                "title": pattern.get("title", match.get("title", "")),
                "description": pattern.get("description", match.get("description", "")),
                "strategy": pattern.get("strategy", match.get("strategy", "")),
                "outcome": pattern.get("outcome", match.get("outcome", "")),
                "success_count": (match.get("success_count", 0) + 1)
                if pattern.get("outcome") == "success"
                else match.get("success_count", 0),
                "failure_count": (match.get("failure_count", 0) + 1)
                if pattern.get("outcome") in ("failed", "needs_improvement")
                else match.get("failure_count", 0),
                "confidence": min(1.0, pattern.get("confidence", match.get("confidence", 0.5)) * 1.05),
                "tags": list(set(match.get("tags", []) + pattern.get("tags", []))),
                "source_run_ids": list(set(match.get("source_run_ids", []) + pattern.get("source_run_ids", []))),
                "created_at": match.get("created_at", now),
                "updated_at": now,
            }
        else:
            p = {
                "id": pattern_id,
                "pattern_type": pattern.get("pattern_type", "strategy"),
                "category": pattern.get("category", "general"),
                "title": pattern.get("title", ""),
                "description": pattern.get("description", ""),
                "strategy": pattern.get("strategy", ""),
                "outcome": pattern.get("outcome", ""),
                "success_count": 1 if pattern.get("outcome") == "success" else 0,
                "failure_count": 1 if pattern.get("outcome") in ("failed", "needs_improvement") else 0,
                "confidence": pattern.get("confidence", 0.5),
                "tags": pattern.get("tags", []),
                "source_run_ids": pattern.get("source_run_ids", []),
                "created_at": now,
                "updated_at": now,
            }

        mem_save_learning_pattern(p)
        return p

    # ── Recommendation Engine ──────────────────────────────────────────────────

    def generate_recommendations(self, category: str | None = None) -> list[dict[str, Any]]:
        """Generate recommendations from stored patterns and feedback."""
        from database.memory_store import (
            mem_list_learning_patterns,
            mem_save_learning_recommendation,
        )

        generated = []

        patterns = mem_list_learning_patterns(min_confidence=0.3, limit=200)

        # Group by category
        by_category: dict[str, list[dict]] = {}
        for p in patterns:
            cat = p.get("category", "general")
            if category and cat != category:
                continue
            by_category.setdefault(cat, []).append(p)

        for cat, cat_patterns in by_category.items():
            high_perf = [
                p for p in cat_patterns if p.get("pattern_type") == "high_performing" and p.get("confidence", 0) >= 0.7
            ]
            low_perf = [
                p
                for p in cat_patterns
                if p.get("pattern_type") in ("low_performing", "failed_strategy") and p.get("confidence", 0) >= 0.3
            ]
            successful = [
                p
                for p in cat_patterns
                if p.get("pattern_type") == "successful_strategy" and p.get("confidence", 0) >= 0.6
            ]
            failed = [
                p for p in cat_patterns if p.get("pattern_type") == "failed_strategy" and p.get("confidence", 0) >= 0.3
            ]

            if high_perf:
                pids = [p["id"] for p in high_perf]
                rec = self._make_recommendation(
                    recommendation_type="workflow",
                    category=cat,
                    title=f"Leverage high-performing {cat} strategies",
                    description=f"Found {len(high_perf)} high-performing patterns in {cat} with confidence >= 0.7",
                    priority="high" if len(high_perf) >= 3 else "medium",
                    rationale="High-confidence patterns indicate reliable strategies that should be prioritized",
                    expected_impact="Improved consistency and reliability in {cat} tasks",
                    implementation_suggestions="Review top patterns and integrate into standard workflows",
                    source_pattern_ids=pids,
                )
                mem_save_learning_recommendation(rec)
                generated.append(rec)

            if low_perf:
                pids = [p["id"] for p in low_perf]
                rec = self._make_recommendation(
                    recommendation_type="architecture",
                    category=cat,
                    title=f"Address recurring {cat} challenges",
                    description=f"Found {len(low_perf)} low-performing or failing patterns in {cat}",
                    priority="high" if len(low_perf) >= 3 else "medium",
                    rationale="Recurring low performance indicates systemic issues",
                    expected_impact="Resolving these issues could significantly improve {cat} outcomes",
                    implementation_suggestions="Analyze failure patterns and implement corrective strategies",
                    source_pattern_ids=pids,
                )
                mem_save_learning_recommendation(rec)
                generated.append(rec)

            if successful and failed:
                pids = [p["id"] for p in successful + failed]
                rec = self._make_recommendation(
                    recommendation_type="benchmark",
                    category=cat,
                    title=f"Compare successful vs failed {cat} approaches",
                    description=f"{len(successful)} successful and {len(failed)} failed strategies identified",
                    priority="medium",
                    rationale="Understanding what differentiates success from failure guides optimization",
                    expected_impact="Better strategy selection for future {cat} tasks",
                    implementation_suggestions="Create comparison matrix of successful vs failed strategy attributes",
                    source_pattern_ids=pids,
                )
                mem_save_learning_recommendation(rec)
                generated.append(rec)

        return generated

    def _make_recommendation(
        self,
        recommendation_type: str,
        category: str,
        title: str,
        description: str,
        priority: str,
        rationale: str,
        expected_impact: str,
        implementation_suggestions: str,
        source_pattern_ids: list[str],
    ) -> dict[str, Any]:
        now = datetime.now(UTC).timestamp()
        return {
            "id": f"rec_{recommendation_type}_{category}_{uuid.uuid4().hex[:8]}",
            "recommendation_type": recommendation_type,
            "category": category,
            "title": title,
            "description": description,
            "priority": priority,
            "rationale": rationale,
            "expected_impact": expected_impact,
            "implementation_suggestions": implementation_suggestions,
            "status": "active",
            "source_pattern_ids": source_pattern_ids,
            "created_at": now,
            "updated_at": now,
        }

    # ── Insights ───────────────────────────────────────────────────────────────

    def generate_insights(self, category: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Generate learning insights from feedback, patterns, and recommendations."""
        from database.memory_store import mem_get_learning_insights

        return mem_get_learning_insights(category=category, limit=limit)

    # ── Query ──────────────────────────────────────────────────────────────────

    def get_patterns(
        self,
        pattern_type: str | None = None,
        category: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 100,
    ) -> list[dict]:
        from database.memory_store import mem_list_learning_patterns

        return mem_list_learning_patterns(
            pattern_type=pattern_type,
            category=category,
            min_confidence=min_confidence,
            limit=limit,
        )

    def get_recommendations(
        self,
        recommendation_type: str | None = None,
        category: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        from database.memory_store import mem_list_learning_recommendations

        return mem_list_learning_recommendations(
            recommendation_type=recommendation_type,
            category=category,
            status=status,
            limit=limit,
        )

    def get_insights(self, category: str | None = None, limit: int = 20) -> list[dict]:
        from database.memory_store import mem_get_learning_insights

        return mem_get_learning_insights(category=category, limit=limit)


def get_learning_feedback_service() -> LearningFeedbackService:
    return LearningFeedbackService()
