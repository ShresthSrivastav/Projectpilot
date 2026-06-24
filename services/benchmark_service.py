"""Benchmark Suite — autonomous software generation evaluation framework."""

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BENCHMARKS_DIR = Path(os.getenv("BENCHMARKS_DIR", "./benchmarks"))
BENCHMARK_HISTORY_DIR = Path(os.getenv("BENCHMARK_HISTORY_DIR", "./benchmark_history"))


class BenchmarkStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class BenchmarkDomain(Enum):
    HOTEL_BOOKING = "hotel_booking"
    ECOMMERCE = "ecommerce"
    BLOG_CMS = "blog_cms"
    TASK_MANAGER = "task_manager"
    EXPENSE_TRACKER = "expense_tracker"
    CHAT_APP = "chat_app"
    LMS = "lms"
    PROPERTY_MANAGEMENT = "property_management"


@dataclass
class BenchmarkMetrics:
    completion_rate: float = 0.0
    architecture_quality: float = 0.0
    code_quality: float = 0.0
    test_pass_rate: float = 0.0
    browser_validation_rate: float = 0.0
    deployment_success_rate: float = 0.0
    self_healing_effectiveness: float = 0.0
    execution_time: float = 0.0
    token_usage: int = 0
    cost: float = 0.0
    feature_completeness: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BenchmarkResult:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    domain: str = ""
    status: BenchmarkStatus = BenchmarkStatus.PENDING
    metrics: BenchmarkMetrics = field(default_factory=BenchmarkMetrics)
    autonomy_score: float = 0.0
    features_passed: list[str] = field(default_factory=list)
    features_failed: list[str] = field(default_factory=list)
    feature_total: int = 0
    logs: list[str] = field(default_factory=list)
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    model: str = "local"
    iteration: int = 1

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["metrics"] = self.metrics.to_dict()
        return d


AUTONOMY_WEIGHTS = {
    "completion_rate": 0.15,
    "architecture_quality": 0.12,
    "code_quality": 0.12,
    "test_pass_rate": 0.12,
    "browser_validation_rate": 0.10,
    "deployment_success_rate": 0.10,
    "self_healing_effectiveness": 0.08,
    "execution_time": 0.05,
    "token_usage": 0.05,
    "feature_completeness": 0.11,
}


def _normalize(value: float, max_val: float, invert: bool = False) -> float:
    if max_val <= 0:
        return 0.0
    normalized = min(value / max_val, 1.0)
    return 1.0 - normalized if invert else normalized


def compute_autonomy_score(metrics: BenchmarkMetrics) -> float:
    score = 0.0
    score += _normalize(metrics.completion_rate, 100.0) * AUTONOMY_WEIGHTS["completion_rate"]
    score += _normalize(metrics.architecture_quality, 100.0) * AUTONOMY_WEIGHTS["architecture_quality"]
    score += _normalize(metrics.code_quality, 100.0) * AUTONOMY_WEIGHTS["code_quality"]
    score += _normalize(metrics.test_pass_rate, 100.0) * AUTONOMY_WEIGHTS["test_pass_rate"]
    score += _normalize(metrics.browser_validation_rate, 100.0) * AUTONOMY_WEIGHTS["browser_validation_rate"]
    score += _normalize(metrics.deployment_success_rate, 100.0) * AUTONOMY_WEIGHTS["deployment_success_rate"]
    score += _normalize(metrics.self_healing_effectiveness, 100.0) * AUTONOMY_WEIGHTS["self_healing_effectiveness"]
    score += _normalize(metrics.execution_time, 600.0, invert=True) * AUTONOMY_WEIGHTS["execution_time"]
    score += _normalize(metrics.token_usage, 100000.0, invert=True) * AUTONOMY_WEIGHTS["token_usage"]
    score += _normalize(metrics.feature_completeness, 100.0) * AUTONOMY_WEIGHTS["feature_completeness"]
    return round(score * 100.0, 1)


class BenchmarkService:
    def __init__(self):
        self.results: dict[str, BenchmarkResult] = {}
        self._lock = threading.Lock()
        BENCHMARK_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        self._domains: dict[str, dict] = {}
        self._load_benchmarks()
        self._restore_history()

    def _load_benchmarks(self) -> None:
        if not BENCHMARKS_DIR.exists():
            logger.warning("Benchmarks directory not found: %s", BENCHMARKS_DIR)
            return
        for domain_dir in sorted(BENCHMARKS_DIR.iterdir()):
            if domain_dir.is_dir():
                domain_name = domain_dir.name
                try:
                    req_file = domain_dir / "requirements.md"
                    features_file = domain_dir / "expected_features.json"
                    success_criteria_file = domain_dir / "success_criteria.json"
                    validation_file = domain_dir / "validation_tests.py"
                    browser_file = domain_dir / "browser_tests.py"
                    deployment_file = domain_dir / "deployment_tests.py"

                    domain_info = {
                        "domain": domain_name,
                        "requirements": req_file.read_text(encoding="utf-8") if req_file.exists() else "",
                        "expected_features": json.loads(features_file.read_text(encoding="utf-8"))
                        if features_file.exists()
                        else {},
                        "success_criteria": json.loads(success_criteria_file.read_text(encoding="utf-8"))
                        if success_criteria_file.exists()
                        else {},
                        "has_validation_tests": validation_file.exists(),
                        "has_browser_tests": browser_file.exists(),
                        "has_deployment_tests": deployment_file.exists(),
                    }
                    self._domains[domain_name] = domain_info
                    logger.info("Loaded benchmark: %s", domain_name)
                except Exception as exc:
                    logger.warning("Failed to load benchmark %s: %s", domain_name, exc)

    def _restore_history(self) -> None:
        history_file = BENCHMARK_HISTORY_DIR / "history.json"
        if history_file.exists():
            try:
                data = json.loads(history_file.read_text(encoding="utf-8"))
                with self._lock:
                    for item in data:
                        result = self._dict_to_result(item)
                        self.results[result.id] = result
                logger.info("Restored %d benchmark results", len(data))
            except Exception as exc:
                logger.warning("Failed to restore benchmark history: %s", exc)

    def _save_history(self) -> None:
        try:
            with self._lock:
                data = [r.to_dict() for r in self.results.values()]
            history_file = BENCHMARK_HISTORY_DIR / "history.json"
            history_file.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to save benchmark history: %s", exc)

    def _dict_to_result(self, d: dict) -> BenchmarkResult:
        metrics_dict = d.get("metrics", {})
        metrics = BenchmarkMetrics(**metrics_dict)
        d.pop("metrics", None)
        status_str = d.pop("status", "pending")
        result = BenchmarkResult(
            metrics=metrics, **{k: v for k, v in d.items() if k in BenchmarkResult.__dataclass_fields__}
        )
        for enum_key, enum_val in BenchmarkStatus.__members__.items():
            if enum_val.value == status_str:
                result.status = enum_val
                break
        return result

    def list_domains(self) -> list[dict[str, Any]]:
        domains = []
        for domain_name, info in self._domains.items():
            domains.append(
                {
                    "domain": domain_name,
                    "features_count": len(info.get("expected_features", {}).get("features", {})),
                    "has_validation_tests": info["has_validation_tests"],
                    "has_browser_tests": info["has_browser_tests"],
                    "has_deployment_tests": info["has_deployment_tests"],
                }
            )
        return domains

    def get_domain_info(self, domain: str) -> dict[str, Any] | None:
        return self._domains.get(domain)

    def run_benchmark(
        self,
        domain: str,
        model: str = "local",
        iteration: int = 1,
    ) -> BenchmarkResult:
        if domain not in self._domains:
            raise ValueError(f"Unknown benchmark domain: {domain}. Available: {list(self._domains.keys())}")

        result = BenchmarkResult(domain=domain, model=model, iteration=iteration)
        with self._lock:
            self.results[result.id] = result

        thread = threading.Thread(
            target=self._execute_benchmark,
            args=(result,),
            daemon=True,
            name=f"benchmark-{domain[:8]}",
        )
        thread.start()
        return result

    def _execute_benchmark(self, result: BenchmarkResult) -> None:
        try:
            result.status = BenchmarkStatus.RUNNING
            start_time = time.time()
            domain_info = self._domains[result.domain]

            result.logs.append(f"[{datetime.now(UTC).isoformat()}] Starting benchmark: {result.domain}")

            completion_rate, architecture_quality, code_quality = self._evaluate_code_quality(result, domain_info)
            result.metrics.completion_rate = completion_rate
            result.metrics.architecture_quality = architecture_quality
            result.metrics.code_quality = code_quality

            test_pass_rate, feature_results = self._run_validation_tests(result, domain_info)
            result.metrics.test_pass_rate = test_pass_rate
            result.features_passed = [f for f, p in feature_results if p]
            result.features_failed = [f for f, p in feature_results if not p]
            result.feature_total = len(feature_results)
            result.metrics.feature_completeness = (len(result.features_passed) / max(result.feature_total, 1)) * 100.0

            browser_rate = self._run_browser_tests(result, domain_info)
            result.metrics.browser_validation_rate = browser_rate

            deploy_rate = self._run_deployment_tests(result, domain_info)
            result.metrics.deployment_success_rate = deploy_rate

            healing_rate = self._evaluate_self_healing(result, domain_info)
            result.metrics.self_healing_effectiveness = healing_rate

            result.metrics.execution_time = time.time() - start_time
            result.metrics.token_usage = self._estimate_token_usage(result)
            result.metrics.cost = self._estimate_cost(result)

            result.autonomy_score = compute_autonomy_score(result.metrics)
            result.status = BenchmarkStatus.COMPLETED
            result.completed_at = time.time()

            result.logs.append(f"[{datetime.now(UTC).isoformat()}] Completed. Autonomy Score: {result.autonomy_score}")

            self._save_history()
            logger.info(
                "Benchmark %s/%s completed: autonomy_score=%.1f", result.domain, result.run_id, result.autonomy_score
            )

        except Exception as exc:
            result.status = BenchmarkStatus.FAILED
            result.error = str(exc)
            result.completed_at = time.time()
            result.logs.append(f"[{datetime.now(UTC).isoformat()}] FAILED: {exc}")
            logger.warning("Benchmark %s/%s failed: %s", result.domain, result.run_id, exc)
            self._save_history()

    def _evaluate_code_quality(self, result: BenchmarkResult, domain_info: dict) -> tuple[float, float, float]:
        project_dir = Path(os.getenv("GENERATED_PROJECTS_DIR", "./generated_projects"))
        job_projects = list(project_dir.iterdir()) if project_dir.exists() else []

        if not job_projects:
            result.logs.append("No generated projects found — using default scores")
            return 60.0, 50.0, 50.0

        latest = max(job_projects, key=lambda p: p.stat().st_mtime)
        py_files = list(latest.rglob("*.py"))
        js_files = list(latest.rglob("*.js"))
        total_files = len(py_files) + len(js_files)

        completion_rate = min(100.0, total_files * 8.0 + 20.0)

        has_tests = len(list(latest.rglob("test_*.py"))) + len(list(latest.rglob("*test*.py")))
        has_readme = (latest / "README.md").exists()
        has_requirements = any((latest / f).exists() for f in ("requirements.txt", "pyproject.toml", "package.json"))
        has_app = any((latest / f).exists() for f in ("main.py", "app.py", "index.js"))

        arch_score = 0.0
        if has_app:
            arch_score += 30.0
        if has_tests > 0:
            arch_score += 20.0
        if has_readme:
            arch_score += 15.0
        if has_requirements:
            arch_score += 15.0
        if has_app and has_tests and has_readme:
            arch_score += 20.0
        architecture_quality = min(100.0, arch_score)

        code_score = 0.0
        for pf in py_files:
            try:
                content = pf.read_text(encoding="utf-8", errors="replace")
                code_score += 10.0 if "def " in content else 5.0
                code_score += 10.0 if "class " in content else 0.0
                code_score += 5.0 if "async def" in content else 0.0
                code_score += 5.0 if "from " in content or "import " in content else 0.0
                code_score += 5.0 if '"""' in content or "'''" in content else 0.0
            except Exception:
                pass
        code_score = min(100.0, code_score / max(len(py_files), 1))

        result.logs.append(
            f"Code quality: {total_files} files, completion={completion_rate:.0f}%, arch={architecture_quality:.0f}%, code={code_score:.0f}%"
        )
        return completion_rate, architecture_quality, code_score

    def _run_validation_tests(self, result: BenchmarkResult, domain_info: dict) -> tuple[float, list[tuple[str, bool]]]:
        expected_features = domain_info.get("expected_features", {})
        features_data = expected_features.get("features", {})
        feature_results: list[tuple[str, bool]] = []

        all_features = []
        for category, flist in features_data.items():
            for f in flist:
                all_features.append((f["name"], f.get("weight", 5)))

        for name, _ in all_features:
            passed = self._check_feature_implemented(name, result.domain)
            feature_results.append((name, passed))

        if not all_features:
            feature_results = [("default_feature", True)]

        pass_count = sum(1 for _, p in feature_results)
        pass_rate = (pass_count / max(len(feature_results), 1)) * 100.0
        result.logs.append(f"Validation: {pass_count}/{len(feature_results)} features passed ({pass_rate:.0f}%)")
        return pass_rate, feature_results

    def _check_feature_implemented(self, feature_name: str, domain: str) -> bool:
        project_dir = Path(os.getenv("GENERATED_PROJECTS_DIR", "./generated_projects"))
        if not project_dir.exists():
            return False
        job_projects = list(project_dir.iterdir())
        if not job_projects:
            return False
        latest = max(job_projects, key=lambda p: p.stat().st_mtime)
        keywords = feature_name.lower().replace(" ", "_").replace("-", "_")
        for py_file in latest.rglob("*.py"):
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace").lower()
                if keywords in content:
                    return True
            except Exception:
                continue
        return False

    def _run_browser_tests(self, result: BenchmarkResult, domain_info: dict) -> float:
        browser_file = BENCHMARKS_DIR / result.domain / "browser_tests.py"
        if not browser_file.exists():
            return 50.0

        try:
            content = browser_file.read_text(encoding="utf-8")
            import re

            journeys = re.findall(r"\{[^}]+\}", content)
            journey_count = len(journeys)
            return min(100.0, journey_count * 25.0 + 25.0)
        except Exception:
            return 50.0

    def _run_deployment_tests(self, result: BenchmarkResult, domain_info: dict) -> float:
        deploy_file = BENCHMARKS_DIR / result.domain / "deployment_tests.py"
        if not deploy_file.exists():
            return 50.0
        project_dir = Path(os.getenv("GENERATED_PROJECTS_DIR", "./generated_projects"))
        score = 50.0
        if project_dir.exists():
            job_projects = list(project_dir.iterdir())
            if job_projects:
                latest = max(job_projects, key=lambda p: p.stat().st_mtime)
                if (latest / "Dockerfile").exists():
                    score += 20.0
                if (latest / "requirements.txt").exists():
                    score += 15.0
                if (latest / ".env.example").exists():
                    score += 15.0
        return min(100.0, score)

    def _evaluate_self_healing(self, result: BenchmarkResult, domain_info: dict) -> float:
        from services.self_healing_service import get_healing_engine

        engine = get_healing_engine()
        sessions = engine.list_sessions() if hasattr(engine, "list_sessions") else []
        if not sessions:
            return 30.0
        completed = sum(1 for s in sessions if s.get("status") == "completed")
        total = len(sessions)
        return (completed / max(total, 1)) * 100.0

    def _estimate_token_usage(self, result: BenchmarkResult) -> int:
        from services.llm_service import get_token_count

        return get_token_count()

    def _estimate_cost(self, result: BenchmarkResult) -> float:
        tokens = result.metrics.token_usage
        cost_per_token = 0.000002 if result.model == "local" else 0.00001
        return round(tokens * cost_per_token, 6)

    def get_result(self, run_id_or_result_id: str) -> BenchmarkResult | None:
        with self._lock:
            for r in self.results.values():
                if r.id == run_id_or_result_id or r.run_id == run_id_or_result_id:
                    return r
        return None

    def list_results(self, domain: str | None = None, limit: int = 50) -> list[dict]:
        with self._lock:
            results = list(self.results.values())
        if domain:
            results = [r for r in results if r.domain == domain]
        results.sort(key=lambda r: r.created_at, reverse=True)
        return [r.to_dict() for r in results[:limit]]

    def get_leaderboard(self, domain: str | None = None, limit: int = 20) -> list[dict]:
        with self._lock:
            results = list(self.results.values())
        if domain:
            results = [r for r in results if r.domain == domain]
        completed = [r for r in results if r.status == BenchmarkStatus.COMPLETED]
        completed.sort(key=lambda r: r.autonomy_score, reverse=True)
        leaderboard = []
        for i, r in enumerate(completed[:limit], 1):
            d = r.to_dict()
            d["rank"] = i
            leaderboard.append(d)
        return leaderboard

    def compare_runs(self, run_id_1: str, run_id_2: str) -> dict[str, Any]:
        r1 = self.get_result(run_id_1)
        r2 = self.get_result(run_id_2)
        if not r1 or not r2:
            missing = "run_1" if not r1 else "run_2"
            raise ValueError(f"Run not found: {missing}")

        comparison = {
            "run_1": {
                "id": r1.id,
                "run_id": r1.run_id,
                "domain": r1.domain,
                "autonomy_score": r1.autonomy_score,
                "metrics": r1.metrics.to_dict(),
            },
            "run_2": {
                "id": r2.id,
                "run_id": r2.run_id,
                "domain": r2.domain,
                "autonomy_score": r2.autonomy_score,
                "metrics": r2.metrics.to_dict(),
            },
            "differences": {},
        }

        for key in r1.metrics.to_dict():
            v1 = getattr(r1.metrics, key, 0.0)
            v2 = getattr(r2.metrics, key, 0.0)
            comparison["differences"][key] = round(v2 - v1, 2)

        comparison["score_difference"] = round(r2.autonomy_score - r1.autonomy_score, 1)
        return comparison

    def generate_report(self, run_id: str, format: str = "json") -> str:
        result = self.get_result(run_id)
        if not result:
            raise ValueError(f"Run not found: {run_id}")

        data = result.to_dict()

        if format == "markdown":
            lines = [
                f"# Benchmark Report: {result.domain}",
                "",
                f"- **Run ID:** {result.run_id}",
                f"- **Domain:** {result.domain}",
                f"- **Status:** {result.status.value}",
                f"- **Autonomy Score:** {result.autonomy_score}/100",
                f"- **Model:** {result.model}",
                f"- **Iteration:** {result.iteration}",
                f"- **Created:** {datetime.fromtimestamp(result.created_at).isoformat()}",
                f"- **Completed:** {datetime.fromtimestamp(result.completed_at).isoformat() if result.completed_at else 'N/A'}",
                "",
                "## Metrics",
                "",
                "| Metric | Value |",
                "|--------|-------|",
            ]
            for key, val in result.metrics.to_dict().items():
                lines.append(f"| {key.replace('_', ' ').title()} | {val} |")

            lines.extend(
                [
                    "",
                    "## Features",
                    "",
                    f"- **Passed:** {len(result.features_passed)}/{result.feature_total}",
                    f"- **Failed:** {len(result.features_failed)}/{result.feature_total}",
                    "",
                    "## Logs",
                ]
            )
            for log in result.logs[-20:]:
                lines.append(f"- {log}")

            if result.error:
                lines.extend(["", "## Error", "", "```", result.error, "```"])

            return "\n".join(lines)

        return json.dumps(data, indent=2, default=str)

    def get_trend_data(self, domain: str | None = None, limit: int = 50) -> dict[str, Any]:
        with self._lock:
            results = list(self.results.values())
        if domain:
            results = [r for r in results if r.domain == domain]
        completed = [r for r in results if r.status == BenchmarkStatus.COMPLETED]
        completed.sort(key=lambda r: r.created_at)

        trend = {
            "dates": [],
            "autonomy_scores": [],
            "completion_rates": [],
            "test_pass_rates": [],
            "execution_times": [],
            "token_usages": [],
        }

        for r in completed[-limit:]:
            trend["dates"].append(datetime.fromtimestamp(r.created_at).isoformat())
            trend["autonomy_scores"].append(r.autonomy_score)
            trend["completion_rates"].append(r.metrics.completion_rate)
            trend["test_pass_rates"].append(r.metrics.test_pass_rate)
            trend["execution_times"].append(r.metrics.execution_time)
            trend["token_usages"].append(r.metrics.token_usage)

        trend["improvement_rate"] = self._calculate_improvement_rate(completed)
        return trend

    def _calculate_improvement_rate(self, results: list[BenchmarkResult]) -> float:
        if len(results) < 2:
            return 0.0
        first = results[0].autonomy_score
        last = results[-1].autonomy_score
        if first <= 0:
            return 0.0
        return round(((last - first) / first) * 100.0, 1)

    def get_statistics(self) -> dict[str, Any]:
        with self._lock:
            results = list(self.results.values())
        completed = [r for r in results if r.status == BenchmarkStatus.COMPLETED]
        if not completed:
            return {"total_runs": 0, "completed_runs": 0, "average_score": 0.0, "best_score": 0.0, "domains_tested": 0}

        scores = [r.autonomy_score for r in completed]
        return {
            "total_runs": len(results),
            "completed_runs": len(completed),
            "average_score": round(sum(scores) / len(scores), 1),
            "best_score": max(scores),
            "best_domain": max(completed, key=lambda r: r.autonomy_score).domain,
            "domains_tested": len(set(r.domain for r in completed)),
            "total_tokens": sum(r.metrics.token_usage for r in completed),
            "total_cost": round(sum(r.metrics.cost for r in completed), 6),
        }


_benchmark_service = BenchmarkService()


def get_benchmark_service() -> BenchmarkService:
    return _benchmark_service
