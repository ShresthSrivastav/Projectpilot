"""Tests for v10.1 Benchmark Suite — autonomy score computation, leaderboard, trends, comparisons."""
import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Unit Tests: Benchmark Service ──────────────────────────────────────────────


class TestBenchmarkMetrics:
    def test_metrics_defaults(self):
        from services.benchmark_service import BenchmarkMetrics
        m = BenchmarkMetrics()
        assert m.completion_rate == 0.0
        assert m.architecture_quality == 0.0
        assert m.code_quality == 0.0
        assert m.test_pass_rate == 0.0
        assert m.browser_validation_rate == 0.0
        assert m.deployment_success_rate == 0.0
        assert m.self_healing_effectiveness == 0.0
        assert m.execution_time == 0.0
        assert m.token_usage == 0
        assert m.cost == 0.0
        assert m.feature_completeness == 0.0

    def test_metrics_to_dict(self):
        from services.benchmark_service import BenchmarkMetrics
        m = BenchmarkMetrics(completion_rate=85.0, token_usage=15000)
        d = m.to_dict()
        assert d["completion_rate"] == 85.0
        assert d["token_usage"] == 15000


class TestAutonomyScore:
    def test_perfect_score(self):
        from services.benchmark_service import BenchmarkMetrics, compute_autonomy_score
        m = BenchmarkMetrics(
            completion_rate=100.0, architecture_quality=100.0, code_quality=100.0,
            test_pass_rate=100.0, browser_validation_rate=100.0, deployment_success_rate=100.0,
            self_healing_effectiveness=100.0, execution_time=1.0, token_usage=100,
            feature_completeness=100.0,
        )
        score = compute_autonomy_score(m)
        assert score > 95.0, f"Perfect metrics should give near-100 score, got {score}"
        assert score <= 100.0

    def test_zero_score(self):
        from services.benchmark_service import BenchmarkMetrics, compute_autonomy_score
        m = BenchmarkMetrics()
        score = compute_autonomy_score(m)
        assert 0.0 <= score <= 15.0, f"Default metrics should give low score, got {score}"

    def test_half_score(self):
        from services.benchmark_service import BenchmarkMetrics, compute_autonomy_score
        m = BenchmarkMetrics(
            completion_rate=50.0, architecture_quality=50.0, code_quality=50.0,
            test_pass_rate=50.0, browser_validation_rate=50.0, deployment_success_rate=50.0,
            self_healing_effectiveness=50.0, execution_time=300.0, token_usage=50000,
            feature_completeness=50.0,
        )
        score = compute_autonomy_score(m)
        assert 30.0 < score < 70.0, f"Half metrics should give ~50 score, got {score}"

    def test_score_improves_with_better_metrics(self):
        from services.benchmark_service import BenchmarkMetrics, compute_autonomy_score
        low = BenchmarkMetrics(completion_rate=30.0)
        high = BenchmarkMetrics(completion_rate=90.0)
        assert compute_autonomy_score(high) > compute_autonomy_score(low)


class TestBenchmarkResult:
    def test_result_creation(self):
        from services.benchmark_service import BenchmarkResult, BenchmarkStatus
        r = BenchmarkResult(domain="hotel_booking")
        assert r.id
        assert r.run_id
        assert r.domain == "hotel_booking"
        assert r.status == BenchmarkStatus.PENDING
        assert r.metrics.completion_rate == 0.0

    def test_result_to_dict(self):
        from services.benchmark_service import BenchmarkResult
        r = BenchmarkResult(domain="ecommerce")
        d = r.to_dict()
        assert d["domain"] == "ecommerce"
        assert d["status"] == "pending"
        assert "metrics" in d
        assert d["metrics"]["completion_rate"] == 0.0


class TestBenchmarkService:
    def test_singleton(self):
        from services.benchmark_service import get_benchmark_service
        s1 = get_benchmark_service()
        s2 = get_benchmark_service()
        assert s1 is s2

    def test_list_domains(self):
        from services.benchmark_service import get_benchmark_service
        svc = get_benchmark_service()
        domains = svc.list_domains()
        assert isinstance(domains, list)

    def test_get_domain_info_unknown(self):
        from services.benchmark_service import get_benchmark_service
        svc = get_benchmark_service()
        info = svc.get_domain_info("nonexistent")
        assert info is None

    def test_run_unknown_domain(self):
        from services.benchmark_service import get_benchmark_service
        svc = get_benchmark_service()
        with pytest.raises(ValueError):
            svc.run_benchmark(domain="nonexistent")

    def test_run_benchmark(self):
        from services.benchmark_service import get_benchmark_service, BenchmarkStatus
        svc = get_benchmark_service()
        result = svc.run_benchmark(domain="hotel_booking", model="local", iteration=1)
        assert result.domain == "hotel_booking"
        assert result.status == BenchmarkStatus.RUNNING or result.status == BenchmarkStatus.PENDING

    def test_get_result_not_found(self):
        from services.benchmark_service import get_benchmark_service
        svc = get_benchmark_service()
        r = svc.get_result("nonexistent")
        assert r is None

    def test_get_result_found(self):
        from services.benchmark_service import get_benchmark_service
        svc = get_benchmark_service()
        result = svc.run_benchmark(domain="hotel_booking")
        found = svc.get_result(result.id)
        assert found is not None
        assert found.id == result.id

    def test_get_result_by_run_id(self):
        from services.benchmark_service import get_benchmark_service
        svc = get_benchmark_service()
        result = svc.run_benchmark(domain="ecommerce")
        found = svc.get_result(result.run_id)
        assert found is not None

    def test_list_results(self):
        from services.benchmark_service import get_benchmark_service
        svc = get_benchmark_service()
        svc.run_benchmark(domain="hotel_booking")
        results = svc.list_results()
        assert len(results) >= 1

    def test_list_results_filtered(self):
        from services.benchmark_service import get_benchmark_service
        svc = get_benchmark_service()
        results = svc.list_results(domain="nonexistent_domain")
        assert len(results) == 0

    def test_leaderboard_empty(self):
        from services.benchmark_service import get_benchmark_service
        svc = get_benchmark_service()
        lb = svc.get_leaderboard()
        assert isinstance(lb, list)

    def test_leaderboard_sorted(self):
        from services.benchmark_service import get_benchmark_service, BenchmarkResult, BenchmarkStatus
        svc = get_benchmark_service()
        r1 = BenchmarkResult(domain="hotel_booking", run_id="aaaa0001")
        r1.autonomy_score = 50.0
        r1.status = BenchmarkStatus.COMPLETED
        r2 = BenchmarkResult(domain="ecommerce", run_id="aaaa0002")
        r2.autonomy_score = 80.0
        r2.status = BenchmarkStatus.COMPLETED
        svc.results[r1.id] = r1
        svc.results[r2.id] = r2
        lb = svc.get_leaderboard()
        assert len(lb) >= 2
        assert lb[0]["autonomy_score"] >= lb[1]["autonomy_score"]

    def test_compare_runs(self):
        from services.benchmark_service import get_benchmark_service, BenchmarkResult, BenchmarkStatus
        svc = get_benchmark_service()
        r1 = BenchmarkResult(domain="hotel_booking", run_id="cmp00001")
        r1.metrics.completion_rate = 50.0
        r1.autonomy_score = 30.0
        r1.status = BenchmarkStatus.COMPLETED
        r2 = BenchmarkResult(domain="hotel_booking", run_id="cmp00002")
        r2.metrics.completion_rate = 80.0
        r2.autonomy_score = 70.0
        r2.status = BenchmarkStatus.COMPLETED
        svc.results[r1.id] = r1
        svc.results[r2.id] = r2
        comp = svc.compare_runs(r1.run_id, r2.run_id)
        assert "run_1" in comp
        assert "run_2" in comp
        assert "differences" in comp
        assert comp["differences"]["completion_rate"] == 30.0
        assert comp["score_difference"] == 40.0

    def test_compare_runs_not_found(self):
        from services.benchmark_service import get_benchmark_service
        svc = get_benchmark_service()
        with pytest.raises(ValueError):
            svc.compare_runs("nonexistent", "also_missing")

    def test_generate_report_json(self):
        from services.benchmark_service import get_benchmark_service, BenchmarkResult, BenchmarkStatus
        svc = get_benchmark_service()
        r = BenchmarkResult(domain="blog_cms", run_id="rpt00001")
        r.autonomy_score = 75.5
        r.status = BenchmarkStatus.COMPLETED
        r.completed_at = time.time()
        svc.results[r.id] = r
        report = svc.generate_report(r.run_id, format="json")
        data = json.loads(report)
        assert data["domain"] == "blog_cms"
        assert data["autonomy_score"] == 75.5

    def test_generate_report_markdown(self):
        from services.benchmark_service import get_benchmark_service, BenchmarkResult, BenchmarkStatus
        svc = get_benchmark_service()
        r = BenchmarkResult(domain="task_manager", run_id="rpt00002")
        r.autonomy_score = 65.0
        r.status = BenchmarkStatus.COMPLETED
        r.completed_at = time.time()
        svc.results[r.id] = r
        report = svc.generate_report(r.run_id, format="markdown")
        assert "# Benchmark Report" in report
        assert "task_manager" in report
        assert "65.0" in report

    def test_generate_report_not_found(self):
        from services.benchmark_service import get_benchmark_service
        svc = get_benchmark_service()
        with pytest.raises(ValueError):
            svc.generate_report("nonexistent")

    def test_trend_data(self):
        from services.benchmark_service import get_benchmark_service, BenchmarkResult, BenchmarkStatus
        svc = get_benchmark_service()
        now = time.time()
        for i in range(3):
            r = BenchmarkResult(domain="hotel_booking", run_id=f"tr{i:04d}")
            r.autonomy_score = 30.0 + i * 10.0
            r.metrics.completion_rate = 40.0 + i * 10.0
            r.metrics.test_pass_rate = 50.0 + i * 10.0
            r.status = BenchmarkStatus.COMPLETED
            r.created_at = now + i
            r.completed_at = now + i
            svc.results[r.id] = r
        trend = svc.get_trend_data(domain="hotel_booking")
        assert len(trend["autonomy_scores"]) >= 3
        assert trend["improvement_rate"] > 0

    def test_statistics_structure(self):
        from services.benchmark_service import get_benchmark_service
        svc = get_benchmark_service()
        stats = svc.get_statistics()
        assert "total_runs" in stats
        assert "completed_runs" in stats
        assert "average_score" in stats
        assert "best_score" in stats
        assert "total_tokens" in stats

    def test_statistics_with_data(self):
        from services.benchmark_service import get_benchmark_service, BenchmarkResult, BenchmarkStatus
        svc = get_benchmark_service()
        for i, domain in enumerate(["hotel_booking", "ecommerce", "blog_cms"]):
            r = BenchmarkResult(domain=domain, run_id=f"st{i:04d}")
            r.autonomy_score = 60.0 + i * 10.0
            r.metrics.token_usage = 1000 * (i + 1)
            r.metrics.cost = 0.01 * (i + 1)
            r.status = BenchmarkStatus.COMPLETED
            r.completed_at = time.time()
            svc.results[r.id] = r
        stats = svc.get_statistics()
        assert stats["total_runs"] >= 3
        assert stats["completed_runs"] >= 3
        assert stats["average_score"] > 0
        assert stats["best_score"] > 0
        assert stats["domains_tested"] >= 3
        assert stats["total_tokens"] > 0

    def test_improvement_rate_no_data(self):
        from services.benchmark_service import BenchmarkService
        svc = BenchmarkService()
        rate = svc._calculate_improvement_rate([])
        assert rate == 0.0

    def test_improvement_rate_single(self):
        from services.benchmark_service import BenchmarkService, BenchmarkResult
        svc = BenchmarkService()
        rate = svc._calculate_improvement_rate([BenchmarkResult()])
        assert rate == 0.0

    def test_normalize_invert(self):
        from services.benchmark_service import _normalize
        assert _normalize(5.0, 10.0, invert=True) == 0.5
        assert _normalize(10.0, 10.0, invert=True) == 0.0
        assert _normalize(0.0, 10.0, invert=True) == 1.0

    def test_normalize_zero_max(self):
        from services.benchmark_service import _normalize
        assert _normalize(5.0, 0.0) == 0.0
        assert _normalize(5.0, 0.0, invert=True) == 0.0


class TestBenchmarkDB:
    def test_save_and_get_benchmark_result(self):
        from database.memory_store import init_db, save_benchmark_result, get_benchmark_results, delete_benchmark_result
        init_db()
        data = {
            "id": "test-bm-001",
            "run_id": "test-run-001",
            "domain": "hotel_booking",
            "status": "completed",
            "autonomy_score": 85.5,
            "metrics": {"completion_rate": 90.0, "test_pass_rate": 80.0},
            "features_passed": ["Search", "Booking"],
            "features_failed": ["Payment"],
            "feature_total": 3,
            "error": None,
            "model": "local",
            "iteration": 1,
            "logs": ["Starting..."],
            "created_at": time.time(),
            "completed_at": time.time(),
        }
        save_benchmark_result(data)
        results = get_benchmark_results(domain="hotel_booking")
        found = any(r["id"] == "test-bm-001" for r in results)
        assert found, "Benchmark result should be saved and retrievable"
        delete_benchmark_result("test-bm-001")


# ── API Tests ──────────────────────────────────────────────────────────────────


class TestBenchmarkAPI:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from backend.main import app
        return TestClient(app)

    def test_health_version(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["version"] == "13.0.0"

    def test_benchmark_domains(self, client):
        r = client.get("/benchmarks/domains")
        assert r.status_code == 200
        data = r.json()
        assert "domains" in data
        assert len(data["domains"]) > 0

    def test_benchmark_domain_info(self, client):
        r = client.get("/benchmarks/domain/hotel_booking")
        assert r.status_code == 200
        data = r.json()
        assert data["domain"] == "hotel_booking"
        assert "requirements" in data
        assert "expected_features" in data

    def test_benchmark_domain_info_not_found(self, client):
        r = client.get("/benchmarks/domain/nonexistent")
        assert r.status_code == 404

    def test_benchmark_run(self, client):
        r = client.post("/benchmarks/run", json={"domain": "hotel_booking", "model": "local", "iteration": 1})
        assert r.status_code == 200
        data = r.json()
        assert "run_id" in data
        assert "result_id" in data
        assert data["domain"] == "hotel_booking"

    def test_benchmark_run_invalid_domain(self, client):
        r = client.post("/benchmarks/run", json={"domain": "nonexistent", "model": "local"})
        assert r.status_code == 400

    def test_benchmark_result(self, client):
        r = client.post("/benchmarks/run", json={"domain": "hotel_booking", "model": "local"})
        run_id = r.json()["run_id"]
        r2 = client.get(f"/benchmarks/result/{run_id}")
        assert r2.status_code == 200
        data = r2.json()
        assert data["domain"] == "hotel_booking"

    def test_benchmark_result_not_found(self, client):
        r = client.get("/benchmarks/result/nonexistent")
        assert r.status_code == 404

    def test_benchmark_results_list(self, client):
        r = client.get("/benchmarks/results")
        assert r.status_code == 200
        data = r.json()
        assert "results" in data

    def test_benchmark_leaderboard(self, client):
        r = client.get("/benchmarks/leaderboard")
        assert r.status_code == 200
        data = r.json()
        assert "leaderboard" in data

    def test_benchmark_compare(self, client):
        r1 = client.post("/benchmarks/run", json={"domain": "hotel_booking", "model": "local"})
        r2 = client.post("/benchmarks/run", json={"domain": "ecommerce", "model": "local"})
        run1 = r1.json()["run_id"]
        run2 = r2.json()["run_id"]
        r = client.post("/benchmarks/compare", json={"run_id_1": run1, "run_id_2": run2})
        assert r.status_code == 200
        data = r.json()
        assert "run_1" in data
        assert "run_2" in data
        assert "differences" in data

    def test_benchmark_compare_not_found(self, client):
        r = client.post("/benchmarks/compare", json={"run_id_1": "nonexistent", "run_id_2": "also_missing"})
        assert r.status_code == 404

    def test_benchmark_report_json(self, client):
        r = client.post("/benchmarks/run", json={"domain": "blog_cms", "model": "local"})
        run_id = r.json()["run_id"]
        r2 = client.get(f"/benchmarks/report/{run_id}?format=json")
        assert r2.status_code == 200
        data = r2.json()
        assert data["domain"] == "blog_cms"

    def test_benchmark_report_markdown(self, client):
        r = client.post("/benchmarks/run", json={"domain": "task_manager", "model": "local"})
        run_id = r.json()["run_id"]
        r2 = client.get(f"/benchmarks/report/{run_id}?format=markdown")
        assert r2.status_code == 200
        assert "# Benchmark Report" in r2.text
        assert "task_manager" in r2.text

    def test_benchmark_report_not_found(self, client):
        r = client.get("/benchmarks/report/nonexistent")
        assert r.status_code == 404

    def test_benchmark_trends(self, client):
        r = client.get("/benchmarks/trends")
        assert r.status_code == 200
        data = r.json()
        assert "dates" in data
        assert "autonomy_scores" in data

    def test_benchmark_statistics(self, client):
        r = client.get("/benchmarks/statistics")
        assert r.status_code == 200
        data = r.json()
        assert "total_runs" in data
        assert "completed_runs" in data
        assert "average_score" in data

    def test_providers_still_work(self, client):
        r = client.get("/providers")
        assert r.status_code == 200
        providers = r.json()["providers"]
        names = [p["name"] for p in providers]
        assert "local" in names
