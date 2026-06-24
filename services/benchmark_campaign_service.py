"""Benchmark Campaign Service — Large-scale benchmark studies across all domains."""

import json
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CAMPAIGN_BASE_DIR = Path("benchmark_campaign")
RESULTS_DIR = CAMPAIGN_BASE_DIR / "results"
REPORTS_DIR = CAMPAIGN_BASE_DIR / "reports"
POLL_INTERVAL = 0.5
DEFAULT_MAX_WORKERS = 4
CAMPAIGN_STALE_TIMEOUT = 3600


@dataclass
class CampaignRunResult:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    campaign_id: str = ""
    domain: str = ""
    iteration: int = 1
    status: str = "pending"
    autonomy_score: float = 0.0
    execution_time: float = 0.0
    cost: float = 0.0
    tests_generated: int = 0
    tests_passed: int = 0
    healing_iterations: int = 0
    deployment_success: bool = False
    benchmark_success: bool = False
    error: str = ""
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CampaignRunResult":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


DOMAIN_METRICS_ORDER = [
    "hotel_booking",
    "ecommerce",
    "blog_cms",
    "task_manager",
    "expense_tracker",
    "chat_app",
    "lms",
    "property_management",
]


class BenchmarkCampaignService:
    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._lock = threading.Lock()
        self._executor: ThreadPoolExecutor | None = None
        CAMPAIGN_BASE_DIR.mkdir(parents=True, exist_ok=True)
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    def create_campaign(
        self,
        domains: list[str] | None = None,
        runs_per_domain: int = 10,
        name: str = "",
        parallel: bool = True,
        max_workers: int = DEFAULT_MAX_WORKERS,
        model: str = "local",
    ) -> dict[str, Any]:
        from database.memory_store import mem_save_campaign

        if not domains:
            from services.benchmark_service import get_benchmark_service

            bsvc = get_benchmark_service()
            domains = [d["id"] for d in bsvc.list_domains()]

        campaign_id = str(uuid.uuid4())
        total_runs = len(domains) * runs_per_domain

        campaign = {
            "id": campaign_id,
            "name": name or f"Campaign-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            "status": "pending",
            "config": json.dumps(
                {
                    "domains": domains,
                    "runs_per_domain": runs_per_domain,
                    "parallel": parallel,
                    "max_workers": max_workers,
                    "model": model,
                }
            ),
            "total_runs": total_runs,
            "completed_runs": 0,
            "failed_runs": 0,
            "domains": json.dumps(domains),
            "created_at": time.time(),
            "started_at": None,
            "completed_at": None,
            "error": "",
        }
        mem_save_campaign(campaign)
        return campaign

    def run_campaign(self, campaign_id: str) -> dict[str, Any]:
        from database.memory_store import (
            mem_get_campaign,
            mem_list_campaign_runs,
            mem_save_campaign_run,
            mem_update_campaign,
        )
        from services.benchmark_service import get_benchmark_service

        campaign = mem_get_campaign(campaign_id)
        if not campaign:
            raise ValueError(f"Campaign not found: {campaign_id}")

        if campaign["status"] in ("running", "completed"):
            return campaign

        config = campaign.get("config", {})
        if isinstance(config, str):
            config = json.loads(config)
        domains = config.get("domains", campaign.get("domains", []))
        if isinstance(domains, str):
            domains = json.loads(domains)
        runs_per_domain = config.get("runs_per_domain", 10)
        parallel = config.get("parallel", True)
        max_workers = config.get("max_workers", DEFAULT_MAX_WORKERS)
        model = config.get("model", "local")

        bsvc = get_benchmark_service()
        now = time.time()
        mem_update_campaign(campaign_id, {"status": "running", "started_at": now})

        existing_runs = mem_list_campaign_runs(campaign_id=campaign_id)
        completed_map = {(r["domain"], r["iteration"]): r for r in existing_runs}

        pending_runs: list[dict] = []
        for domain in domains:
            for iteration in range(1, runs_per_domain + 1):
                key = (domain, iteration)
                if key in completed_map:
                    continue
                run = {
                    "id": str(uuid.uuid4()),
                    "campaign_id": campaign_id,
                    "domain": domain,
                    "iteration": iteration,
                    "status": "pending",
                    "created_at": time.time(),
                }
                mem_save_campaign_run(run)
                pending_runs.append(run)

        if not pending_runs:
            self._finalize_campaign(campaign_id)
            return mem_get_campaign(campaign_id)

        if parallel:
            self._execute_parallel(bsvc, pending_runs, max_workers, model, campaign_id)
        else:
            for run in pending_runs:
                self._execute_single(bsvc, run, model, campaign_id)

        self._finalize_campaign(campaign_id)
        return mem_get_campaign(campaign_id)

    def _execute_parallel(
        self,
        bsvc: Any,
        runs: list[dict],
        max_workers: int,
        model: str,
        campaign_id: str,
    ) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        futures = {}
        for run in runs:
            future = self._executor.submit(self._execute_single, bsvc, run, model, campaign_id)
            futures[future] = run

        for future in as_completed(futures):
            run = futures[future]
            try:
                future.result()
            except Exception as exc:
                logger.warning("Campaign run %s/%s failed: %s", run["domain"], run["iteration"], exc)
                from database.memory_store import mem_update_campaign_run

                mem_update_campaign_run(run["id"], {"status": "failed", "error": str(exc)})
                mem_update_campaign(campaign_id, {"failed_runs": None})  # placeholder, counted below

        self._executor.shutdown(wait=False)
        self._executor = None

    def _execute_single(self, bsvc: Any, run: dict, model: str, campaign_id: str) -> None:
        from database.memory_store import mem_update_campaign, mem_update_campaign_run

        try:
            mem_update_campaign_run(run["id"], {"status": "running"})

            result = bsvc.run_benchmark(domain=run["domain"], model=model, iteration=run["iteration"])

            poll_start = time.time()
            while result.status.value in ("pending", "running"):
                if time.time() - poll_start > CAMPAIGN_STALE_TIMEOUT:
                    raise TimeoutError(f"Benchmark {run['domain']}/{run['iteration']} timed out")
                time.sleep(POLL_INTERVAL)

            metrics = result.metrics
            run_result = CampaignRunResult(
                id=run["id"],
                campaign_id=campaign_id,
                domain=run["domain"],
                iteration=run["iteration"],
                status="completed" if result.status.value == "completed" else "failed",
                autonomy_score=result.autonomy_score,
                execution_time=getattr(metrics, "execution_time", 0.0),
                cost=getattr(metrics, "cost", 0.0),
                tests_generated=getattr(metrics, "feature_completeness", 0),
                tests_passed=int(
                    getattr(metrics, "test_pass_rate", 0) * max(getattr(metrics, "feature_completeness", 100), 1) / 100
                )
                if getattr(metrics, "test_pass_rate", 0) > 0
                else 0,
                healing_iterations=int(getattr(metrics, "self_healing_effectiveness", 0) / 10)
                if getattr(metrics, "self_healing_effectiveness", 0) > 0
                else 0,
                deployment_success=getattr(metrics, "deployment_success_rate", 0) >= 80.0,
                benchmark_success=result.status.value == "completed",
                error=result.error or "",
                completed_at=time.time(),
            )

            mem_update_campaign_run(
                run["id"],
                {
                    "status": run_result.status,
                    "autonomy_score": run_result.autonomy_score,
                    "execution_time": run_result.execution_time,
                    "cost": run_result.cost,
                    "tests_generated": run_result.tests_generated,
                    "tests_passed": run_result.tests_passed,
                    "healing_iterations": run_result.healing_iterations,
                    "deployment_success": 1 if run_result.deployment_success else 0,
                    "benchmark_success": 1 if run_result.benchmark_success else 0,
                    "error": run_result.error,
                    "completed_at": run_result.completed_at,
                },
            )

            self._save_run_result_file(run_result)
            self._update_campaign_counts(campaign_id)

            # Feed into Learning Engine
            self._feed_learning_engine(run_result)

        except Exception as exc:
            mem_update_campaign_run(run["id"], {"status": "failed", "error": str(exc), "completed_at": time.time()})
            mem_update_campaign(campaign_id, {"failed_runs": None})
            logger.warning("_execute_single failed for %s/%s: %s", run["domain"], run["iteration"], exc)

    def _update_campaign_counts(self, campaign_id: str) -> None:
        from database.memory_store import mem_list_campaign_runs

        runs = mem_list_campaign_runs(campaign_id=campaign_id)
        completed = sum(1 for r in runs if r["status"] == "completed")
        failed = sum(1 for r in runs if r["status"] == "failed")
        from database.memory_store import mem_update_campaign

        mem_update_campaign(
            campaign_id,
            {
                "completed_runs": completed,
                "failed_runs": failed,
            },
        )

    def _finalize_campaign(self, campaign_id: str) -> None:
        from database.memory_store import mem_get_campaign, mem_list_campaign_runs, mem_update_campaign

        campaign = mem_get_campaign(campaign_id)
        if not campaign:
            return

        runs = mem_list_campaign_runs(campaign_id=campaign_id)
        completed = sum(1 for r in runs if r["status"] == "completed")
        failed = sum(1 for r in runs if r["status"] == "failed")
        total = len(runs)
        status = "completed" if completed + failed >= total else "failed"
        if failed > 0 and completed == 0:
            status = "failed"
        elif failed > 0 and completed > 0:
            status = "completed_with_errors"
        mem_update_campaign(
            campaign_id,
            {
                "status": status,
                "completed_runs": completed,
                "failed_runs": failed,
                "completed_at": time.time(),
            },
        )

        self._generate_domain_reports(campaign_id)
        self._generate_aggregate_report(campaign_id)
        self._generate_leaderboard_report(campaign_id)

    def _feed_learning_engine(self, run: CampaignRunResult) -> None:
        """Feed campaign run results into the Learning Feedback Service."""
        try:
            from services.learning_feedback_service import get_learning_feedback_service

            learning = get_learning_feedback_service()
            learning.ingest_benchmark_score(
                {
                    "domain": run.domain,
                    "iteration": run.iteration,
                    "score": run.autonomy_score,
                    "status": run.status,
                    "execution_time": run.execution_time,
                    "cost": run.cost,
                    "tests_passed": run.tests_passed,
                    "tests_generated": run.tests_generated,
                    "deployment_success": run.deployment_success,
                    "healing_iterations": run.healing_iterations,
                    "category": "benchmark_performance",
                    "timestamp": run.completed_at,
                }
            )
        except Exception as exc:
            logger.warning("Campaign learning feed failed: %s", exc)

    def _save_run_result_file(self, run: CampaignRunResult) -> None:
        domain_dir = RESULTS_DIR / run.domain
        domain_dir.mkdir(parents=True, exist_ok=True)
        filepath = domain_dir / f"run_{run.iteration:03d}_{run.id[:8]}.json"
        with open(filepath, "w") as f:
            json.dump(run.to_dict(), f, indent=2, default=str)

    # ── Resume ────────────────────────────────────────────────────────

    def resume_interrupted_campaign(self, campaign_id: str) -> dict[str, Any]:
        from database.memory_store import mem_get_campaign, mem_update_campaign

        campaign = mem_get_campaign(campaign_id)
        if not campaign:
            raise ValueError(f"Campaign not found: {campaign_id}")

        # Reset status to pending so run_campaign will process it
        mem_update_campaign(campaign_id, {"status": "pending"})
        return self.run_campaign(campaign_id)

    def detect_interrupted_campaigns(self) -> list[dict]:
        from database.memory_store import mem_list_campaigns

        campaigns = mem_list_campaigns()
        interrupted = []
        for c in campaigns:
            if c["status"] in ("pending", "running"):
                created = c.get("created_at", 0)
                if created > 0 and time.time() - created > CAMPAIGN_STALE_TIMEOUT:
                    interrupted.append(c)
        return interrupted

    # ── Reports ─────────────────────────────────────────────────────────

    def _get_runs_for_campaign(self, campaign_id: str) -> list[dict]:
        from database.memory_store import mem_list_campaign_runs

        return mem_list_campaign_runs(campaign_id=campaign_id)

    def _generate_domain_reports(self, campaign_id: str) -> None:
        runs = self._get_runs_for_campaign(campaign_id)
        by_domain: dict[str, list[dict]] = {}
        for r in runs:
            by_domain.setdefault(r["domain"], []).append(r)

        for domain, domain_runs in by_domain.items():
            report = self._build_domain_report(domain, domain_runs)
            domain_dir = REPORTS_DIR / "domains"
            domain_dir.mkdir(parents=True, exist_ok=True)
            filepath = domain_dir / f"{domain}_{campaign_id[:8]}.json"
            with open(filepath, "w") as f:
                json.dump(report, f, indent=2, default=str)

    def _build_domain_report(self, domain: str, runs: list[dict]) -> dict:
        completed = [r for r in runs if r["status"] == "completed"]
        failed = [r for r in runs if r["status"] == "failed"]

        if not completed:
            return {
                "domain": domain,
                "total_runs": len(runs),
                "completed": 0,
                "failed": len(failed),
                "status": "no_completed_runs",
            }

        scores = [r["autonomy_score"] for r in completed]
        costs = [r["cost"] for r in completed]
        times = [r["execution_time"] for r in completed]
        passed = [r["tests_passed"] for r in completed]
        generated = [r["tests_generated"] for r in completed]
        healing = [r["healing_iterations"] for r in completed]
        deploy_ok = sum(1 for r in completed if r["deployment_success"])
        benchmark_ok = sum(1 for r in completed if r["benchmark_success"])

        return {
            "domain": domain,
            "total_runs": len(runs),
            "completed": len(completed),
            "failed": len(failed),
            "avg_autonomy_score": sum(scores) / len(scores),
            "max_autonomy_score": max(scores),
            "min_autonomy_score": min(scores),
            "avg_cost": sum(costs) / len(costs),
            "avg_execution_time": sum(times) / len(times),
            "total_execution_time": sum(times),
            "avg_tests_generated": sum(generated) / len(generated) if generated else 0,
            "avg_tests_passed": sum(passed) / len(passed) if passed else 0,
            "avg_healing_iterations": sum(healing) / len(healing) if healing else 0,
            "deployment_success_rate": deploy_ok / len(completed) if completed else 0,
            "benchmark_success_rate": benchmark_ok / len(completed) if completed else 0,
            "deployment_success_count": deploy_ok,
            "benchmark_success_count": benchmark_ok,
            "aggregate_score": self._compute_aggregate_score(scores, deploy_ok, benchmark_ok, completed),
        }

    def _generate_aggregate_report(self, campaign_id: str) -> None:
        runs = self._get_runs_for_campaign(campaign_id)
        by_domain = self._build_all_domain_reports(runs)
        completed = [r for r in runs if r["status"] == "completed"]
        failed = [r for r in runs if r["status"] == "failed"]

        all_scores = [r["autonomy_score"] for r in completed]
        all_costs = [r["cost"] for r in completed]
        all_times = [r["execution_time"] for r in completed]
        deploy_total = sum(1 for r in completed if r["deployment_success"])
        bench_total = sum(1 for r in completed if r["benchmark_success"])

        report = {
            "campaign_id": campaign_id,
            "generated_at": datetime.now(UTC).isoformat(),
            "total_domains": len(by_domain),
            "total_runs_planned": len(runs),
            "total_completed": len(completed),
            "total_failed": len(failed),
            "overall_avg_autonomy_score": sum(all_scores) / len(all_scores) if all_scores else 0,
            "overall_avg_cost": sum(all_costs) / len(all_costs) if all_costs else 0,
            "overall_total_cost": sum(all_costs),
            "overall_avg_execution_time": sum(all_times) / len(all_times) if all_times else 0,
            "overall_total_execution_time": sum(all_times),
            "overall_deployment_success_rate": deploy_total / len(completed) if completed else 0,
            "overall_benchmark_success_rate": bench_total / len(completed) if completed else 0,
            "overall_aggregate_score": self._compute_aggregate_score(all_scores, deploy_total, bench_total, completed),
            "domain_reports": by_domain,
        }

        filepath = REPORTS_DIR / f"aggregate_{campaign_id[:8]}.json"
        with open(filepath, "w") as f:
            json.dump(report, f, indent=2, default=str)

    def _build_all_domain_reports(self, runs: list[dict]) -> dict[str, dict]:
        by_domain: dict[str, list[dict]] = {}
        for r in runs:
            by_domain.setdefault(r["domain"], []).append(r)
        return {d: self._build_domain_report(d, druns) for d, druns in by_domain.items()}

    def _generate_leaderboard_report(self, campaign_id: str) -> None:
        runs = self._get_runs_for_campaign(campaign_id)
        completed = [r for r in runs if r["status"] == "completed"]
        by_domain: dict[str, list[dict]] = {}
        for r in completed:
            by_domain.setdefault(r["domain"], []).append(r)

        entries = []
        seen = set()
        for domain, druns in by_domain.items():
            for r in druns:
                key = (r["id"], r["iteration"])
                if key not in seen:
                    seen.add(key)
                    entries.append(
                        {
                            "rank": 0,
                            "domain": domain,
                            "iteration": r["iteration"],
                            "autonomy_score": r["autonomy_score"],
                            "execution_time": r["execution_time"],
                            "cost": r["cost"],
                            "tests_passed": r["tests_passed"],
                            "benchmark_success": r["benchmark_success"],
                            "deployment_success": r["deployment_success"],
                        }
                    )

        entries.sort(key=lambda x: x["autonomy_score"], reverse=True)
        for i, e in enumerate(entries):
            e["rank"] = i + 1

        domain_leaders: dict[str, dict] = {}
        for e in entries:
            domain = e["domain"]
            if domain not in domain_leaders or e["autonomy_score"] > domain_leaders[domain]["autonomy_score"]:
                domain_leaders[domain] = e

        report = {
            "campaign_id": campaign_id,
            "generated_at": datetime.now(UTC).isoformat(),
            "overall_leader": entries[0] if entries else None,
            "best_autonomy_score": entries[0]["autonomy_score"] if entries else 0,
            "domain_leaders": domain_leaders,
            "top_10": entries[:10],
            "all_entries_sorted": entries,
        }

        filepath = REPORTS_DIR / f"leaderboard_{campaign_id[:8]}.json"
        with open(filepath, "w") as f:
            json.dump(report, f, indent=2, default=str)

    @staticmethod
    def _compute_aggregate_score(scores: list[float], deploy_ok: int, bench_ok: int, completed: list) -> float:
        if not scores:
            return 0.0
        avg_score = sum(scores) / len(scores)
        deploy_rate = deploy_ok / len(completed) if completed else 0
        bench_rate = bench_ok / len(completed) if completed else 0
        return avg_score * 0.5 + deploy_rate * 0.25 + bench_rate * 0.25

    # ── Query ───────────────────────────────────────────────────────────

    def get_campaign_status(self, campaign_id: str) -> dict[str, Any] | None:
        from database.memory_store import mem_get_campaign

        campaign = mem_get_campaign(campaign_id)
        if not campaign:
            return None
        runs = self._get_runs_for_campaign(campaign_id)
        campaign["runs"] = runs
        return campaign

    def get_campaign_results(
        self,
        campaign_id: str,
        domain: str | None = None,
    ) -> list[dict]:
        from database.memory_store import mem_list_campaign_runs

        return mem_list_campaign_runs(campaign_id=campaign_id, domain=domain)

    def get_campaign_report(
        self,
        campaign_id: str,
        report_type: str = "aggregate",
    ) -> dict | None:
        filepath = REPORTS_DIR / f"{report_type}_{campaign_id[:8]}.json"
        if filepath.exists():
            with open(filepath) as f:
                return json.load(f)
        if report_type == "aggregate":
            self._generate_aggregate_report(campaign_id)
            if filepath.exists():
                with open(filepath) as f:
                    return json.load(f)
        return None

    def get_campaign_leaderboard(self, campaign_id: str) -> dict | None:
        filepath = REPORTS_DIR / f"leaderboard_{campaign_id[:8]}.json"
        if filepath.exists():
            with open(filepath) as f:
                return json.load(f)
        return None

    def list_campaigns(self, limit: int = 50) -> list[dict]:
        from database.memory_store import mem_list_campaigns

        return mem_list_campaigns(limit=limit)

    def get_domain_report(self, campaign_id: str, domain: str) -> dict | None:
        filepath = REPORTS_DIR / "domains" / f"{domain}_{campaign_id[:8]}.json"
        if filepath.exists():
            with open(filepath) as f:
                return json.load(f)
        return None


_campaign_service = BenchmarkCampaignService()


def get_benchmark_campaign_service() -> BenchmarkCampaignService:
    return _campaign_service
