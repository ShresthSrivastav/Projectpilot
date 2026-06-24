"""Phase 2.5 — Critical Security & Workspace Isolation Fixes.

Tests:
  1. Agent context propagation (thread safety, explicit workspace_id)
  2. RAG workspace isolation (upload/query/list/delete scoped by workspace)
  3. Membership security (guarded member list)
  4. Analytics/metrics workspace scoping
  5. Stress tests (concurrent agent execution, switching, knowledge retrieval)
"""

import gc
import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["MEMORY_STORE_DIR"] = tempfile.mkdtemp()
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["CHROMA_PATH"] = os.path.join(tempfile.mkdtemp(), "chroma")

from database.database import Base, engine, get_db
from database.memory_store import init_db as init_memory_db
from database.chroma_db import init_db as init_chroma_db
from services.jwt_service import decode_access_token

init_chroma_db()
init_memory_db()

TEST_DB_URL = "sqlite:///./test_phase25.db"
_test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
_test_session_local = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)


def override_get_db():
    db = _test_session_local()
    try:
        yield db
    finally:
        db.close()


def _cleanup():
    _test_engine.dispose()
    engine.dispose()
    gc.collect()
    for f in ["test_phase25.db", "test_phase25.db-wal", "test_phase25.db-shm"]:
        try:
            if os.path.exists(f):
                os.remove(f)
        except PermissionError:
            pass


from backend.main import app

client = TestClient(app)


def _register(name: str, email: str) -> dict:
    resp = client.post(
        "/api/auth/register",
        json={
            "name": name,
            "email": email,
            "password": "password123",
            "confirm_password": "password123",
        },
    )
    assert resp.status_code == 200, f"Register failed: {resp.text}"
    return resp.json()


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def setup_db():
    _cleanup()
    Base.metadata.create_all(bind=_test_engine)
    app.dependency_overrides[get_db] = override_get_db
    init_memory_db()
    from services.audit_service import init_audit_db

    init_audit_db()
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=_test_engine)


# ═════════════════════════════════════════════════════════════════════════════
# Section 1: Agent Context Propagation
# ═════════════════════════════════════════════════════════════════════════════


class TestAgentContextPropagation:
    def test_agent_context_dataclass(self):
        from services.agent_context import AgentContext

        ctx = AgentContext(workspace_id="ws-1", user_id="u1", job_id="job-1", project_name="Test", request_id="req-1")
        assert ctx.workspace_id == "ws-1"
        assert ctx.job_id == "job-1"
        assert ctx.is_isolated is True
        ctx2 = AgentContext()
        assert ctx2.is_isolated is False

    def test_orchestrator_receives_workspace_id(self):
        """Verify run_pipeline passes workspace_id through to Orchestrator."""
        from services.agent_context import AgentContext
        from agents.orchestrator_agent import Orchestrator

        ctx = AgentContext(workspace_id="orchestrator-test-ws", job_id="test-job", project_name="Test")
        orch = Orchestrator(context=ctx, prompt="test", model="local")
        assert orch._ws == "orchestrator-test-ws"
        assert orch.job_id == "test-job"

    def test_chromadb_operations_use_explicit_workspace_id(self):
        """All key ChromaDB operations must accept and respect workspace_id."""
        from database.chroma_db import (
            create_job,
            get_job,
            update_job_status,
            save_prompt,
            log_to_db,
            save_requirements,
            get_requirements,
            save_blueprint,
            get_blueprint,
            save_generated_project,
        )

        ws_a = "agent-test-ws-a"
        ws_b = "agent-test-ws-b"

        # Create same job ID in both workspaces
        for ws in [ws_a, ws_b]:
            create_job("agent-ctx-job", workspace_id=ws)
            save_prompt("agent-ctx-job", "test prompt", "Test", workspace_id=ws)
            update_job_status("agent-ctx-job", "running", workspace_id=ws, current_agent="test", progress_pct=50)
            log_to_db("agent-ctx-job", "TestAgent", "test log", workspace_id=ws)
            save_requirements("agent-ctx-job", {"req": True}, workspace_id=ws)
            save_blueprint("agent-ctx-job", {"bp": True}, workspace_id=ws)

        # Verify isolation
        job_a = get_job("agent-ctx-job", workspace_id=ws_a)
        job_b = get_job("agent-ctx-job", workspace_id=ws_b)
        assert job_a is not None
        assert job_b is not None
        assert job_a["workspace_id"] == ws_a
        assert job_b["workspace_id"] == ws_b
        assert job_a["job_id"] == "agent-ctx-job"

    def test_agent_log_isolated(self):
        """log_to_db with workspace_id writes to the correct collection."""
        from database.chroma_db import log_to_db, get_logs

        ws_a = "log-test-ws-a"
        ws_b = "log-test-ws-b"

        log_to_db("job-1", "AgentA", "WS A message", workspace_id=ws_a)
        log_to_db("job-1", "AgentA", "WS B message", workspace_id=ws_b)

        logs_a = get_logs("job-1", workspace_id=ws_a)
        logs_b = get_logs("job-1", workspace_id=ws_b)

        texts_a = [l["message"] for l in logs_a]
        texts_b = [l["message"] for l in logs_b]

        assert any("WS A message" in t for t in texts_a)
        assert not any("WS B message" in t for t in texts_a)
        assert any("WS B message" in t for t in texts_b)
        assert not any("WS A message" in t for t in texts_b)

    def test_agent_memory_propagated_with_workspace(self):
        """Agent memory stored with workspace_id is isolated."""
        from database.memory_store import store_agent_memory, get_agent_memory

        ws_a = "mem-propagate-ws-a"
        ws_b = "mem-propagate-ws-b"

        store_agent_memory("PlannerAgent", "job-1", "preferred_framework", "FastAPI", workspace_id=ws_a)
        store_agent_memory("PlannerAgent", "job-2", "preferred_framework", "Django", workspace_id=ws_b)

        mem_a = get_agent_memory("PlannerAgent", key="preferred_framework", workspace_id=ws_a)
        mem_b = get_agent_memory("PlannerAgent", key="preferred_framework", workspace_id=ws_b)

        vals_a = [m["value"] for m in mem_a]
        vals_b = [m["value"] for m in mem_b]
        assert "FastAPI" in vals_a
        assert "Django" not in vals_a
        assert "Django" in vals_b
        assert "FastAPI" not in vals_b

    def test_analytics_recorded_with_workspace(self):
        """Project analytics are scoped to workspace."""
        from database.memory_store import record_project_analytics, get_project_analytics

        ws_a = "analytics-propagate-a"
        ws_b = "analytics-propagate-b"

        record_project_analytics("proj-1", project_name="Project A", workspace_id=ws_a)
        record_project_analytics("proj-2", project_name="Project B", workspace_id=ws_b)

        a_projs = get_project_analytics(workspace_id=ws_a)
        b_projs = get_project_analytics(workspace_id=ws_b)

        a_names = [p["project_name"] for p in a_projs]
        b_names = [p["project_name"] for p in b_projs]
        assert "Project A" in a_names
        assert "Project B" not in a_names
        assert "Project B" in b_names
        assert "Project A" not in b_names


# ═════════════════════════════════════════════════════════════════════════════
# Section 2: RAG Workspace Isolation
# ═════════════════════════════════════════════════════════════════════════════


class TestRAGWorkspaceIsolation:
    def test_rag_upload_requires_workspace(self):
        from services.rag_service import upload_document
        import tempfile

        f = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
        f.write("test content")
        f.close()
        result = upload_document(f.name, workspace_id="")
        os.unlink(f.name)
        assert result["status"] == "error"
        assert "workspace_id is required" in result.get("error", "")

    def test_rag_upload_and_retrieve_isolated(self):
        from services.rag_service import upload_document, query, list_documents, delete_document
        import tempfile

        ws_a = "rag-test-ws-a"
        ws_b = "rag-test-ws-b"

        # Upload FastAPI doc to WS A
        f_a = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
        f_a.write("We use FastAPI for our backend architecture")
        f_a.close()
        upload_document(f_a.name, tags=["backend"], workspace_id=ws_a, uploaded_by="user-a")
        os.unlink(f_a.name)

        # Upload Django doc to WS B
        f_b = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
        f_b.write("We use Django for our backend architecture")
        f_b.close()
        upload_document(f_b.name, tags=["backend"], workspace_id=ws_b, uploaded_by="user-b")
        os.unlink(f_b.name)

        # WS A query should only see FastAPI
        results_a = query("What framework?", top_k=5, workspace_id=ws_a)
        a_texts = [r.get("text", "") for r in results_a]
        assert any("FastAPI" in t for t in a_texts), "WS A must see FastAPI docs"
        assert not any("Django" in t for t in a_texts), "WS A must NOT see Django docs"

        # WS B query should only see Django
        results_b = query("What framework?", top_k=5, workspace_id=ws_b)
        b_texts = [r.get("text", "") for r in results_b]
        assert any("Django" in t for t in b_texts), "WS B must see Django docs"
        assert not any("FastAPI" in t for t in b_texts), "WS B must NOT see FastAPI docs"

        # List documents should be workspace-scoped
        docs_a = list_documents(workspace_id=ws_a)
        docs_b = list_documents(workspace_id=ws_b)
        a_sources = [d["source"] for d in docs_a]
        b_sources = [d["source"] for d in docs_b]
        assert len(docs_a) == 1
        assert len(docs_b) == 1

        # Cleanup
        for doc in docs_a:
            delete_document(doc["doc_id"], workspace_id=ws_a)
        for doc in docs_b:
            delete_document(doc["doc_id"], workspace_id=ws_b)

    def test_rag_query_empty_without_workspace(self):
        from services.rag_service import query, list_documents

        assert query("test", workspace_id="") == []
        assert list_documents(workspace_id="") == []

    def test_rag_delete_requires_workspace(self):
        from services.rag_service import delete_document

        assert delete_document("any-id", workspace_id="") is False

    def test_rag_document_has_workspace_metadata(self):
        from services.rag_service import upload_document, list_documents, delete_document
        import tempfile

        ws = "rag-metadata-ws"
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
        f.write("test content for metadata check")
        f.close()
        upload_document(f.name, tags=["test"], workspace_id=ws, uploaded_by="tester")
        os.unlink(f.name)

        docs = list_documents(workspace_id=ws)
        assert len(docs) == 1
        assert docs[0]["workspace_id"] == ws
        assert "test" in docs[0]["tags"]

        delete_document(docs[0]["doc_id"], workspace_id=ws)

    def test_get_workspace_knowledge_collection(self):
        from services.rag_service import get_workspace_knowledge_collection

        coll = get_workspace_knowledge_collection("test-ws")
        assert coll is not None
        assert coll.name == "workspace_test-ws_knowledge"


# ═════════════════════════════════════════════════════════════════════════════
# Section 3: Membership Security
# ═════════════════════════════════════════════════════════════════════════════


class TestMembershipSecurity:
    def test_non_member_cannot_list_members(self):
        a = _register("Alice", "alice_memsec@test.com")
        b = _register("Bob", "bob_memsec@test.com")
        b_ws = client.get("/api/workspace", headers=_auth_header(b["access_token"])).json()
        b_ws_id = b_ws[0]["id"]

        # Alice tries to list Bob's workspace members by ID
        members = client.get(f"/api/workspace/members/{b_ws_id}", headers=_auth_header(a["access_token"]))
        assert members.status_code == 403, "Non-member must get 403"

    def test_member_can_list_members(self):
        owner = _register("Owner", "owner_memsec@test.com")
        user = _register("User", "user_memsec@test.com")
        owner_ws = client.get("/api/workspace", headers=_auth_header(owner["access_token"])).json()
        owner_ws_id = owner_ws[0]["id"]

        # Switch owner to their workspace
        switch = client.post(
            "/api/workspace/switch", json={"workspace_id": owner_ws_id}, headers=_auth_header(owner["access_token"])
        ).json()
        owner_token = switch["access_token"]

        # Invite user
        invite = client.post(
            "/api/workspace/current/invite",
            json={"email": "user_memsec@test.com", "role": "MEMBER"},
            headers=_auth_header(owner_token),
        ).json()
        client.post(
            "/api/workspace/accept", json={"token": invite["token"]}, headers=_auth_header(user["access_token"])
        )

        # Now user can list members
        members = client.get(f"/api/workspace/members/{owner_ws_id}", headers=_auth_header(user["access_token"]))
        assert members.status_code == 200
        data = members.json()
        assert any(m["name"] == "Owner" for m in data)
        assert any(m["name"] == "User" for m in data)


# ═════════════════════════════════════════════════════════════════════════════
# Section 4: Analytics/Metrics Scoping
# ═════════════════════════════════════════════════════════════════════════════


class TestAnalyticsScoping:
    def test_analytics_overview_scoped(self):
        from database.memory_store import record_project_analytics, get_analytics_summary

        ws_a = "analytics-scope-ws-a"
        ws_b = "analytics-scope-ws-b"

        record_project_analytics("job-a", project_name="A", workspace_id=ws_a)
        record_project_analytics("job-b", project_name="B", workspace_id=ws_b)

        overview_a = get_analytics_summary(workspace_id=ws_a)
        overview_b = get_analytics_summary(workspace_id=ws_b)

        assert overview_a.get("total_projects", 0) == 1
        assert overview_b.get("total_projects", 0) == 1

    def test_analytics_projects_scoped(self):
        from database.memory_store import get_project_analytics

        ws_a = "analytics-proj-scope-a"
        ws_b = "analytics-proj-scope-b"

        from database.memory_store import record_project_analytics

        record_project_analytics("job-a1", project_name="Project A1", workspace_id=ws_a)
        record_project_analytics("job-a2", project_name="Project A2", workspace_id=ws_a)
        record_project_analytics("job-b1", project_name="Project B1", workspace_id=ws_b)

        a_projs = get_project_analytics(workspace_id=ws_a)
        b_projs = get_project_analytics(workspace_id=ws_b)

        assert len(a_projs) == 2
        assert len(b_projs) == 1

    def test_metrics_scoped(self):
        """Verify that metrics endpoint is available and returns data."""
        reg = _register("MetricsUser", "metrics@test.com")
        ws = client.get("/api/workspace/current", headers=_auth_header(reg["access_token"])).json()

        resp = client.get("/metrics", headers=_auth_header(reg["access_token"]))
        assert resp.status_code == 200
        data = resp.json()
        assert "workspace_id" in data


# ═════════════════════════════════════════════════════════════════════════════
# Section 5: Stress Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestPhase25Stress:
    def test_concurrent_workspace_switching(self):
        reg = _register("Stress", "stress_p25@test.com")
        n = 5
        ws_list = [
            client.post("/api/workspace", json={"name": f"SWS {i}"}, headers=_auth_header(reg["access_token"])).json()
            for i in range(n)
        ]

        import concurrent.futures

        def switch_and_verify(ws_info):
            token = reg["access_token"]
            switch = client.post(
                "/api/workspace/switch", json={"workspace_id": ws_info["id"]}, headers=_auth_header(token)
            ).json()
            current = client.get("/api/workspace/current", headers=_auth_header(switch["access_token"])).json()
            return current["id"] == ws_info["id"]

        with concurrent.futures.ThreadPoolExecutor(max_workers=n) as exe:
            results = list(exe.map(switch_and_verify, ws_list))

        assert all(results), "Some switches returned stale context"

    def test_concurrent_knowledge_upload_and_query(self):
        from services.rag_service import upload_document, query, list_documents, delete_document
        import tempfile
        import concurrent.futures

        ws = "stress-knowledge-ws"
        n_docs = 5

        def upload_and_verify(i):
            f = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
            f.write(f"This is document {i} from workspace stress test")
            f.close()
            result = upload_document(f.name, tags=[f"tag-{i}"], workspace_id=ws, uploaded_by="stress-tester")
            os.unlink(f.name)
            return result["status"] == "ok"

        with concurrent.futures.ThreadPoolExecutor(max_workers=n_docs) as exe:
            results = list(exe.map(upload_and_verify, range(n_docs)))

        assert all(results), "Some uploads failed"

        docs = list_documents(workspace_id=ws)
        assert len(docs) == n_docs

        # Cleanup
        for doc in docs:
            delete_document(doc["doc_id"], workspace_id=ws)

    def test_rapid_create_and_switch(self):
        reg = _register("RapidP25", "rapid_p25@test.com")
        token = reg["access_token"]
        for i in range(20):
            ws = client.post("/api/workspace", json={"name": f"Rapid P25 WS {i}"}, headers=_auth_header(token)).json()
            switch = client.post("/api/workspace/switch", json={"workspace_id": ws["id"]}, headers=_auth_header(token))
            assert switch.status_code == 200, f"Create+switch {i} failed"
            token = switch.json()["access_token"]


# ═════════════════════════════════════════════════════════════════════════════
# Cleanup
# ═════════════════════════════════════════════════════════════════════════════


def teardown_module():
    import shutil

    mem_dir = os.environ.get("MEMORY_STORE_DIR", "")
    chroma_dir = os.environ.get("CHROMA_PATH", "")
    for d in [mem_dir, chroma_dir]:
        if d and os.path.exists(d):
            try:
                shutil.rmtree(d, ignore_errors=True)
            except Exception:
                pass
    _cleanup()
