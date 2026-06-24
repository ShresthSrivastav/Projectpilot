"""Tests for v9 subsystems: Task Graph, Knowledge Graph, Debate, Validation, Autonomous."""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Task Graph Engine Tests ───────────────────────────────────────────────


class TestTaskGraphEngine:
    def test_create_graph(self):
        from services.graph_engine import Task, TaskGraph

        g = TaskGraph()
        t1 = Task(name="Task 1")
        t2 = Task(name="Task 2", deps=[t1.id])
        g.add_task(t1)
        g.add_task(t2)
        assert len(g.tasks) == 2
        assert t1.id in g.tasks
        assert t2.id in g.tasks

    def test_dependency_tracking(self):
        from services.graph_engine import Task, TaskGraph

        g = TaskGraph()
        t1 = Task(name="A")
        t2 = Task(name="B")
        t3 = Task(name="C", deps=[t1.id, t2.id])
        g.add_task(t1)
        g.add_task(t2)
        g.add_task(t3)
        g.add_dependency(t3.id, t1.id)
        g.add_dependency(t3.id, t2.id)
        assert len(t1.dependents) == 1
        assert len(t2.dependents) == 1

    def test_topological_order(self):
        from services.graph_engine import Task, TaskGraph

        g = TaskGraph()
        t1 = Task(name="A")
        t2 = Task(name="B", deps=[t1.id])
        t3 = Task(name="C", deps=[t2.id])
        g.add_task(t1)
        g.add_task(t2)
        g.add_task(t3)
        order = g.get_topological_order()
        assert order.index(t1.id) < order.index(t2.id)
        assert order.index(t2.id) < order.index(t3.id)

    def test_ready_tasks(self):
        from services.graph_engine import Task, TaskGraph

        g = TaskGraph()
        t1 = Task(name="A")
        t2 = Task(name="B", deps=[t1.id])
        g.add_task(t1)
        g.add_task(t2)
        ready = g.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == t1.id
        g.mark_completed(t1.id)
        ready2 = g.get_ready_tasks()
        assert len(ready2) == 1
        assert ready2[0].id == t2.id

    def test_status_transitions(self):
        from services.graph_engine import Task, TaskGraph, TaskStatus

        g = TaskGraph()
        t = Task(name="Test")
        g.add_task(t)
        assert g.tasks[t.id].status == TaskStatus.PENDING
        g.mark_running(t.id)
        assert g.tasks[t.id].status == TaskStatus.RUNNING
        g.mark_completed(t.id)
        assert g.tasks[t.id].status == TaskStatus.COMPLETED

    def test_checkpoint_save_load(self):
        from services.graph_engine import Task, TaskGraph

        g = TaskGraph()
        t1 = Task(name="Checkpoint A")
        t2 = Task(name="Checkpoint B", deps=[t1.id])
        g.add_task(t1)
        g.add_task(t2)
        g.mark_completed(t1.id)
        cp = g.save_checkpoint()
        assert cp.id
        checkpoints = g.list_checkpoints()
        assert len(checkpoints) >= 1

    def test_standard_plan_builder(self):
        from services.graph_engine import PlanBuilder

        builder = PlanBuilder()
        graph = builder.build_standard_plan("Build a web app", "job-123", "local")
        assert len(graph.tasks) >= 5
        names = [t.name for t in graph.tasks.values()]
        assert "Requirements Analysis" in names

    def test_visualize_mermaid(self):
        from services.graph_engine import Task, TaskGraph

        g = TaskGraph()
        t1 = Task(name="Node 1")
        t2 = Task(name="Node 2", deps=[t1.id])
        g.add_task(t1)
        g.add_task(t2)
        viz = g.visualize_mermaid()
        assert "graph TD" in viz
        assert "-->" in viz


# ── Knowledge Graph Tests ─────────────────────────────────────────────────


class TestKnowledgeGraph:
    def test_build_empty_repo(self):
        from services.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph()
        with pytest.raises(FileNotFoundError):
            kg.build_from_repo("/nonexistent/path")

    def test_parse_python_file(self):
        from services.knowledge_graph import FileNode, KnowledgeGraph

        kg = KnowledgeGraph()
        content = """
import os
from fastapi import APIRouter
from typing import Optional

class UserService:
    pass

@app.get("/api/users")
def list_users():
    return []

def helper_func():
    pass
"""
        node = FileNode(path="test.py", file_type=".py")
        kg._parse_python_file(content, node)
        assert "os" in node.imports
        assert "fastapi" in ".".join(node.imports)
        assert "UserService" in node.classes
        assert any(
            "get" in str(a).lower() or "GET" in str(a.get("method", ""))
            for a in node.apis
            if isinstance(a.get("method"), str)
        )

    def test_parse_js_file(self):
        from services.knowledge_graph import FileNode, KnowledgeGraph

        kg = KnowledgeGraph()
        content = """
import React from 'react';
import { useState } from 'react';
export function App() {
    return <div>Hello</div>;
}
"""
        node = FileNode(path="App.jsx", file_type=".jsx")
        kg._parse_js_ts_file(content, node)
        assert any("react" in i.lower() for i in node.imports)
        assert "App" in node.exports

    def test_impact_analysis(self):
        from services.knowledge_graph import FileNode, KnowledgeGraph

        kg = KnowledgeGraph()
        kg.files["src/main.py"] = FileNode(path="src/main.py", imports=["src.utils"])
        kg.files["src/utils.py"] = FileNode(path="src/utils.py", classes=["Helper"])
        kg.files["tests/test_main.py"] = FileNode(path="tests/test_main.py", imports=["src.main"])
        kg._reverse_adj["src/main.py"].add("tests/test_main.py")
        result = kg.impact_analysis(["src/main.py"])
        assert result is not None
        assert result.impact_score >= 0

    def test_find_test_files(self):
        from services.knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph()
        kg.repo_path = Path(tempfile.mkdtemp())
        test_file = kg.repo_path / "tests/test_app.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("")
        tests = kg.find_test_files("app.py")
        assert isinstance(tests, list)

    def test_query_apis(self):
        from services.knowledge_graph import FileNode, KnowledgeGraph

        kg = KnowledgeGraph()
        kg.files["app.py"] = FileNode(path="app.py", apis=[{"method": "GET", "path": "/api/users", "handler": "list"}])
        apis = kg.query_apis()
        assert len(apis) == 1
        assert apis[0]["method"] == "GET"

    def test_architecture_summary(self):
        from services.knowledge_graph import FileNode, KnowledgeGraph

        kg = KnowledgeGraph()
        kg.files["main.py"] = FileNode(path="main.py", apis=[{"method": "GET", "path": "/"}], tech_stack=["python"])
        summary = kg.get_architecture_summary()
        assert summary["file_count"] == 1
        assert summary["api_count"] == 1

    def test_mermaid_viz(self):
        from services.knowledge_graph import FileNode, KnowledgeGraph

        kg = KnowledgeGraph()
        kg.files["a.py"] = FileNode(path="a.py")
        kg.files["b.py"] = FileNode(path="b.py")
        from services.knowledge_graph import Relationship

        kg.relationships.append(Relationship(source="a.py", target="b.py", rel_type="imports"))
        viz = kg.visualize_mermaid()
        assert "graph LR" in viz


# ── Debate System Tests ───────────────────────────────────────────────────


class TestDebateSystem:
    def test_debate_session_creation(self):
        from services.debate_system import DebateConfig, DebateSession

        config = DebateConfig(solvers=["local"])
        session = DebateSession(topic="Write a Python function to sort a list", config=config)
        assert session.id
        assert session.status == "pending"
        assert session.round.value == "independent"

    def test_consensus_weighted(self):
        from services.debate_system import ConsensusMethod, DebateSession, SolverResult

        session = DebateSession(topic="test")
        session.config.consensus_method = ConsensusMethod.WEIGHTED
        r1 = SolverResult(
            solver_id="a",
            solver_name="A",
            solution="solution a with enough length to exceed the minimum threshold of fifty characters for validation purposes",
            confidence=0.9,
        )
        r2 = SolverResult(
            solver_id="b",
            solver_name="B",
            solution="solution b with enough length to also exceed the minimum threshold of fifty characters for validation",
            confidence=0.5,
        )
        session.results = [r1, r2]
        from services.debate_system import DebateSystem

        ds = DebateSystem()
        solution, score = ds._weighted_consensus(session.results)
        assert solution
        assert score > 0

    def test_quality_evaluation(self):
        from services.debate_system import DebateSession, DebateSystem, SolverResult

        ds = DebateSystem()
        session = DebateSession(topic="test")
        session.results = [
            SolverResult(
                solver_id="a",
                solver_name="A",
                solution="valid solution here with enough length to exceed the 50 character threshold for validation",
                confidence=0.8,
            ),
            SolverResult(solver_id="b", solver_name="B", solution="", confidence=0.0),
        ]
        ds.sessions[session.id] = session
        quality = ds.evaluate_quality(session.id)
        assert quality["valid_solutions"] == 1
        assert quality["solver_count"] == 2

    def test_debate_session_to_dict(self):
        from services.debate_system import DebateSession

        session = DebateSession(topic="Test topic")
        d = session.to_dict()
        assert d["topic"] == "Test topic"
        assert "id" in d
        assert "status" in d


# ── Browser Validation Tests ──────────────────────────────────────────────


class TestBrowserValidation:
    def test_create_journey(self):
        from services.browser_validation_service import BrowserValidationService

        vs = BrowserValidationService()
        journey = vs.create_journey("Test Journey", "http://localhost:8000", tags=["smoke"])
        assert journey.id
        assert journey.name == "Test Journey"
        assert journey.base_url == "http://localhost:8000"

    def test_add_step(self):
        from services.browser_validation_service import BrowserValidationService, ValidationStep

        vs = BrowserValidationService()
        journey = vs.create_journey("Test", "http://localhost:8000")
        step = ValidationStep(action="navigate", url="http://localhost:8000", description="Home page")
        ok = vs.add_step(journey.id, step)
        assert ok
        assert len(vs.journeys[journey.id].steps) == 1

    def test_list_journeys(self):
        from services.browser_validation_service import BrowserValidationService

        vs = BrowserValidationService()
        vs.create_journey("J1", "http://localhost:8000")
        vs.create_journey("J2", "http://localhost:8000/api")
        journeys = vs.list_journeys()
        assert len(journeys) >= 2

    def test_delete_journey(self):
        from services.browser_validation_service import BrowserValidationService

        vs = BrowserValidationService()
        journey = vs.create_journey("To Delete", "http://localhost:8000")
        ok = vs.delete_journey(journey.id)
        assert ok
        assert vs.get_journey(journey.id) is None

    def test_auto_generate_tests(self):
        from services.browser_validation_service import BrowserValidationService

        vs = BrowserValidationService()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "templates").mkdir()
            (Path(tmp) / "templates" / "login.html").write_text(
                '<html><body><form><input type="password" name="pass"></form></body></html>'
            )
            journey = vs.auto_generate_tests(tmp, "http://localhost:8000", "Auto Test")
            assert len(journey.steps) > 0

    def test_regression_test_lifecycle(self):
        from services.browser_validation_service import BrowserValidationService

        vs = BrowserValidationService()
        journey = vs.create_journey("Reg Journey", "http://localhost:8000")
        rt = vs.create_regression_test("Regression 1", [journey.id])
        assert rt.id
        assert rt.name == "Regression 1"
        assert journey.id in rt.journeys

    def test_list_regression_tests(self):
        from services.browser_validation_service import BrowserValidationService

        vs = BrowserValidationService()
        vs.create_regression_test("R1")
        vs.create_regression_test("R2")
        tests = vs.list_regression_tests()
        assert len(tests) >= 2

    def test_delete_regression_test(self):
        from services.browser_validation_service import BrowserValidationService

        vs = BrowserValidationService()
        rt = vs.create_regression_test("To Delete R")
        ok = vs.delete_regression_test(rt.id)
        assert ok

    def test_execute_journey_no_session(self):
        from services.browser_validation_service import BrowserValidationService

        vs = BrowserValidationService()
        result = vs.execute_journey("nonexistent")
        assert not result.get("success", True)


# ── Autonomous Engine Tests ───────────────────────────────────────────────


class TestAutonomousEngine:
    def test_create_session(self):
        from services.autonomous_service import AutonomousConfig, AutonomousEngine

        engine = AutonomousEngine()
        config = AutonomousConfig(max_iterations=3, quality_threshold=0.5)
        session = engine.start_session("job-123", config=config)
        assert session.id
        assert session.job_id == "job-123"
        assert session.config.max_iterations == 3

    def test_get_session(self):
        from services.autonomous_service import AutonomousEngine

        engine = AutonomousEngine()
        session = engine.start_session("job-456")
        found = engine.get_session(session.id)
        assert found is not None
        assert found.id == session.id

    def test_list_sessions(self):
        from services.autonomous_service import AutonomousEngine

        engine = AutonomousEngine()
        engine.start_session("job-1")
        engine.start_session("job-2")
        sessions = engine.list_sessions()
        assert len(sessions) >= 2

    def test_iteration_history(self):
        from services.autonomous_service import AutonomousConfig, AutonomousEngine, IterationMetrics

        engine = AutonomousEngine()
        session = engine.start_session("job-history", AutonomousConfig(max_iterations=2))
        m1 = IterationMetrics(iteration=1, score=0.5, tokens_used=100, test_passed=5, test_total=10)
        m2 = IterationMetrics(iteration=2, score=0.8, tokens_used=200, test_passed=9, test_total=10)
        session.iterations = [m1, m2]
        session.initial_score = 0.5
        session.final_score = 0.8
        session.total_tokens = 300
        history = engine.get_iteration_history(session.id)
        assert "iterations" in history
        assert len(history["iterations"]) == 2

    def test_assess_code_quality(self):
        from services.autonomous_service import AutonomousEngine

        engine = AutonomousEngine()
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["BASE_DIR"] = tmp
            job_dir = Path(tmp) / "job-quality"
            job_dir.mkdir()
            (job_dir / "main.py").write_text(
                'def hello(name: str) -> str:\n    """Greet the user."""\n    return f"Hello {name}"\n'
            )
            score = engine._assess_code_quality("job-quality")
            assert score >= 0.5

    def test_session_to_dict(self):
        from services.autonomous_service import AutonomousConfig, AutonomousSession

        session = AutonomousSession(job_id="test", config=AutonomousConfig(max_iterations=5))
        d = session.to_dict()
        assert d["job_id"] == "test"
        assert d["iteration_count"] == 0

    def test_evaluate_project_nonexistent(self):
        from services.autonomous_service import AutonomousEngine

        engine = AutonomousEngine()
        score = engine._evaluate_project("nonexistent-job", "local")
        assert score == 0.0


# ── Cost Tracking Tests ───────────────────────────────────────────────────


class TestCostTracking:
    def test_record_cost(self):
        from database.memory_store import get_cost_summary, record_cost

        record_cost("job-cost-1", "test", 100, 0.001, 500, "local")
        summary = get_cost_summary("job-cost-1")
        assert summary["sessions"] >= 1
        assert summary["tokens"] >= 100

    def test_cost_summary_all(self):
        from database.memory_store import get_cost_summary

        summary = get_cost_summary()
        assert "sessions" in summary
        assert "tokens" in summary

    def test_save_iteration_history(self):
        import json

        from database.memory_store import get_iteration_history, save_iteration_history

        data = json.dumps([{"iteration": 1, "score": 0.5}])
        save_iteration_history("job-iter", "session-iter-1", data)
        history = get_iteration_history("job-iter")
        assert len(history) >= 1

    def test_save_graph_session(self):
        from database.memory_store import get_graph_session, save_graph_session

        save_graph_session("graph-test-1", "job-graph", '{"tasks": {}}', "built")
        saved = get_graph_session("graph-test-1")
        assert saved is not None
        assert saved["status"] == "built"


# ── Integration: API Route Tests ──────────────────────────────────────────


class TestAPI:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        from backend.main import app

        return TestClient(app)

    def test_health_v9(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["version"] == "13.0.0"

    def test_graph_build(self, client):
        r = client.post(
            "/graph/build",
            json={
                "prompt": "Build a todo app with FastAPI",
                "job_id": "v9-test-graph",
                "model": "local",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert "graph_id" in data
        assert "tasks" in data

    def test_graph_list(self, client):
        r = client.get("/graphs")
        assert r.status_code == 200
        assert "graphs" in r.json()

    def test_debate_start(self, client):
        r = client.post(
            "/debate/start",
            json={
                "topic": "Write a Python function to reverse a linked list",
                "solvers": ["local"],
                "context": "",
                "job_id": "v9-test-debate",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert "session_id" in data

    def test_debate_sessions(self, client):
        r = client.get("/debate/sessions")
        assert r.status_code == 200
        assert "sessions" in r.json()

    def test_validation_create_journey(self, client):
        r = client.post(
            "/validation/journey/create",
            json={
                "name": "API Test Journey",
                "base_url": "http://localhost:8000",
                "tags": ["test"],
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert "journey_id" in data

    def test_validation_list_journeys(self, client):
        r = client.get("/validation/journeys")
        assert r.status_code == 200
        assert "journeys" in r.json()

    def test_autonomous_start(self, client):
        r = client.post(
            "/autonomous/start",
            json={
                "job_id": "v9-test-auto",
                "max_iterations": 3,
                "quality_threshold": 0.5,
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert "session_id" in data

    def test_autonomous_sessions(self, client):
        r = client.get("/autonomous/sessions")
        assert r.status_code == 200
        assert "sessions" in r.json()

    def test_cost_total(self, client):
        r = client.get("/cost/total")
        assert r.status_code == 200

    def test_visualizer_graphs(self, client):
        r = client.get("/visualizer/graphs")
        assert r.status_code == 200

    def test_visualizer_debates(self, client):
        r = client.get("/visualizer/debates")
        assert r.status_code == 200

    def test_visualizer_autonomous(self, client):
        r = client.get("/visualizer/autonomous")
        assert r.status_code == 200

    def test_metrics_includes_cost(self, client):
        r = client.get("/metrics")
        assert r.status_code == 200
        data = r.json()
        assert "cost" in data

    def test_knowledge_graph_build(self, client):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "main.py").write_text("print('hello')")
            r = client.post("/kg/build", json={"repo_path": tmp})
            assert r.status_code == 200
            data = r.json()
            assert "file_count" in data

    def test_knowledge_graph_impact(self, client):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "main.py").write_text("import utils")
            (Path(tmp) / "utils.py").write_text("def helper(): pass")
            r = client.post(
                "/kg/impact",
                json={
                    "repo_path": tmp,
                    "changed_files": ["main.py"],
                },
            )
            assert r.status_code == 200
            data = r.json()
            assert "impact_score" in data

    def test_knowledge_graph_query(self, client):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text("from fastapi import APIRouter")
            r = client.post(
                "/kg/query",
                json={
                    "repo_path": tmp,
                    "file_pattern": ".py",
                },
            )
            assert r.status_code == 200
            data = r.json()
            assert "dependency_graph" in data

    def test_knowledge_graph_visualize(self, client):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text("x = 1")
            r = client.post("/kg/visualize", json={"repo_path": tmp})
            assert r.status_code == 200
            data = r.json()
            assert "mermaid" in data

    def test_knowledge_graph_architecture(self, client):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text("x = 1")
            r = client.post("/kg/architecture", json={"repo_path": tmp})
            assert r.status_code == 200
            data = r.json()
            assert "file_count" in data

    def test_validation_step_add(self, client):
        r = client.post("/validation/journey/create", json={"name": "Step Test", "base_url": "http://localhost:8000"})
        jid = r.json()["journey_id"]
        r2 = client.post(
            "/validation/journey/step",
            json={
                "journey_id": jid,
                "action": "navigate",
                "url": "http://localhost:8000",
            },
        )
        assert r2.status_code == 200

    def test_validation_auto_generate(self, client):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "login.html").write_text('<html><body><form><input type="password"></form></body></html>')
            r = client.post(
                "/validation/auto-generate",
                json={
                    "repo_path": tmp,
                    "base_url": "http://localhost:8000",
                    "name": "Auto",
                },
            )
            assert r.status_code == 200

    def test_validation_regression_create(self, client):
        r = client.post(
            "/validation/regression/create",
            json={
                "name": "RegTest",
                "journey_ids": [],
            },
        )
        assert r.status_code == 200

    def test_validation_list_regression(self, client):
        r = client.get("/validation/regression-tests")
        assert r.status_code == 200

    def test_validation_delete_journey(self, client):
        r = client.post("/validation/journey/create", json={"name": "To Delete", "base_url": "http://localhost:8000"})
        jid = r.json()["journey_id"]
        r2 = client.delete(f"/validation/journey/{jid}")
        assert r2.status_code == 200

    def test_debate_status(self, client):
        r = client.post(
            "/debate/start",
            json={
                "topic": "Test debate status",
                "solvers": ["local"],
                "job_id": "v9-test-status",
            },
        )
        sid = r.json()["session_id"]
        r2 = client.get(f"/debate/status/{sid}")
        assert r2.status_code == 200

    def test_debate_quality(self, client):
        r = client.post(
            "/debate/start",
            json={
                "topic": "Test debate quality",
                "solvers": ["local"],
            },
        )
        sid = r.json()["session_id"]
        r2 = client.get(f"/debate/quality/{sid}")
        assert r2.status_code == 200

    def test_autonomous_status(self, client):
        r = client.post(
            "/autonomous/start",
            json={
                "job_id": "v9-auto-status",
                "max_iterations": 2,
            },
        )
        sid = r.json()["session_id"]
        r2 = client.get(f"/autonomous/status/{sid}")
        assert r2.status_code == 200

    def test_autonomous_history(self, client):
        r = client.post(
            "/autonomous/start",
            json={
                "job_id": "v9-auto-history",
                "max_iterations": 2,
            },
        )
        sid = r.json()["session_id"]
        r2 = client.get(f"/autonomous/history/{sid}")
        assert r2.status_code == 200

    def test_cost_by_job(self, client):
        from database.memory_store import record_cost

        record_cost("v9-cost-job", "test", 50, 0.0005)
        r = client.get("/cost/v9-cost-job")
        assert r.status_code == 200

    def test_visualizer_progress(self, client):
        from database.memory_store import save_iteration_history

        save_iteration_history("v9-viz-job", "viz-session", json.dumps([{"i": 1}]))
        r = client.get("/visualizer/progress/v9-viz-job")
        assert r.status_code == 200
