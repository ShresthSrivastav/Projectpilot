"""Tests for workspace isolation — ChromaDB, memory store, and context propagation."""

import os

import pytest
from fastapi.testclient import TestClient

# Use dedicated test directories
os.environ["MEMORY_STORE_DIR"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_memory_store")
os.environ["CHROMA_PATH"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_chroma")
os.environ["RATE_LIMIT_ENABLED"] = "false"

from backend.main import app
from database.chroma_db import (
    _collection,
    create_job,
    get_job,
    list_jobs,
    set_workspace_context,
    get_workspace_context,
    init_db as init_chroma_db,
    init_workspace,
)
from database.memory_store import (
    store_agent_memory,
    get_agent_memory,
    record_project_analytics,
    get_project_analytics,
    init_db as init_memory_db,
)
from database.database import init_db as init_sqlalchemy_db

WS_A = "ws-alice-uuid"
WS_B = "ws-bob-uuid"


@pytest.fixture(autouse=True)
def setup():
    """Reset test state before each test."""
    os.environ["CHROMA_PATH"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_chroma")
    set_workspace_context("")
    init_memory_db()
    init_chroma_db()
    # Clean up test workspace collections in ChromaDB
    from database.chroma_db import _get_client

    client_obj = _get_client()
    for ws in [WS_A, WS_B]:
        for ct in ("jobs", "generation_logs", "requirements", "blueprints"):
            name = f"workspace_{ws}_{ct}"
            try:
                coll = client_obj.get_collection(name)
                if coll.count() > 0:
                    existing = coll.get()
                    if existing["ids"]:
                        coll.delete(existing["ids"])
            except Exception:
                pass
    # Clean up test data in memory store
    from database.memory_store import _get_conn

    conn = _get_conn()
    for tbl in ["agent_memory", "project_analytics"]:
        try:
            conn.execute(f"DELETE FROM {tbl}")
        except Exception:
            pass
    conn.commit()
    yield
    set_workspace_context("")


# ── ChromaDB isolation tests ──────────────────────────────────────────


class TestChromaDBIsolation:
    def test_workspace_context_var(self, setup):
        assert get_workspace_context() == ""
        set_workspace_context(WS_A)
        assert get_workspace_context() == WS_A
        set_workspace_context("")
        assert get_workspace_context() == ""

    def test_chromadb_jobs_isolated(self, setup):
        create_job("job-1", workspace_id=WS_A)
        create_job("job-2", workspace_id=WS_B)

        jobs_a = list_jobs(workspace_id=WS_A)
        jobs_b = list_jobs(workspace_id=WS_B)

        assert len(jobs_a) == 1
        assert jobs_a[0]["job_id"] == "job-1"
        assert len(jobs_b) == 1
        assert jobs_b[0]["job_id"] == "job-2"

    def test_chromadb_get_job_isolated(self, setup):
        create_job("shared-job", workspace_id=WS_A)
        create_job("shared-job", workspace_id=WS_B)

        got_a = get_job("shared-job", workspace_id=WS_A)
        got_b = get_job("shared-job", workspace_id=WS_B)
        assert got_a is not None
        assert got_b is not None
        assert got_a["workspace_id"] == WS_A
        assert got_b["workspace_id"] == WS_B

    def test_workspace_collection_naming(self, setup):
        coll = _collection(WS_A, "jobs")
        assert coll == f"workspace_{WS_A}_jobs"
        # Without workspace_id
        coll2 = _collection("", "jobs")
        assert coll2 == "jobs"

    def test_workspace_context_auto_detection(self, setup):
        """When workspace_id is empty but contextvar is set, use contextvar."""
        set_workspace_context(WS_A)
        create_job("ctx-job")
        found = get_job("ctx-job")  # No explicit workspace_id
        assert found is not None
        assert found["workspace_id"] == WS_A
        set_workspace_context("")

    def test_workspace_init(self, setup):
        """Verify init_workspace creates all collections."""
        from database.chroma_db import _get_client

        init_workspace("test-ws")
        for ct in ("jobs", "generation_logs", "requirements", "blueprints"):
            name = f"workspace_test-ws_{ct}"
            coll = _get_client().get_collection(name)
            assert coll is not None


# ── Memory store isolation tests ──────────────────────────────────────


class TestMemoryStoreIsolation:
    def test_agent_memory_isolated(self, setup):
        store_agent_memory("agent-x", "job-1", "key1", "val_a", workspace_id=WS_A)
        store_agent_memory("agent-x", "job-2", "key1", "val_b", workspace_id=WS_B)

        mem_a = get_agent_memory("agent-x", key="key1", workspace_id=WS_A)
        mem_b = get_agent_memory("agent-x", key="key1", workspace_id=WS_B)

        assert len(mem_a) == 1
        assert mem_a[0]["value"] == "val_a"
        assert len(mem_b) == 1
        assert mem_b[0]["value"] == "val_b"

    def test_project_analytics_isolated(self, setup):
        record_project_analytics("proj-a", project_name="Project A", workspace_id=WS_A)
        record_project_analytics("proj-b", project_name="Project B", workspace_id=WS_B)

        analytics_a = get_project_analytics(workspace_id=WS_A)
        analytics_b = get_project_analytics(workspace_id=WS_B)

        names_a = [a["project_name"] for a in analytics_a]
        names_b = [b["project_name"] for b in analytics_b]

        assert "Project A" in names_a
        assert "Project B" not in names_a
        assert "Project B" in names_b
        assert "Project A" not in names_b


# ── Audit log tests ───────────────────────────────────────────────────


class TestAuditLog:
    def test_audit_log_write_and_read(self, setup):
        from services.audit_service import log_audit_event, get_audit_logs, init_audit_db

        init_audit_db()

        log_audit_event(WS_A, "user-1", "Project Created", "project", "job-1")
        log_audit_event(WS_B, "user-2", "Project Deleted", "project", "job-2")

        logs_a = get_audit_logs(WS_A)
        logs_b = get_audit_logs(WS_B)

        assert len(logs_a) >= 1
        assert any(l["action"] == "Project Created" for l in logs_a)
        assert not any(l["action"] == "Project Deleted" for l in logs_a)

        assert len(logs_b) >= 1
        assert any(l["action"] == "Project Deleted" for l in logs_b)

    def test_audit_log_empty_workspace(self, setup):
        from services.audit_service import get_audit_logs

        logs = get_audit_logs("nonexistent-workspace")
        assert logs == []


# ── Cleanup test files ────────────────────────────────────────────────


def teardown_module():
    """Clean up test directories."""
    import shutil

    for d in ["test_memory_store", "test_chroma"]:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), d)
        if os.path.exists(path):
            shutil.rmtree(path, ignore_errors=True)
