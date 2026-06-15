"""v12.6 — Benchmark Campaign Framework tests.

Covers campaign creation, execution, persistence, reports,
API routes, resume, and integration with Benchmark Suite.
"""
import json
import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.memory_store import (
    init_db, mem_save_campaign, mem_get_campaign,
    mem_list_campaigns, mem_update_campaign, mem_delete_campaign,
    mem_save_campaign_run, mem_get_campaign_run,
    mem_list_campaign_runs, mem_update_campaign_run,
    mem_count_campaign_runs,
)


# ── Mock helpers ─────────────────────────────────────────────────────────────

class MockBenchmarkMetrics:
    execution_time = 12.5
    cost = 0.045
    test_pass_rate = 92.0
    feature_completeness = 85.0
    self_healing_effectiveness = 75.0
    deployment_success_rate = 95.0
    completion_rate = 90.0
    architecture_quality = 85.0
    code_quality = 80.0
    browser_validation_rate = 88.0
    token_usage = 15000


class MockBenchmarkStatus:
    value = "completed"


class MockBenchmarkResult:
    status = MockBenchmarkStatus()
    autonomy_score = 0.87
    error = None
    metrics = MockBenchmarkMetrics()
    run_id = "abc12345"

    def to_dict(self):
        return {"run_id": self.run_id, "autonomy_score": self.autonomy_score}


class MockBenchmarkFailedResult:
    status = type("MockStatus", (), {"value": "failed"})()
    autonomy_score = 0.0
    error = "Simulated failure"
    metrics = MockBenchmarkMetrics()
    run_id = "fail1234"


class MockBenchmarkService:
    def __init__(self):
        self._domains = {"hotel_booking": {}, "ecommerce": {}, "blog_cms": {}}

    def list_domains(self):
        return [{"id": d} for d in self._domains]

    def run_benchmark(self, domain, model="local", iteration=1):
        return MockBenchmarkResult()


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_db():
    init_db()
    from database.memory_store import _get_conn
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM campaign_runs")
        conn.execute("DELETE FROM campaigns")
        conn.commit()
    except Exception:
        pass


@pytest.fixture
def client():
    from backend.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def campaign_service():
    from services.benchmark_campaign_service import get_benchmark_campaign_service
    svc = get_benchmark_campaign_service()
    return svc


# ═══════════════════════════════════════════════════════════════════════════
# Campaign CRUD Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestCampaignCRUD:

    def test_save_and_get_campaign(self):
        cid = "test-campaign-1"
        campaign = {
            "id": cid,
            "name": "Test Campaign",
            "status": "pending",
            "config": {"domains": ["hotel_booking"], "runs_per_domain": 5},
            "total_runs": 5,
            "completed_runs": 0,
            "failed_runs": 0,
            "domains": ["hotel_booking"],
            "created_at": time.time(),
        }
        assert mem_save_campaign(campaign)
        loaded = mem_get_campaign(cid)
        assert loaded is not None
        assert loaded["id"] == cid
        assert loaded["name"] == "Test Campaign"
        assert loaded["config"]["domains"] == ["hotel_booking"]

    def test_list_campaigns(self):
        for i in range(3):
            mem_save_campaign({
                "id": f"c{i}", "name": f"C{i}", "status": "pending",
                "config": {}, "total_runs": 0, "completed_runs": 0,
                "failed_runs": 0, "domains": [], "created_at": time.time(),
            })
        campaigns = mem_list_campaigns()
        assert len(campaigns) >= 3

    def test_list_campaigns_filter_status(self):
        mem_save_campaign({
            "id": "c-running", "name": "Running", "status": "running",
            "config": {}, "total_runs": 0, "completed_runs": 0,
            "failed_runs": 0, "domains": [], "created_at": time.time(),
        })
        mem_save_campaign({
            "id": "c-completed", "name": "Done", "status": "completed",
            "config": {}, "total_runs": 0, "completed_runs": 0,
            "failed_runs": 0, "domains": [], "created_at": time.time(),
        })
        running = mem_list_campaigns(status="running")
        assert len(running) == 1
        assert running[0]["id"] == "c-running"

    def test_update_campaign(self):
        mem_save_campaign({
            "id": "c-upd", "name": "Before", "status": "pending",
            "config": {}, "total_runs": 10, "completed_runs": 0,
            "failed_runs": 0, "domains": ["a"], "created_at": time.time(),
        })
        assert mem_update_campaign("c-upd", {"status": "running", "completed_runs": 5})
        loaded = mem_get_campaign("c-upd")
        assert loaded["status"] == "running"
        assert loaded["completed_runs"] == 5

    def test_delete_campaign_cascades(self):
        cid = "c-del"
        mem_save_campaign({
            "id": cid, "name": "Delete", "status": "pending",
            "config": {}, "total_runs": 2, "completed_runs": 0,
            "failed_runs": 0, "domains": [], "created_at": time.time(),
        })
        mem_save_campaign_run({
            "id": "r-del-1", "campaign_id": cid, "domain": "test",
            "iteration": 1, "status": "completed",
        })
        assert mem_delete_campaign(cid)
        assert mem_get_campaign(cid) is None
        assert mem_get_campaign_run("r-del-1") is None


class TestCampaignRunCRUD:

    def test_save_and_get_run(self):
        run = {
            "id": "run-1",
            "campaign_id": "c-1",
            "domain": "hotel_booking",
            "iteration": 1,
            "status": "completed",
            "autonomy_score": 0.87,
            "execution_time": 12.5,
            "cost": 0.045,
            "tests_generated": 85,
            "tests_passed": 78,
            "healing_iterations": 3,
            "deployment_success": True,
            "benchmark_success": True,
            "error": "",
            "created_at": time.time(),
            "completed_at": time.time(),
        }
        assert mem_save_campaign_run(run)
        loaded = mem_get_campaign_run("run-1")
        assert loaded is not None
        assert loaded["domain"] == "hotel_booking"
        assert loaded["autonomy_score"] == 0.87
        assert loaded["deployment_success"] is True
        assert loaded["benchmark_success"] is True

    def test_list_runs_by_campaign(self):
        cid = "c-list"
        for i in range(5):
            mem_save_campaign_run({
                "id": f"r-{i}", "campaign_id": cid, "domain": "test",
                "iteration": i, "status": "completed",
            })
        runs = mem_list_campaign_runs(campaign_id=cid)
        assert len(runs) == 5
        # Ordered by created_at ASC
        assert runs[0]["id"] == "r-0"

    def test_list_runs_filter_domain(self):
        cid = "c-dom"
        mem_save_campaign_run({"id": "r-dom-1", "campaign_id": cid, "domain": "a", "iteration": 1, "status": "completed"})
        mem_save_campaign_run({"id": "r-dom-2", "campaign_id": cid, "domain": "b", "iteration": 1, "status": "completed"})
        a_runs = mem_list_campaign_runs(campaign_id=cid, domain="a")
        assert len(a_runs) == 1
        assert a_runs[0]["domain"] == "a"

    def test_list_runs_filter_status(self):
        cid = "c-st"
        mem_save_campaign_run({"id": "r-st-1", "campaign_id": cid, "domain": "a", "iteration": 1, "status": "completed"})
        mem_save_campaign_run({"id": "r-st-2", "campaign_id": cid, "domain": "a", "iteration": 2, "status": "failed"})
        completed = mem_list_campaign_runs(campaign_id=cid, status="completed")
        assert len(completed) == 1

    def test_update_run(self):
        mem_save_campaign_run({
            "id": "r-upd", "campaign_id": "c-upd", "domain": "test",
            "iteration": 1, "status": "running",
        })
        assert mem_update_campaign_run("r-upd", {"status": "completed", "autonomy_score": 0.9})
        loaded = mem_get_campaign_run("r-upd")
        assert loaded["status"] == "completed"
        assert loaded["autonomy_score"] == 0.9

    def test_count_runs(self):
        cid = "c-cnt"
        mem_save_campaign_run({"id": "r-cnt-1", "campaign_id": cid, "domain": "a", "iteration": 1, "status": "completed"})
        mem_save_campaign_run({"id": "r-cnt-2", "campaign_id": cid, "domain": "a", "iteration": 2, "status": "completed"})
        assert mem_count_campaign_runs(campaign_id=cid) == 2
        assert mem_count_campaign_runs(campaign_id=cid, status="completed") == 2
        assert mem_count_campaign_runs(campaign_id=cid, status="failed") == 0


# ═══════════════════════════════════════════════════════════════════════════
# CampaignService Unit Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestCampaignServiceCreate:

    def test_create_campaign_with_domains(self, campaign_service):
        campaign = campaign_service.create_campaign(
            domains=["hotel_booking", "ecommerce"],
            runs_per_domain=5,
            name="Test Study",
        )
        assert campaign["status"] == "pending"
        assert campaign["total_runs"] == 10
        assert campaign["name"] == "Test Study"

    def test_create_campaign_without_domains_uses_all(self, campaign_service):
        with patch("services.benchmark_service.get_benchmark_service") as mock_bsvc:
            mock_svc = MagicMock()
            mock_svc.list_domains.return_value = [
                {"id": "a"}, {"id": "b"}, {"id": "c"},
            ]
            mock_bsvc.return_value = mock_svc
            campaign = campaign_service.create_campaign(runs_per_domain=2)
            assert campaign["total_runs"] == 6

    def test_create_campaign_persists_to_db(self, campaign_service):
        campaign = campaign_service.create_campaign(
            domains=["hotel_booking"],
            runs_per_domain=3,
        )
        loaded = mem_get_campaign(campaign["id"])
        assert loaded is not None
        assert loaded["total_runs"] == 3

    def test_list_campaigns(self, campaign_service):
        campaign_service.create_campaign(domains=["a"], runs_per_domain=1, name="C1")
        campaign_service.create_campaign(domains=["b"], runs_per_domain=1, name="C2")
        campaigns = campaign_service.list_campaigns()
        names = {c["name"] for c in campaigns}
        assert "C1" in names
        assert "C2" in names


class TestCampaignServiceRun:

    @patch("services.benchmark_service.get_benchmark_service")
    def test_run_campaign_completes_all_runs(self, mock_bsvc, campaign_service):
        mock_bsvc.return_value = MockBenchmarkService()
        campaign = campaign_service.create_campaign(
            domains=["hotel_booking", "ecommerce"],
            runs_per_domain=3,
        )
        result = campaign_service.run_campaign(campaign["id"])
        assert result["status"] in ("completed", "completed_with_errors")
        assert result["completed_runs"] == 6

    @patch("services.benchmark_service.get_benchmark_service")
    def test_run_campaign_persists_results(self, mock_bsvc, campaign_service):
        mock_bsvc.return_value = MockBenchmarkService()
        campaign = campaign_service.create_campaign(
            domains=["hotel_booking"],
            runs_per_domain=2,
        )
        campaign_service.run_campaign(campaign["id"])
        runs = mem_list_campaign_runs(campaign_id=campaign["id"])
        assert len(runs) == 2
        for r in runs:
            assert r["status"] == "completed"
            assert r["autonomy_score"] > 0

    @patch("services.benchmark_service.get_benchmark_service")
    def test_run_campaign_sequential(self, mock_bsvc, campaign_service):
        mock_bsvc.return_value = MockBenchmarkService()
        campaign = campaign_service.create_campaign(
            domains=["hotel_booking", "ecommerce"],
            runs_per_domain=2,
            parallel=False,
        )
        result = campaign_service.run_campaign(campaign["id"])
        assert result["completed_runs"] == 4

    @patch("services.benchmark_service.get_benchmark_service")
    def test_run_existing_completed_campaign_idempotent(self, mock_bsvc, campaign_service):
        mock_bsvc.return_value = MockBenchmarkService()
        campaign = campaign_service.create_campaign(domains=["hotel_booking"], runs_per_domain=1)
        campaign_service.run_campaign(campaign["id"])
        result2 = campaign_service.run_campaign(campaign["id"])
        assert result2["status"] == "completed" or result2["status"] == "running"

    @patch("services.benchmark_service.get_benchmark_service")
    def test_run_creates_result_files(self, mock_bsvc, campaign_service):
        from services.benchmark_campaign_service import RESULTS_DIR
        mock_bsvc.return_value = MockBenchmarkService()
        campaign = campaign_service.create_campaign(domains=["hotel_booking"], runs_per_domain=1)
        campaign_service.run_campaign(campaign["id"])
        domain_dir = RESULTS_DIR / "hotel_booking"
        assert domain_dir.exists()
        files = list(domain_dir.glob("*.json"))
        assert len(files) >= 1

    def test_run_nonexistent_campaign_raises(self, campaign_service):
        with pytest.raises(ValueError):
            campaign_service.run_campaign("nonexistent-id")


class TestCampaignServiceReport:

    @patch("services.benchmark_service.get_benchmark_service")
    def test_domain_report_generated(self, mock_bsvc, campaign_service):
        mock_bsvc.return_value = MockBenchmarkService()
        campaign = campaign_service.create_campaign(domains=["hotel_booking"], runs_per_domain=3)
        campaign_service.run_campaign(campaign["id"])
        report = campaign_service.get_domain_report(campaign["id"], "hotel_booking")
        assert report is not None
        assert report["domain"] == "hotel_booking"
        assert report["completed"] == 3
        assert report["avg_autonomy_score"] > 0

    @patch("services.benchmark_service.get_benchmark_service")
    def test_domain_report_metrics(self, mock_bsvc, campaign_service):
        mock_bsvc.return_value = MockBenchmarkService()
        campaign = campaign_service.create_campaign(domains=["hotel_booking"], runs_per_domain=2)
        campaign_service.run_campaign(campaign["id"])
        report = campaign_service.get_domain_report(campaign["id"], "hotel_booking")
        assert report["avg_autonomy_score"] > 0
        assert report["avg_cost"] > 0
        assert report["avg_execution_time"] > 0
        assert report["deployment_success_rate"] > 0
        assert report["benchmark_success_rate"] > 0

    @patch("services.benchmark_service.get_benchmark_service")
    def test_aggregate_report_generated(self, mock_bsvc, campaign_service):
        mock_bsvc.return_value = MockBenchmarkService()
        campaign = campaign_service.create_campaign(
            domains=["hotel_booking", "ecommerce"],
            runs_per_domain=2,
        )
        campaign_service.run_campaign(campaign["id"])
        report = campaign_service.get_campaign_report(campaign["id"], "aggregate")
        assert report is not None
        assert report["total_domains"] == 2
        assert report["total_completed"] == 4
        assert "domain_reports" in report
        assert report["overall_avg_autonomy_score"] > 0

    @patch("services.benchmark_service.get_benchmark_service")
    def test_leaderboard_report_generated(self, mock_bsvc, campaign_service):
        mock_bsvc.return_value = MockBenchmarkService()
        campaign = campaign_service.create_campaign(
            domains=["hotel_booking", "ecommerce"],
            runs_per_domain=1,
        )
        campaign_service.run_campaign(campaign["id"])
        report = campaign_service.get_campaign_leaderboard(campaign["id"])
        assert report is not None
        assert "overall_leader" in report
        assert "top_10" in report
        assert "domain_leaders" in report

    @patch("services.benchmark_service.get_benchmark_service")
    def test_aggregate_score(self, mock_bsvc, campaign_service):
        mock_bsvc.return_value = MockBenchmarkService()
        campaign = campaign_service.create_campaign(domains=["hotel_booking"], runs_per_domain=2)
        campaign_service.run_campaign(campaign["id"])
        report = campaign_service.get_campaign_report(campaign["id"], "aggregate")
        assert report["overall_aggregate_score"] > 0

    def test_no_report_for_invalid_campaign(self, campaign_service):
        report = campaign_service.get_campaign_report("nonexistent", "aggregate")
        # Even for nonexistent IDs, an empty report is generated
        assert report is not None
        assert report.get("total_completed", 0) == 0


class TestCampaignServiceResume:

    @patch("services.benchmark_service.get_benchmark_service")
    def test_resume_interrupted_campaign(self, mock_bsvc, campaign_service):
        mock_bsvc.return_value = MockBenchmarkService()
        campaign = campaign_service.create_campaign(domains=["hotel_booking"], runs_per_domain=3)
        mem_update_campaign(campaign["id"], {"status": "running"})
        result = campaign_service.resume_interrupted_campaign(campaign["id"])
        assert result["completed_runs"] == 3

    def test_resume_nonexistent_raises(self, campaign_service):
        with pytest.raises(ValueError):
            campaign_service.resume_interrupted_campaign("nonexistent")

    @patch("services.benchmark_service.get_benchmark_service")
    def test_resume_completed_campaign_returns(self, mock_bsvc, campaign_service):
        mock_bsvc.return_value = MockBenchmarkService()
        campaign = campaign_service.create_campaign(domains=["hotel_booking"], runs_per_domain=1)
        campaign_service.run_campaign(campaign["id"])
        result = campaign_service.resume_interrupted_campaign(campaign["id"])
        assert result["status"] == "completed"

    def test_detect_interrupted(self, campaign_service):
        campaign_service.create_campaign(domains=["a"], runs_per_domain=1, name="Fresh")
        old_id = "stale-campaign"
        mem_save_campaign({
            "id": old_id, "name": "Stale", "status": "running",
            "config": {}, "total_runs": 5, "completed_runs": 2,
            "failed_runs": 0, "domains": ["a"],
            "created_at": time.time() - 7200,  # 2 hours ago
        })
        interrupted = campaign_service.detect_interrupted_campaigns()
        ids = [c["id"] for c in interrupted]
        assert old_id in ids


class TestCampaignServiceQuery:

    @patch("services.benchmark_service.get_benchmark_service")
    def test_get_campaign_status(self, mock_bsvc, campaign_service):
        mock_bsvc.return_value = MockBenchmarkService()
        campaign = campaign_service.create_campaign(domains=["hotel_booking"], runs_per_domain=2)
        campaign_service.run_campaign(campaign["id"])
        status = campaign_service.get_campaign_status(campaign["id"])
        assert status is not None
        assert "runs" in status
        assert len(status["runs"]) == 2

    @patch("services.benchmark_service.get_benchmark_service")
    def test_get_campaign_results(self, mock_bsvc, campaign_service):
        mock_bsvc.return_value = MockBenchmarkService()
        campaign = campaign_service.create_campaign(domains=["hotel_booking"], runs_per_domain=2)
        campaign_service.run_campaign(campaign["id"])
        results = campaign_service.get_campaign_results(campaign["id"])
        assert len(results) == 2
        results_filtered = campaign_service.get_campaign_results(campaign["id"], domain="hotel_booking")
        assert len(results_filtered) == 2

    def test_get_status_nonexistent(self, campaign_service):
        assert campaign_service.get_campaign_status("nonexistent") is None

    @patch("services.benchmark_service.get_benchmark_service")
    def test_campaign_run_populates_all_metrics(self, mock_bsvc, campaign_service):
        mock_bsvc.return_value = MockBenchmarkService()
        campaign = campaign_service.create_campaign(domains=["hotel_booking"], runs_per_domain=1)
        campaign_service.run_campaign(campaign["id"])
        results = campaign_service.get_campaign_results(campaign["id"])
        r = results[0]
        assert r["autonomy_score"] > 0
        assert r["execution_time"] > 0
        assert r["cost"] > 0
        assert r["tests_generated"] > 0
        assert r["tests_passed"] > 0
        assert r["healing_iterations"] >= 0
        assert r["deployment_success"] is True
        assert r["benchmark_success"] is True
        assert len(r["error"]) == 0


# ═══════════════════════════════════════════════════════════════════════════
# API Route Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestCampaignAPIRoutes:

    @patch("services.benchmark_service.get_benchmark_service")
    def test_post_campaign_run_without_execution(self, mock_bsvc, client):
        mock_bsvc.return_value = MockBenchmarkService()
        resp = client.post("/campaign/run", json={
            "domains": ["hotel_booking"],
            "runs_per_domain": 2,
            "skip_run": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["campaign"]["status"] == "pending"
        assert data["campaign"]["total_runs"] == 2

    @patch("services.benchmark_service.get_benchmark_service")
    def test_post_campaign_run_and_execute(self, mock_bsvc, client):
        mock_bsvc.return_value = MockBenchmarkService()
        resp = client.post("/campaign/run", json={
            "domains": ["hotel_booking"],
            "runs_per_domain": 1,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        # May be running or completed depending on timing
        assert data["campaign"]["status"] in ("running", "completed", "completed_with_errors")

    def test_get_campaign_status_not_found(self, client):
        resp = client.get("/campaign/status?campaign_id=nonexistent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    @patch("services.benchmark_service.get_benchmark_service")
    def test_get_campaign_status_found(self, mock_bsvc, client):
        mock_bsvc.return_value = MockBenchmarkService()
        create_resp = client.post("/campaign/run", json={"domains": ["hotel_booking"], "runs_per_domain": 1})
        cid = create_resp.json()["campaign"]["id"]
        resp = client.get(f"/campaign/status?campaign_id={cid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "campaign" in data

    @patch("services.benchmark_service.get_benchmark_service")
    def test_get_campaign_results(self, mock_bsvc, client):
        mock_bsvc.return_value = MockBenchmarkService()
        create_resp = client.post("/campaign/run", json={"domains": ["hotel_booking"], "runs_per_domain": 1})
        cid = create_resp.json()["campaign"]["id"]
        resp = client.get(f"/campaign/results?campaign_id={cid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "results" in data

    @patch("services.benchmark_service.get_benchmark_service")
    def test_get_campaign_report_aggregate(self, mock_bsvc, client):
        mock_bsvc.return_value = MockBenchmarkService()
        create_resp = client.post("/campaign/run", json={"domains": ["hotel_booking"], "runs_per_domain": 1})
        cid = create_resp.json()["campaign"]["id"]
        resp = client.get(f"/campaign/report?campaign_id={cid}&report_type=aggregate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    @patch("services.benchmark_service.get_benchmark_service")
    def test_get_campaign_report_leaderboard(self, mock_bsvc, client):
        mock_bsvc.return_value = MockBenchmarkService()
        create_resp = client.post("/campaign/run", json={"domains": ["hotel_booking"], "runs_per_domain": 1})
        cid = create_resp.json()["campaign"]["id"]
        resp = client.get(f"/campaign/report?campaign_id={cid}&report_type=leaderboard")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_get_campaign_report_not_found(self, client):
        resp = client.get("/campaign/report?campaign_id=nonexistent&report_type=aggregate")
        assert resp.status_code == 200
        data = resp.json()
        # Report is generated even for nonexistent IDs (empty aggregate)
        assert data["success"] is True

    @patch("services.benchmark_service.get_benchmark_service")
    def test_post_campaign_resume(self, mock_bsvc, client):
        mock_bsvc.return_value = MockBenchmarkService()
        create_resp = client.post("/campaign/run", json={"domains": ["hotel_booking"], "runs_per_domain": 1, "skip_run": True})
        cid = create_resp.json()["campaign"]["id"]
        resp = client.post("/campaign/resume", json={"campaign_id": cid})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_campaign_resume_no_id(self, client):
        resp = client.post("/campaign/resume", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    @patch("services.benchmark_service.get_benchmark_service")
    def test_get_campaign_list(self, mock_bsvc, client):
        mock_bsvc.return_value = MockBenchmarkService()
        client.post("/campaign/run", json={"domains": ["hotel_booking"], "runs_per_domain": 1, "skip_run": True})
        resp = client.get("/campaign/list")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["campaigns"]) >= 1

    @patch("services.benchmark_service.get_benchmark_service")
    def test_detect_interrupted_api(self, mock_bsvc, client):
        mock_bsvc.return_value = MockBenchmarkService()
        resp = client.get("/campaign/detect-interrupted")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True


# ═══════════════════════════════════════════════════════════════════════════
# Integration Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestCampaignIntegration:

    @patch("services.benchmark_service.get_benchmark_service")
    def test_multi_domain_campaign(self, mock_bsvc, campaign_service):
        mock_bsvc.return_value = MockBenchmarkService()
        campaign = campaign_service.create_campaign(
            domains=["hotel_booking", "ecommerce", "blog_cms"],
            runs_per_domain=2,
        )
        assert campaign["total_runs"] == 6
        result = campaign_service.run_campaign(campaign["id"])
        assert result["completed_runs"] == 6
        # Verify per-domain runs
        for domain in ["hotel_booking", "ecommerce", "blog_cms"]:
            domain_runs = mem_list_campaign_runs(campaign_id=campaign["id"], domain=domain)
            assert len(domain_runs) == 2

    @patch("services.benchmark_service.get_benchmark_service")
    def test_report_files_created(self, mock_bsvc, campaign_service):
        from services.benchmark_campaign_service import REPORTS_DIR
        mock_bsvc.return_value = MockBenchmarkService()
        campaign = campaign_service.create_campaign(domains=["hotel_booking"], runs_per_domain=2)
        campaign_service.run_campaign(campaign["id"])
        cid_short = campaign["id"][:8]
        assert (REPORTS_DIR / f"aggregate_{cid_short}.json").exists()
        assert (REPORTS_DIR / f"leaderboard_{cid_short}.json").exists()
        assert (REPORTS_DIR / "domains" / f"hotel_booking_{cid_short}.json").exists()

    @patch("services.benchmark_service.get_benchmark_service")
    def test_aggregate_report_content(self, mock_bsvc, campaign_service):
        mock_bsvc.return_value = MockBenchmarkService()
        campaign = campaign_service.create_campaign(
            domains=["hotel_booking", "ecommerce"],
            runs_per_domain=3,
        )
        campaign_service.run_campaign(campaign["id"])
        report = campaign_service.get_campaign_report(campaign["id"], "aggregate")
        assert report["total_domains"] == 2
        assert report["total_completed"] == 6
        assert report["overall_avg_autonomy_score"] > 0
        assert "hotel_booking" in report["domain_reports"]
        assert "ecommerce" in report["domain_reports"]

    @patch("services.benchmark_service.get_benchmark_service")
    def test_leaderboard_ranks_by_score(self, mock_bsvc, campaign_service):
        mock_bsvc.return_value = MockBenchmarkService()
        campaign = campaign_service.create_campaign(
            domains=["hotel_booking", "ecommerce"],
            runs_per_domain=1,
        )
        campaign_service.run_campaign(campaign["id"])
        report = campaign_service.get_campaign_leaderboard(campaign["id"])
        entries = report["all_entries_sorted"]
        for i in range(len(entries) - 1):
            assert entries[i]["autonomy_score"] >= entries[i + 1]["autonomy_score"]

    @patch("services.benchmark_service.get_benchmark_service")
    def test_campaign_with_failures(self, mock_bsvc, campaign_service):
        class MixedBenchmarkService:
            def __init__(self):
                self._domains = {"hotel_booking": {}, "ecommerce": {}}
                self.call_count = 0

            def list_domains(self):
                return [{"id": d} for d in self._domains]

            def run_benchmark(self, domain, model="local", iteration=1):
                self.call_count += 1
                if self.call_count == 2:
                    return MockBenchmarkFailedResult()
                return MockBenchmarkResult()

        mock_bsvc.return_value = MixedBenchmarkService()
        campaign = campaign_service.create_campaign(domains=["hotel_booking"], runs_per_domain=3)
        campaign_service.run_campaign(campaign["id"])
        runs = mem_list_campaign_runs(campaign_id=campaign["id"])
        completed = [r for r in runs if r["status"] == "completed"]
        failed = [r for r in runs if r["status"] == "failed"]
        assert len(completed) >= 2
        assert len(failed) >= 1

    def test_run_result_fields_preserved(self, campaign_service):
        run = MockBenchmarkResult()
        assert run.autonomy_score == 0.87
        assert run.metrics.execution_time == 12.5
        assert run.metrics.cost == 0.045

    @patch("services.benchmark_service.get_benchmark_service")
    def test_reports_generated_for_all_domains(self, mock_bsvc, campaign_service):
        mock_bsvc.return_value = MockBenchmarkService()
        campaign = campaign_service.create_campaign(
            domains=["hotel_booking", "ecommerce", "blog_cms"],
            runs_per_domain=1,
        )
        campaign_service.run_campaign(campaign["id"])
        for domain in ["hotel_booking", "ecommerce", "blog_cms"]:
            assert campaign_service.get_domain_report(campaign["id"], domain) is not None
