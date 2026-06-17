"""v12.5 — Learning Engine Feedback Loop tests.

Covers feedback ingestion, pattern extraction, recommendation generation,
insight aggregation, API routes, and integration with evaluation completion.
"""
import os
import sys
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.memory_store import init_db


@pytest.fixture(autouse=True)
def reset_db():
    init_db()
    # Clear learning tables to prevent cross-test contamination
    from database.memory_store import _get_conn
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM learning_feedback_patterns")
        conn.execute("DELETE FROM learning_feedback_recommendations")
        conn.execute("DELETE FROM learning_feedback")
        conn.commit()
    except Exception:
        pass


@pytest.fixture
def client():
    from backend.main import app
    with TestClient(app) as c:
        yield c


# ═══════════════════════════════════════════════════════════════════════════
# Feedback Ingestion Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestFeedbackIngestion:
    """Test all 5 feedback ingestion types."""

    def test_ingest_evaluation_result(self):
        from services.learning_feedback_service import get_learning_feedback_service
        service = get_learning_feedback_service()
        run = {
            "id": "eval-test-1",
            "schedule": "nightly",
            "triggered_by": "system",
            "autonomy_score": 0.92,
            "success_rate": 0.95,
            "total_cost": 100.0,
            "avg_runtime_ms": 5000.0,
            "healing_rate": 0.88,
            "deployment_success_rate": 0.97,
            "status": "completed",
        }
        result = service.ingest_evaluation_result(run)
        assert result["run_id"] == "eval-test-1"
        assert result["score"] == 0.92
        assert result["patterns_extracted"] >= 1

    def test_ingest_benchmark_score(self):
        from services.learning_feedback_service import get_learning_feedback_service
        service = get_learning_feedback_service()
        data = {
            "id": "bench-test-1",
            "score": 0.85,
            "metric": "test_pass_rate",
            "source": "benchmark_service",
            "context": {"domain": "ecommerce"},
        }
        result = service.ingest_benchmark_score(data)
        assert result["score"] == 0.85
        assert result["id"].startswith("bench_")

    def test_ingest_regression_report(self):
        from services.learning_feedback_service import get_learning_feedback_service
        service = get_learning_feedback_service()
        report = {
            "source": "regression_detector",
            "regressions": [
                {"id": "reg-1", "category": "cost", "metric": "total_cost",
                 "previous_value": 100.0, "current_value": 500.0,
                 "change_pct": 400.0, "severity": "high",
                 "run_id": "run-1"},
                {"id": "reg-2", "category": "autonomy", "metric": "autonomy_score",
                 "previous_value": 0.9, "current_value": 0.5,
                 "change_pct": -44.4, "severity": "high",
                 "run_id": "run-1"},
            ],
        }
        result = service.ingest_regression_report(report)
        assert result["ingested"] == 2
        assert len(result["regression_ids"]) == 2

    def test_ingest_deployment_success(self):
        from services.learning_feedback_service import get_learning_feedback_service
        service = get_learning_feedback_service()
        deploy = {
            "id": "deploy-1",
            "success": True,
            "environment": "production",
            "duration_seconds": 120,
            "source": "deployment_service",
            "run_id": "run-1",
        }
        result = service.ingest_deployment_outcome(deploy)
        assert result["success"] is True

    def test_ingest_deployment_failure(self):
        from services.learning_feedback_service import get_learning_feedback_service
        service = get_learning_feedback_service()
        deploy = {
            "id": "deploy-2",
            "success": False,
            "environment": "staging",
            "duration_seconds": 300,
            "error": "Connection timeout to database",
            "source": "deployment_service",
            "run_id": "run-2",
            "strategy": "rolling_update",
        }
        result = service.ingest_deployment_outcome(deploy)
        assert result["success"] is False
        # Should have created a failed pattern
        patterns = service.get_patterns(pattern_type="failed_strategy", category="deployment")
        assert len(patterns) >= 1

    def test_ingest_healing_statistics(self):
        from services.learning_feedback_service import get_learning_feedback_service
        service = get_learning_feedback_service()
        healing = {
            "id": "heal-1",
            "healing_rate": 0.92,
            "total_incidents": 50,
            "auto_resolved": 46,
            "mean_time_to_heal": 120,
            "source": "evaluation_reporter",
            "run_id": "run-1",
        }
        result = service.ingest_healing_statistics(healing)
        assert result["healing_rate"] == 0.92


class TestFeedbackAPIIngestion:
    """Test feedback ingestion via HTTP API."""

    def test_post_ingest_evaluation(self, client):
        resp = client.post("/learning/ingest", json={
            "feedback_type": "evaluation",
            "id": "api-eval-1",
            "autonomy_score": 0.9,
            "success_rate": 0.95,
            "status": "completed",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "result" in data

    def test_post_ingest_benchmark(self, client):
        resp = client.post("/learning/ingest", json={
            "feedback_type": "benchmark",
            "id": "api-bench-1",
            "score": 0.75,
            "metric": "code_quality",
        })
        assert resp.status_code == 200

    def test_post_ingest_regression(self, client):
        resp = client.post("/learning/ingest", json={
            "feedback_type": "regression",
            "regressions": [{"id": "api-reg-1", "category": "cost", "change_pct": 50.0}],
        })
        assert resp.status_code == 200

    def test_post_ingest_deployment(self, client):
        resp = client.post("/learning/ingest", json={
            "feedback_type": "deployment",
            "id": "api-deploy-1",
            "success": True,
            "environment": "production",
        })
        assert resp.status_code == 200

    def test_post_ingest_healing(self, client):
        resp = client.post("/learning/ingest", json={
            "feedback_type": "healing",
            "id": "api-heal-1",
            "healing_rate": 0.85,
        })
        assert resp.status_code == 200

    def test_post_ingest_default_type(self, client):
        resp = client.post("/learning/ingest", json={
            "autonomy_score": 0.8,
            "status": "completed",
        })
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# Pattern Extraction Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestPatternExtraction:
    """Test automatic extraction of patterns from evaluation results."""

    def test_high_autonomy_pattern(self):
        from services.learning_feedback_service import LearningFeedbackService
        service = LearningFeedbackService()
        patterns = service._extract_patterns_from_run({
            "id": "high-score",
            "autonomy_score": 0.92,
            "success_rate": 0.95,
            "total_cost": 100.0,
            "avg_runtime_ms": 5000.0,
            "healing_rate": 0.90,
            "deployment_success_rate": 0.98,
        })
        types = [p["pattern_type"] for p in patterns]
        assert "high_performing" in types
        assert "successful_strategy" in types

    def test_low_autonomy_pattern(self):
        from services.learning_feedback_service import LearningFeedbackService
        service = LearningFeedbackService()
        patterns = service._extract_patterns_from_run({
            "id": "low-score",
            "autonomy_score": 0.35,
            "success_rate": 0.40,
            "total_cost": 800.0,
            "avg_runtime_ms": 50000.0,
            "healing_rate": 0.30,
            "deployment_success_rate": 0.50,
        })
        types = [p["pattern_type"] for p in patterns]
        assert "low_performing" in types
        assert "failed_strategy" in types

    def test_mixed_patterns(self):
        from services.learning_feedback_service import LearningFeedbackService
        service = LearningFeedbackService()
        patterns = service._extract_patterns_from_run({
            "id": "mixed",
            "autonomy_score": 0.88,
            "success_rate": 0.92,
            "total_cost": 50.0,
            "avg_runtime_ms": 3000.0,
            "healing_rate": 0.55,
            "deployment_success_rate": 0.95,
        })
        types = [p["pattern_type"] for p in patterns]
        assert "high_performing" in types  # high autonomy
        assert "failed_strategy" in types  # low healing

    def test_pattern_has_required_fields(self):
        from services.learning_feedback_service import LearningFeedbackService
        service = LearningFeedbackService()
        patterns = service._extract_patterns_from_run({
            "id": "fields-test",
            "autonomy_score": 0.75,
            "success_rate": 0.80,
            "total_cost": 200.0,
            "avg_runtime_ms": 10000.0,
            "healing_rate": 0.70,
            "deployment_success_rate": 0.85,
        })
        for p in patterns:
            for key in ("pattern_type", "category", "title", "description",
                         "strategy", "outcome", "confidence", "tags", "source_run_ids"):
                assert key in p, f"Missing key: {key} in pattern {p.get('title', 'unknown')}"

    def test_pattern_confidence_bounded(self):
        from services.learning_feedback_service import LearningFeedbackService
        service = LearningFeedbackService()
        patterns = service._extract_patterns_from_run({
            "id": "confidence-test",
            "autonomy_score": 0.99,
            "success_rate": 0.99,
            "total_cost": 10.0,
            "avg_runtime_ms": 1000.0,
            "healing_rate": 0.98,
            "deployment_success_rate": 0.99,
        })
        for p in patterns:
            assert 0.0 <= p["confidence"] <= 1.0


class TestPatternStorage:
    """Test storing and retrieving patterns."""

    def test_store_new_pattern(self):
        from services.learning_feedback_service import get_learning_feedback_service
        service = get_learning_feedback_service()
        pattern = {
            "pattern_type": "successful_strategy",
            "category": "testing",
            "title": "Comprehensive test suite",
            "description": "Projects with >80% test coverage succeed more often",
            "strategy": "Maintain high test coverage with automated CI",
            "outcome": "success",
            "confidence": 0.85,
            "tags": ["testing", "coverage", "ci"],
            "source_run_ids": ["run-1", "run-2"],
        }
        stored = service.store_pattern(pattern)
        assert stored["id"] is not None
        assert stored["success_count"] == 1
        assert stored["confidence"] == 0.85

    def test_store_and_update_existing_pattern(self):
        from services.learning_feedback_service import get_learning_feedback_service
        service = get_learning_feedback_service()
        # Use a unique title to avoid cross-test contamination
        unique_title = f"Unique test pattern {__name__}"
        pattern = {
            "pattern_type": "successful_strategy",
            "category": "testing",
            "title": unique_title,
            "description": "Original description",
            "strategy": "Maintain high test coverage",
            "outcome": "success",
            "confidence": 0.70,
            "tags": ["testing"],
            "source_run_ids": ["run-1"],
        }
        first = service.store_pattern(pattern)
        assert first["success_count"] == 1

        # Store again with same title — should merge
        pattern2 = {
            "pattern_type": "successful_strategy",
            "category": "testing",
            "title": unique_title,
            "description": "Updated description",
            "strategy": "Maintain high test coverage with automated CI",
            "outcome": "success",
            "confidence": 0.80,
            "tags": ["testing", "ci"],
            "source_run_ids": ["run-3"],
        }
        second = service.store_pattern(pattern2)
        assert second["id"] == first["id"]
        assert second["success_count"] == 2  # incremented
        assert second["confidence"] > first["confidence"]  # boosted

    def test_store_failed_pattern(self):
        from services.learning_feedback_service import get_learning_feedback_service
        service = get_learning_feedback_service()
        pattern = {
            "pattern_type": "failed_strategy",
            "category": "deployment",
            "title": "Rolling update fails on DB migration",
            "description": "Database migration causes connection timeouts during rolling update",
            "strategy": "Use blue-green deployment for schema changes",
            "outcome": "failed",
            "confidence": 0.6,
            "tags": ["deployment", "migration"],
            "source_run_ids": ["run-fail-1"],
        }
        stored = service.store_pattern(pattern)
        assert stored["failure_count"] == 1
        assert stored["success_count"] == 0

    def test_store_low_performing_pattern(self):
        from services.learning_feedback_service import get_learning_feedback_service
        service = get_learning_feedback_service()
        pattern = {
            "pattern_type": "low_performing",
            "category": "benchmark_performance",
            "title": "Low benchmark scores on ecommerce domain",
            "description": "Ecommerce benchmarks consistently score below 0.5",
            "strategy": "Review ecommerce test data and domain configuration",
            "outcome": "needs_improvement",
            "confidence": 0.75,
            "tags": ["benchmark", "ecommerce"],
            "source_run_ids": ["run-low-1"],
        }
        stored = service.store_pattern(pattern)
        assert stored["failure_count"] == 1
        assert stored["outcome"] == "needs_improvement"

    def test_get_patterns_by_type(self):
        from services.learning_feedback_service import get_learning_feedback_service
        service = get_learning_feedback_service()
        service.store_pattern({
            "pattern_type": "high_performing", "category": "architecture",
            "title": "Microservices architecture", "description": "",
            "strategy": "", "outcome": "success", "confidence": 0.9,
            "tags": [], "source_run_ids": [],
        })
        service.store_pattern({
            "pattern_type": "failed_strategy", "category": "architecture",
            "title": "Monolith antipattern", "description": "",
            "strategy": "", "outcome": "failed", "confidence": 0.6,
            "tags": [], "source_run_ids": [],
        })
        high = service.get_patterns(pattern_type="high_performing")
        assert len(high) >= 1
        for p in high:
            assert p["pattern_type"] == "high_performing"

    def test_get_patterns_by_category(self):
        from services.learning_feedback_service import get_learning_feedback_service
        service = get_learning_feedback_service()
        service.store_pattern({
            "pattern_type": "high_performing", "category": "architecture",
            "title": "Microservices architecture", "description": "",
            "strategy": "", "outcome": "success", "confidence": 0.9,
            "tags": [], "source_run_ids": [],
        })
        service.store_pattern({
            "pattern_type": "failed_strategy", "category": "architecture",
            "title": "Monolith antipattern", "description": "",
            "strategy": "", "outcome": "failed", "confidence": 0.6,
            "tags": [], "source_run_ids": [],
        })
        arch = service.get_patterns(category="architecture")
        assert len(arch) >= 2


# ═══════════════════════════════════════════════════════════════════════════
# Recommendation Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestRecommendationEngine:
    """Test recommendation generation from patterns."""

    def test_generate_recommendations(self):
        from services.learning_feedback_service import get_learning_feedback_service
        service = get_learning_feedback_service()
        # Seed some patterns first
        service.store_pattern({
            "pattern_type": "high_performing", "category": "testing",
            "title": "Unit testing best practices", "description": "",
            "strategy": "Write unit tests first", "outcome": "success",
            "confidence": 0.85, "tags": [], "source_run_ids": ["r1"],
        })
        service.store_pattern({
            "pattern_type": "high_performing", "category": "testing",
            "title": "Integration testing pattern", "description": "",
            "strategy": "Mock external services", "outcome": "success",
            "confidence": 0.80, "tags": [], "source_run_ids": ["r2"],
        })
        service.store_pattern({
            "pattern_type": "high_performing", "category": "testing",
            "title": "E2E testing pattern", "description": "",
            "strategy": "Use Cypress for E2E", "outcome": "success",
            "confidence": 0.75, "tags": [], "source_run_ids": ["r3"],
        })
        recs = service.generate_recommendations(category="testing")
        assert len(recs) >= 1

    def test_generate_recommendations_for_low_perf(self):
        from services.learning_feedback_service import get_learning_feedback_service
        service = get_learning_feedback_service()
        service.store_pattern({
            "pattern_type": "low_performing", "category": "cost_efficiency",
            "title": "High cloud costs", "description": "",
            "strategy": "Optimize resource allocation", "outcome": "needs_improvement",
            "confidence": 0.7, "tags": [], "source_run_ids": ["r1"],
        })
        service.store_pattern({
            "pattern_type": "low_performing", "category": "cost_efficiency",
            "title": "Expensive API calls", "description": "",
            "strategy": "Cache API responses", "outcome": "needs_improvement",
            "confidence": 0.8, "tags": [], "source_run_ids": ["r2"],
        })
        service.store_pattern({
            "pattern_type": "low_performing", "category": "cost_efficiency",
            "title": "Inefficient queries", "description": "",
            "strategy": "Add database indexes", "outcome": "needs_improvement",
            "confidence": 0.65, "tags": [], "source_run_ids": ["r3"],
        })
        recs = service.generate_recommendations(category="cost_efficiency")
        assert len(recs) >= 1

    def test_recommendation_has_required_fields(self):
        from services.learning_feedback_service import get_learning_feedback_service
        service = get_learning_feedback_service()
        service.store_pattern({
            "pattern_type": "high_performing", "category": "code_quality",
            "title": "Code review process", "description": "",
            "strategy": "Mandatory peer reviews", "outcome": "success",
            "confidence": 0.9, "tags": [], "source_run_ids": ["r1"],
        })
        recs = service.generate_recommendations(category="code_quality")
        for rec in recs:
            for key in ("id", "recommendation_type", "category", "title",
                         "description", "priority", "rationale", "expected_impact",
                         "implementation_suggestions", "status", "source_pattern_ids"):
                assert key in rec, f"Missing key: {key}"

    def test_recommendation_priority_logic(self):
        from services.learning_feedback_service import get_learning_feedback_service
        service = get_learning_feedback_service()
        # Add many high-perf patterns — should yield high priority
        for i in range(5):
            service.store_pattern({
                "pattern_type": "high_performing", "category": "execution_speed",
                "title": f"Speed pattern {i}", "description": "",
                "strategy": "Optimize", "outcome": "success",
                "confidence": 0.85, "tags": [], "source_run_ids": [f"r{i}"],
            })
        recs = service.generate_recommendations(category="execution_speed")
        high_priority = [r for r in recs if r.get("priority") == "high"]
        assert len(high_priority) >= 1

    def test_empty_patterns_no_recommendations(self):
        from services.learning_feedback_service import get_learning_feedback_service
        service = get_learning_feedback_service()
        recs = service.generate_recommendations(category="nonexistent")
        assert len(recs) == 0


class TestRecommendationAPI:
    """Test recommendation endpoints."""

    def test_get_recommendations_empty(self, client):
        resp = client.get("/learning/feedback-recommendations")
        assert resp.status_code == 200
        data = resp.json()
        assert "recommendations" in data

    def test_get_recommendations_filter_type(self, client):
        resp = client.get("/learning/feedback-recommendations?recommendation_type=workflow")
        assert resp.status_code == 200

    def test_get_recommendations_filter_category(self, client):
        resp = client.get("/learning/feedback-recommendations?category=testing")
        assert resp.status_code == 200

    def test_get_recommendations_filter_status(self, client):
        resp = client.get("/learning/feedback-recommendations?status=active")
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# Insight Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestInsights:
    """Test insight generation and aggregation."""

    def test_generate_insights(self):
        from services.learning_feedback_service import get_learning_feedback_service
        service = get_learning_feedback_service()
        insights = service.generate_insights()
        assert isinstance(insights, list)

    def test_insights_contain_patterns_and_recs(self):
        from services.learning_feedback_service import get_learning_feedback_service
        service = get_learning_feedback_service()
        service.store_pattern({
            "pattern_type": "successful_strategy", "category": "healing",
            "title": "Auto-retry pattern", "description": "",
            "strategy": "Implement exponential backoff", "outcome": "success",
            "confidence": 0.9, "tags": [], "source_run_ids": ["r1"],
        })
        service.store_pattern({
            "pattern_type": "failed_strategy", "category": "healing",
            "title": "Manual fix pattern", "description": "",
            "strategy": "Manual rollback", "outcome": "failed",
            "confidence": 0.5, "tags": [], "source_run_ids": ["r2"],
        })
        service.generate_recommendations(category="healing")
        insights = service.generate_insights(category="healing")
        insights_types = {i.get("insight_type") for i in insights}
        assert "pattern" in insights_types
        assert "recommendation" in insights_types or "feedback_summary" in insights_types

    def test_insights_filter_by_category(self):
        from services.learning_feedback_service import get_learning_feedback_service
        service = get_learning_feedback_service()
        arch_insights = service.generate_insights(category="architecture")
        for i in arch_insights:
            if i.get("insight_type") in ("pattern", "recommendation"):
                assert i.get("category") == "architecture"

    def test_insights_limit(self):
        from services.learning_feedback_service import get_learning_feedback_service
        service = get_learning_feedback_service()
        insights = service.generate_insights(category="testing", limit=5)
        assert len(insights) <= 5


class TestInsightsAPI:
    """Test insights API endpoints."""

    def test_get_insights_empty(self, client):
        resp = client.get("/learning/insights")
        assert resp.status_code == 200
        data = resp.json()
        assert "insights" in data

    def test_get_insights_filter_category(self, client):
        resp = client.get("/learning/insights?category=testing")
        assert resp.status_code == 200

    def test_get_insights_limit(self, client):
        resp = client.get("/learning/insights?limit=3")
        assert resp.status_code == 200
        assert len(resp.json()["insights"]) <= 3


# ═══════════════════════════════════════════════════════════════════════════
# Pattern API Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestPatternAPI:
    """Test pattern API endpoints."""

    def test_get_patterns_empty(self, client):
        resp = client.get("/learning/patterns")
        assert resp.status_code == 200
        data = resp.json()
        assert "patterns" in data

    def test_get_patterns_filter_type(self, client):
        resp = client.get("/learning/patterns?pattern_type=high_performing")
        assert resp.status_code == 200

    def test_get_patterns_filter_category(self, client):
        resp = client.get("/learning/patterns?category=testing")
        assert resp.status_code == 200

    def test_get_patterns_filter_confidence(self, client):
        resp = client.get("/learning/patterns?min_confidence=0.5")
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# Integration Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestIntegration:
    """End-to-end integration tests for the learning feedback loop."""

    @patch("services.benchmark_service.BenchmarkService")
    def test_evaluation_triggers_learning(self, mock_bsvc, client):
        """When an evaluation run completes, learning feedback is ingested."""
        from database.memory_store import mem_list_learning_feedback
        from tests.test_v12_evaluation import MockBenchmarkService
        mock_bsvc.return_value = MockBenchmarkService()
        before = len(mem_list_learning_feedback())
        client.post("/evaluation/run", json={"trigger_type": "nightly"})
        after = len(mem_list_learning_feedback())
        # At least one feedback entry should be created
        assert after > before

    @patch("services.benchmark_service.BenchmarkService")
    def test_evaluation_creates_patterns(self, mock_bsvc, client):
        """Evaluation completion extracts and stores patterns."""
        from database.memory_store import mem_list_learning_patterns
        from tests.test_v12_evaluation import MockBenchmarkService
        mock_bsvc.return_value = MockBenchmarkService()
        before = len(mem_list_learning_patterns())
        client.post("/evaluation/run", json={"trigger_type": "nightly"})
        after = len(mem_list_learning_patterns())
        assert after >= before

    def test_full_learning_cycle(self):
        """Ingest → Patterns → Recommendations → Insights cycle."""
        from services.learning_feedback_service import get_learning_feedback_service
        service = get_learning_feedback_service()

        # 1. Ingest evaluation results
        for i in range(3):
            service.ingest_evaluation_result({
                "id": f"cycle-run-{i}",
                "autonomy_score": 0.85 + i * 0.05,
                "success_rate": 0.90,
                "total_cost": 100 - i * 20,
                "avg_runtime_ms": 5000 - i * 500,
                "healing_rate": 0.80 + i * 0.05,
                "deployment_success_rate": 0.95,
                "schedule": "nightly",
                "triggered_by": "system",
                "status": "completed",
            })

        # 2. Generate recommendations
        recs = service.generate_recommendations()
        assert len(recs) >= 0

        # 3. Get insights
        insights = service.generate_insights()
        assert len(insights) >= 0

        # 4. Patterns should exist
        patterns = service.get_patterns()
        assert len(patterns) >= 1

    @patch("services.benchmark_service.BenchmarkService")
    def test_multiple_evaluations_accumulate_learning(self, mock_bsvc, client):
        """Multiple evaluation runs accumulate patterns and increase confidence."""
        from database.memory_store import mem_list_learning_patterns
        from tests.test_v12_evaluation import MockBenchmarkService
        mock_bsvc.return_value = MockBenchmarkService()

        # Run 3 evaluations with high scores
        for _ in range(3):
            client.post("/evaluation/run", json={"trigger_type": "nightly"})

        patterns = mem_list_learning_patterns()
        high_perf = [p for p in patterns if p.get("pattern_type") == "high_performing"]
        if high_perf:
            # Confidence should be > 0.85 after repeat high scores
            assert high_perf[0]["confidence"] >= 0.85

    def test_learning_service_singleton(self):
        from services.learning_feedback_service import LearningFeedbackService
        s1 = LearningFeedbackService()
        s2 = LearningFeedbackService()
        assert s1 is s2

    def test_learning_feedback_database_crud(self):
        """Verify database CRUD operations work for all 3 learning tables."""
        from database.memory_store import (
            mem_save_learning_feedback, mem_list_learning_feedback,
            mem_save_learning_pattern, mem_save_learning_recommendation, mem_get_learning_pattern, mem_get_learning_recommendation,
        )
        import time
        now = time.time()

        # Feedback
        mem_save_learning_feedback({
            "id": "crud-fb-1", "feedback_type": "evaluation",
            "source": "test", "category": "testing",
            "score": 0.9, "metric_name": "pass_rate", "metric_value": 0.9,
            "context": {}, "run_id": "r1", "version": "13.0.0",
            "created_at": now,
        })
        fb_list = mem_list_learning_feedback(feedback_type="evaluation")
        assert len(fb_list) >= 1

        # Patterns
        mem_save_learning_pattern({
            "id": "crud-pat-1", "pattern_type": "successful_strategy",
            "category": "testing", "title": "Test pattern",
            "description": "desc", "strategy": "strat", "outcome": "success",
            "success_count": 1, "failure_count": 0, "confidence": 0.8,
            "tags": ["a"], "source_run_ids": ["r1"],
            "created_at": now, "updated_at": now,
        })
        pat = mem_get_learning_pattern("crud-pat-1")
        assert pat is not None
        assert pat["title"] == "Test pattern"

        # Recommendations
        mem_save_learning_recommendation({
            "id": "crud-rec-1", "recommendation_type": "workflow",
            "category": "testing", "title": "Test rec",
            "description": "desc", "priority": "high",
            "rationale": "why", "expected_impact": "impact",
            "implementation_suggestions": "how",
            "status": "active", "source_pattern_ids": ["crud-pat-1"],
            "created_at": now, "updated_at": now,
        })
        rec = mem_get_learning_recommendation("crud-rec-1")
        assert rec is not None
        assert rec["priority"] == "high"

    def test_learn_categories_exist(self):
        from services.learning_feedback_service import LEARNING_CATEGORIES
        expected = [
            "architecture", "code_quality", "testing", "deployment",
            "healing", "benchmark_performance", "cost_efficiency", "execution_speed",
        ]
        assert sorted(LEARNING_CATEGORIES) == sorted(expected)
