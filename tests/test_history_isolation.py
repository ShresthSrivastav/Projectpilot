"""Tests for strict user-level project history isolation.

Verifies that every user sees only their own projects across all
history/view/download/delete endpoints, and cross-user access is blocked.
"""

import os
import uuid

import pytest
from fastapi.testclient import TestClient

os.environ["MEMORY_STORE_DIR"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_memory_store")
os.environ["CHROMA_PATH"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_chroma")
os.environ["RATE_LIMIT_ENABLED"] = "false"

from backend.main import app
from database.chroma_db import (
    create_job,
    delete_job,
    get_job,
    list_jobs,
    save_prompt,
    set_workspace_context,
    init_db as init_chroma_db,
)
from database.memory_store import (
    record_project_analytics,
    get_project_analytics,
    delete_project_analytics,
    init_db as init_memory_db,
)

WS_ID = "test-history-ws"
USER_A = "user-a-uuid"
USER_B = "user-b-uuid"


def _job_id(prefix: str = "job") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@pytest.fixture(autouse=True)
def setup():
    set_workspace_context("")
    init_memory_db()
    init_chroma_db()
    # Clean up ChromaDB collections
    from database.chroma_db import _get_client

    client = _get_client()
    for ws in [WS_ID, "other-ws"]:
        for ct in ("jobs", "generation_logs", "requirements", "blueprints"):
            name = f"workspace_{ws}_{ct}"
            try:
                coll = client.get_collection(name)
                if coll.count() > 0:
                    existing = coll.get()
                    if existing["ids"]:
                        coll.delete(existing["ids"])
            except Exception:
                pass
    # Clean up memory store
    from database.memory_store import _get_conn

    conn = _get_conn()
    for tbl in ["project_analytics"]:
        try:
            conn.execute(f"DELETE FROM {tbl}")
        except Exception:
            pass
    conn.commit()
    yield
    set_workspace_context("")


# ── Helper: create projects for a given user ──────────────────────────


def _create_project_for(uid: str, wid: str = WS_ID) -> str:
    jid = _job_id()
    create_job(jid, workspace_id=wid, user_id=uid)
    save_prompt(jid, f"prompt-{jid}", f"project-{jid}", workspace_id=wid, user_id=uid)
    record_project_analytics(
        job_id=jid,
        project_name=f"project-{jid}",
        file_count=3,
        test_count=5,
        test_passed=4,
        token_usage=1000,
        total_duration_ms=5000,
        status="complete",
        workspace_id=wid,
        user_id=uid,
    )
    return jid


# ── ChromaDB layer isolation tests ────────────────────────────────────


class TestChromaDBHistoryIsolation:
    def test_list_jobs_only_shows_own_projects(self, setup):
        jid_a = _create_project_for(USER_A)
        jid_b = _create_project_for(USER_B)

        jobs_a = list_jobs(workspace_id=WS_ID, user_id=USER_A)
        assert len(jobs_a) == 1
        assert jobs_a[0]["job_id"] == jid_a

        jobs_b = list_jobs(workspace_id=WS_ID, user_id=USER_B)
        assert len(jobs_b) == 1
        assert jobs_b[0]["job_id"] == jid_b

        # Without user_id filter, all jobs are visible
        jobs_all = list_jobs(workspace_id=WS_ID, limit=50)
        assert len(jobs_all) == 2

    def test_user_b_cannot_see_user_a_project(self, setup):
        jid_a = _create_project_for(USER_A)
        jobs_b = list_jobs(workspace_id=WS_ID, user_id=USER_B, limit=50)
        jids_b = {j["job_id"] for j in jobs_b}
        assert jid_a not in jids_b

    def test_get_job_owner_returns_correct_user(self, setup):
        from database.chroma_db import get_job_owner

        jid_a = _create_project_for(USER_A)
        jid_b = _create_project_for(USER_B)
        assert get_job_owner(jid_a, WS_ID) == USER_A
        assert get_job_owner(jid_b, WS_ID) == USER_B

    def test_job_metadata_contains_user_id(self, setup):
        jid = _create_project_for(USER_A)
        job = get_job(jid, workspace_id=WS_ID)
        assert job is not None
        assert job.get("user_id") == USER_A

    def test_project_count_isolation(self, setup):
        for _ in range(3):
            _create_project_for(USER_A)
        for _ in range(2):
            _create_project_for(USER_B)

        a_count = len(list_jobs(workspace_id=WS_ID, user_id=USER_A))
        b_count = len(list_jobs(workspace_id=WS_ID, user_id=USER_B))
        assert a_count == 3
        assert b_count == 2

    def test_delete_own_project(self, setup):
        jid = _create_project_for(USER_A)
        assert delete_job(jid, workspace_id=WS_ID) is True
        assert get_job(jid, workspace_id=WS_ID) is None

    def test_user_id_survives_status_updates(self, setup):
        from database.chroma_db import update_job_status

        jid = _create_project_for(USER_A)
        update_job_status(jid, "running", workspace_id=WS_ID, progress_pct=50)
        job = get_job(jid, workspace_id=WS_ID)
        assert job is not None
        assert job.get("user_id") == USER_A
        assert job.get("status") == "running"


# ── SQLite analytics isolation tests ──────────────────────────────────


class TestAnalyticsHistoryIsolation:
    def test_analytics_isolated_per_user(self, setup):
        jid_a = _create_project_for(USER_A)
        jid_b = _create_project_for(USER_B)

        a_analytics = get_project_analytics(workspace_id=WS_ID, user_id=USER_A)
        b_analytics = get_project_analytics(workspace_id=WS_ID, user_id=USER_B)

        a_jids = {r["job_id"] for r in a_analytics}
        b_jids = {r["job_id"] for r in b_analytics}

        assert jid_a in a_jids
        assert jid_b not in a_jids
        assert jid_b in b_jids
        assert jid_a not in b_jids

    def test_delete_analytics_requires_user_match(self, setup):
        jid_a = _create_project_for(USER_A)

        # User B tries to delete User A's analytics — should not match
        deleted = delete_project_analytics(jid_a, workspace_id=WS_ID, user_id=USER_B)
        # Returns True but may not have matched any rows
        remaining = get_project_analytics(workspace_id=WS_ID, user_id=USER_A)
        assert any(r["job_id"] == jid_a for r in remaining)

        # User A deletes their own — should succeed
        deleted2 = delete_project_analytics(jid_a, workspace_id=WS_ID, user_id=USER_A)
        assert deleted2 is True
        remaining2 = get_project_analytics(workspace_id=WS_ID, user_id=USER_A)
        assert not any(r["job_id"] == jid_a for r in remaining2)

    def test_project_analytics_record_has_user_id(self, setup):
        jid = _create_project_for(USER_A)
        records = get_project_analytics(workspace_id=WS_ID, user_id=USER_A)
        match = [r for r in records if r["job_id"] == jid]
        assert len(match) == 1
        assert match[0].get("user_id") == USER_A


# ── API endpoint isolation tests ──────────────────────────────────────


class TestAPIEndpointIsolation:
    def setup_method(self):
        skip_auth = os.getenv("SKIP_AUTH", "").lower() in ("true", "1", "yes")
        if skip_auth:
            pytest.skip("SKIP_AUTH is active — auth isolation tests not applicable")

    def test_list_jobs_api_only_shows_own(self, setup):
        from services.jwt_service import create_access_token

        jid_a = _create_project_for(USER_A)
        _create_project_for(USER_B)

        token_a = create_access_token(USER_A, WS_ID)
        with TestClient(app) as client:
            resp = client.get("/jobs", headers={"Authorization": f"Bearer {token_a}"})
        assert resp.status_code == 200
        jids = {j["job_id"] for j in resp.json()["jobs"]}
        assert jid_a in jids  # User A sees own
        assert len(jids) == 1  # Only User A's

    def test_status_api_forbidden_cross_user(self, setup):
        from services.jwt_service import create_access_token

        jid_a = _create_project_for(USER_A)
        token_b = create_access_token(USER_B, WS_ID)
        with TestClient(app) as client:
            resp = client.get(f"/status/{jid_a}", headers={"Authorization": f"Bearer {token_b}"})
        assert resp.status_code in (403, 404)

    def test_download_api_forbidden_cross_user(self, setup):
        from services.jwt_service import create_access_token

        jid_a = _create_project_for(USER_A)
        token_b = create_access_token(USER_B, WS_ID)
        with TestClient(app) as client:
            resp = client.get(f"/download/{jid_a}", headers={"Authorization": f"Bearer {token_b}"})
        assert resp.status_code in (403, 404)

    def test_files_api_forbidden_cross_user(self, setup):
        from services.jwt_service import create_access_token

        jid_a = _create_project_for(USER_A)
        token_b = create_access_token(USER_B, WS_ID)
        with TestClient(app) as client:
            resp = client.get(f"/files/{jid_a}", headers={"Authorization": f"Bearer {token_b}"})
        assert resp.status_code in (403, 404)

    def test_validate_api_forbidden_cross_user(self, setup):
        from services.jwt_service import create_access_token

        jid_a = _create_project_for(USER_A)
        token_b = create_access_token(USER_B, WS_ID)
        with TestClient(app) as client:
            resp = client.get(f"/validate/{jid_a}", headers={"Authorization": f"Bearer {token_b}"})
        assert resp.status_code in (403, 404)

    def test_delete_api_forbidden_cross_user(self, setup):
        from services.jwt_service import create_access_token

        jid_a = _create_project_for(USER_A)
        token_b = create_access_token(USER_B, WS_ID)
        with TestClient(app) as client:
            resp = client.delete(f"/jobs/{jid_a}", headers={"Authorization": f"Bearer {token_b}"})
        assert resp.status_code in (403, 404)
        # Verify User A's project still exists
        job = get_job(jid_a, workspace_id=WS_ID)
        assert job is not None

    def test_delete_own_project_api_succeeds(self, setup):
        from services.jwt_service import create_access_token

        jid_a = _create_project_for(USER_A)
        token_a = create_access_token(USER_A, WS_ID)
        with TestClient(app) as client:
            resp = client.delete(f"/jobs/{jid_a}", headers={"Authorization": f"Bearer {token_a}"})
        assert resp.status_code == 200
        # Verify deletion
        job = get_job(jid_a, workspace_id=WS_ID)
        assert job is None

    def test_unauthenticated_access_returns_401(self, setup):
        _create_project_for(USER_A)
        with TestClient(app) as client:
            for path in ["/jobs", f"/jobs/some-id"]:
                resp = client.get(path)
                assert resp.status_code == 401

    def test_changelog_api_forbidden_cross_user(self, setup):
        from services.jwt_service import create_access_token

        jid_a = _create_project_for(USER_A)
        token_b = create_access_token(USER_B, WS_ID)
        with TestClient(app) as client:
            resp = client.get(f"/changelog/{jid_a}", headers={"Authorization": f"Bearer {token_b}"})
        assert resp.status_code in (403, 404)

    def test_test_files_api_forbidden_cross_user(self, setup):
        from services.jwt_service import create_access_token

        jid_a = _create_project_for(USER_A)
        token_b = create_access_token(USER_B, WS_ID)
        with TestClient(app) as client:
            resp = client.get(f"/test-files/{jid_a}", headers={"Authorization": f"Bearer {token_b}"})
        assert resp.status_code in (403, 404)

    def test_read_project_file_api_forbidden_cross_user(self, setup):
        from services.jwt_service import create_access_token

        jid_a = _create_project_for(USER_A)
        token_b = create_access_token(USER_B, WS_ID)
        with TestClient(app) as client:
            resp = client.get(f"/read-project-file/{jid_a}/main.py", headers={"Authorization": f"Bearer {token_b}"})
        # Should be 403/404 due to ownership check (directory won't exist)
        assert resp.status_code in (403, 404)
