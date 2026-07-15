"""pytest test suite — ProjectPilot

Covers:
  - All v3 tests (health, generate, status, jobs, ChromaDB, agents, services)
  - New v4 endpoints: /clarify, /cancel, /regenerate-file, /files, /validate
  - CleanupService unit tests
  - TestGenAgent unit tests
  - StackConfig validation tests
  - LLM retry/backoff (mocked)
"""

import json
import os
import shutil
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ["CHROMA_PATH"] = "./test_chroma_data_v4"
os.environ["GENERATED_PROJECTS_DIR"] = "./test_generated_projects_v4"
os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"
os.environ["ZIP_RETENTION_HOURS"] = "1"
os.environ["ADMIN_API_KEY"] = "test-admin-key-123"
os.environ["USER_API_KEY"] = "test-user-key-456"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["SKIP_AUTH"] = "true"

from backend.main import app
from database.chroma_db import (
    create_job,
    get_blueprint,
    get_job,
    get_logs,
    get_requirements,
    init_db,
    log_to_db,
    save_blueprint,
    save_requirements,
    update_job_status,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module", autouse=True)
def setup_and_teardown():
    init_db()
    yield
    for d in ["./test_chroma_data_v4", "./test_generated_projects_v4"]:
        p = Path(d)
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _make_job(client, prompt="Build a task manager with CRUD and SQLite database."):
    with patch("backend.routes.pipeline_routes.run_pipeline"):
        r = client.post(
            "/generate-project",
            json={
                "prompt": prompt,
                "project_name": "TestApp",
                "model": "local",
            },
        )
    assert r.status_code == 200
    return r.json()["job_id"]


# ── Health


def test_health_200(client):
    assert client.get("/health").status_code == 200


def test_health_fields(client):
    d = client.get("/health").json()
    assert d["status"] == "ok"
    for f in ("ollama_online", "available_models", "models_ready", "pull_status"):
        assert f in d


# ── Generate


@patch("backend.routes.pipeline_routes.run_pipeline")
def test_generate_valid(mock_p, client):
    r = client.post(
        "/generate-project",
        json={
            "prompt": "Build a task manager with CRUD and SQLite database.",
            "project_name": "TaskApp",
            "model": "local",
        },
    )
    assert r.status_code == 200
    d = r.json()
    assert "job_id" in d
    assert d["status"] == "queued"


@patch("backend.routes.pipeline_routes.run_pipeline")
def test_generate_with_stack(mock_p, client):
    r = client.post(
        "/generate-project",
        json={
            "prompt": "Build an inventory system with product CRUD.",
            "project_name": "InvApp",
            "model": "local",
            "stack": {"backend": "fastapi", "frontend": "streamlit", "db": "sqlite"},
        },
    )
    assert r.status_code == 200
    assert "job_id" in r.json()


@patch("backend.routes.pipeline_routes.run_pipeline")
def test_generate_with_clarification(mock_p, client):
    r = client.post(
        "/generate-project",
        json={
            "prompt": "Build a student system.",
            "project_name": "StudentApp",
            "model": "local",
            "clarification": "Include attendance tracking and grades.",
        },
    )
    assert r.status_code == 200


def test_generate_invalid_stack(client):
    r = client.post(
        "/generate-project",
        json={
            "prompt": "Build a task manager with CRUD.",
            "project_name": "App",
            "stack": {"backend": "django", "frontend": "streamlit", "db": "sqlite"},
        },
    )
    assert r.status_code == 422


def test_generate_empty_prompt(client):
    assert client.post("/generate-project", json={"prompt": "", "project_name": "T"}).status_code == 422


def test_generate_short_prompt(client):
    assert client.post("/generate-project", json={"prompt": "Hi", "project_name": "T"}).status_code == 422


def test_generate_missing_prompt(client):
    assert client.post("/generate-project", json={"project_name": "T"}).status_code == 422


# ── Clarify ───────────────────────────────────────────────────────────────────


def test_clarify_returns_question_or_null(client):
    with patch("agents.requirement_agent.call_model", return_value="CLEAR"):
        r = client.post("/clarify", json={"prompt": "Build a task manager with CRUD.", "model": "local"})
    assert r.status_code == 200
    d = r.json()
    assert "question" in d
    assert d["question"] is None


def test_clarify_returns_question(client):
    with patch("agents.requirement_agent.call_model", return_value="Do you need user authentication?"):
        r = client.post("/clarify", json={"prompt": "Build something.", "model": "local"})
    assert r.status_code == 200
    d = r.json()
    assert d["question"] is not None
    assert "?" in d["question"]


def test_clarify_short_prompt(client):
    r = client.post("/clarify", json={"prompt": "Hi", "model": "local"})
    assert r.status_code == 422


# ── Status ────────────────────────────────────────────────────────────────────


def test_status_valid(client):
    jid = _make_job(client)
    r = client.get(f"/status/{jid}")
    assert r.status_code == 200
    assert r.json()["job_id"] == jid


def test_status_not_found(client):
    assert client.get("/status/00000000-0000-0000-0000-000000000000").status_code == 404


def test_status_has_required_fields(client):
    jid = _make_job(client, "Build a blog with posts and comments.")
    d = client.get(f"/status/{jid}").json()
    for field in ("job_id", "status", "current_agent", "progress_pct", "logs"):
        assert field in d, f"Missing field: {field}"
    assert d["progress"] == d["progress_pct"]
    assert d["tests_total"] == d["test_total"]


def test_read_project_file_returns_json_content(client):
    import os

    jid = _make_job(client)
    path = Path(os.environ["GENERATED_PROJECTS_DIR"]) / jid / "main.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("print('ok')\n", encoding="utf-8")
    try:
        response = client.get(f"/read-project-file/{jid}/main.py")
        assert response.status_code == 200
        assert response.json() == {"content": "print('ok')\n"}
    finally:
        shutil.rmtree(path.parent, ignore_errors=True)


# ── Cancel ────────────────────────────────────────────────────────────────────


def test_cancel_queued_job(client):
    jid = _make_job(client)
    r = client.post(f"/cancel/{jid}")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"


def test_cancel_nonexistent(client):
    assert client.post("/cancel/00000000-0000-0000-0000-000000000000").status_code == 404


def test_cancel_already_complete(client):
    jid = _make_job(client)
    update_job_status(jid, "complete", progress_pct=100)
    r = client.post(f"/cancel/{jid}")
    assert r.status_code == 400


# ── Files endpoint ────────────────────────────────────────────────────────────


def test_files_nonexistent_job(client):
    assert client.get("/files/00000000-0000-0000-0000-000000000000").status_code == 404


def test_files_zipped_job(client, tmp_path):
    # Simulate a completed (zipped) job: dir gone, only zip remains
    jid = _make_job(client)
    r = client.get(f"/files/{jid}")
    assert r.status_code == 200
    d = r.json()
    assert "files" in d
    assert "zipped" in d


def test_files_live_job(client, tmp_path):
    # Simulate live job dir with some files
    import os

    base = Path(os.environ["GENERATED_PROJECTS_DIR"])
    jid = _make_job(client)
    job_dir = base / jid
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "backend").mkdir(exist_ok=True)
    (job_dir / "backend" / "main.py").write_text("# main")
    (job_dir / "requirements.txt").write_text("fastapi\n")

    r = client.get(f"/files/{jid}")
    assert r.status_code == 200
    files = r.json()["files"]
    assert any("main.py" in f for f in files)
    shutil.rmtree(job_dir, ignore_errors=True)


# ── Validate endpoint ─────────────────────────────────────────────────────────


def test_validate_nonexistent_job(client):
    assert client.get("/validate/00000000-0000-0000-0000-000000000000").status_code == 404


def test_validate_with_valid_python(client, tmp_path):
    import os

    base = Path(os.environ["GENERATED_PROJECTS_DIR"])
    jid = _make_job(client)
    job_dir = base / jid
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "backend").mkdir(exist_ok=True)
    (job_dir / "backend" / "main.py").write_text("def hello(): return 'world'\n")

    r = client.get(f"/validate/{jid}")
    assert r.status_code == 200
    d = r.json()
    assert d["syntax_ok"] is True
    shutil.rmtree(job_dir, ignore_errors=True)


def test_validate_with_invalid_python(client, tmp_path):
    import os

    base = Path(os.environ["GENERATED_PROJECTS_DIR"])
    jid = _make_job(client)
    job_dir = base / jid
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "backend").mkdir(exist_ok=True)
    (job_dir / "backend" / "main.py").write_text("def broken(:\n    pass\n")

    r = client.get(f"/validate/{jid}")
    assert r.status_code == 200
    d = r.json()
    assert d["syntax_ok"] is False
    shutil.rmtree(job_dir, ignore_errors=True)


# ── Regenerate file ───────────────────────────────────────────────────────────


def test_regenerate_nonexistent_job(client):
    r = client.post(
        "/regenerate-file",
        json={
            "job_id": "00000000-0000-0000-0000-000000000000",
            "file_path": "backend/main.py",
        },
    )
    assert r.status_code == 404


def test_regenerate_running_job_rejected(client):
    jid = _make_job(client)
    update_job_status(jid, "running", current_agent="CodeAgent", progress_pct=40)
    r = client.post("/regenerate-file", json={"job_id": jid, "file_path": "backend/main.py"})
    assert r.status_code == 400


def test_regenerate_file_success(client, tmp_path):
    import os

    base = Path(os.environ["GENERATED_PROJECTS_DIR"])
    jid = _make_job(client)
    update_job_status(jid, "complete", progress_pct=100)
    job_dir = base / jid
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "backend").mkdir(exist_ok=True)
    (job_dir / "backend" / "main.py").write_text("# old content\n")

    new_code = (
        "from fastapi import FastAPI\napp = FastAPI()\n\n@app.get('/health')\ndef health(): return {'status': 'ok'}\n"
    )
    with patch("backend.routes.pipeline_routes.call_model", return_value=new_code):
        r = client.post(
            "/regenerate-file",
            json={
                "job_id": jid,
                "file_path": "backend/main.py",
                "correction_note": "Add health endpoint",
                "model": "local",
            },
        )
    assert r.status_code == 200
    d = r.json()
    assert d["syntax_ok"] is True
    shutil.rmtree(job_dir, ignore_errors=True)


# ── Jobs list ─────────────────────────────────────────────────────────────────


def test_list_jobs(client):
    _make_job(client)
    r = client.get("/jobs")
    assert r.status_code == 200
    assert isinstance(r.json()["jobs"], list)
    assert len(r.json()["jobs"]) >= 1


# ── ChromaDB ──────────────────────────────────────────────────────────────────


def test_chroma_job_lifecycle():
    jid = "chroma-v4-001"
    create_job(jid)
    job = get_job(jid)
    assert job is not None
    assert job["status"] == "queued"

    update_job_status(jid, "running", current_agent="CodeAgent", progress_pct=40)
    job2 = get_job(jid)
    assert job2["status"] == "running"
    assert int(job2["progress_pct"]) == 40

    update_job_status(jid, "complete", progress_pct=100)
    assert get_job(jid)["status"] == "complete"


def test_chroma_cancelled_status():
    jid = "chroma-v4-cancel"
    create_job(jid)
    update_job_status(jid, "cancelled", error_message="Cancelled by user.")
    job = get_job(jid)
    assert job["status"] == "cancelled"
    assert "Cancelled" in job["error_message"]


def test_chroma_logs():
    jid = "chroma-v4-logs"
    create_job(jid)
    log_to_db(jid, "TestAgent", "Info message", "INFO")
    log_to_db(jid, "TestAgent", "Warning message", "WARNING")
    log_to_db(jid, "TestAgent", "Error message", "ERROR")
    logs = get_logs(jid)
    assert len(logs) == 3
    assert {l["log_level"] for l in logs} == {"INFO", "WARNING", "ERROR"}


def test_chroma_requirements():
    jid = "chroma-v4-req"
    create_job(jid)
    data = {"project_name": "Test", "features": ["login", "CRUD"], "complexity": "simple"}
    save_requirements(jid, data)
    fetched = get_requirements(jid)
    assert fetched["project_name"] == "Test"
    assert "login" in fetched["features"]


def test_chroma_blueprint():
    jid = "chroma-v4-bp"
    create_job(jid)
    data = {"folders": ["backend", "frontend"], "routes": [], "db_tables": []}
    save_blueprint(jid, data)
    fetched = get_blueprint(jid)
    assert "backend" in fetched["folders"]


# ── RequirementAgent ──────────────────────────────────────────────────────────


def test_req_agent_parses():
    mock_resp = json.dumps(
        {
            "project_name": "Task",
            "project_type": "task_manager",
            "features": ["create task", "list tasks", "delete task"],
            "modules": ["tasks"],
            "complexity": "simple",
            "auth_required": False,
            "db_entities": ["Task"],
        }
    )
    with patch("agents.requirement_agent.call_model", return_value=mock_resp):
        from agents import requirement_agent

        r = requirement_agent.run(
            "Build a task manager with CRUD and database.",
            "Task",
            "req-v4-001",
            model="local",
            stack={"backend": "fastapi", "frontend": "streamlit", "db": "sqlite"},
        )
    assert r["project_type"] == "task_manager"
    assert len(r["features"]) >= 3
    assert "stack" in r


def test_req_agent_stack_attached():
    mock_resp = json.dumps(
        {
            "project_name": "Inv",
            "project_type": "inventory_system",
            "features": ["list products"],
            "modules": ["products"],
            "complexity": "simple",
            "auth_required": False,
            "db_entities": ["Product"],
        }
    )
    with patch("agents.requirement_agent.call_model", return_value=mock_resp):
        from agents import requirement_agent

        r = requirement_agent.run(
            "Build an inventory system.",
            "Inv",
            "req-v4-002",
            model="local",
            stack={"backend": "fastapi", "frontend": "streamlit", "db": "postgresql"},
        )
    assert r["stack"]["db"] == "postgresql"


def test_req_agent_empty_raises():
    from agents import requirement_agent

    with pytest.raises(ValueError, match="empty"):
        requirement_agent.run("", "T", "req-v4-003")


def test_req_agent_unsupported_raises():
    from agents import requirement_agent

    with pytest.raises(ValueError, match="Unsupported"):
        requirement_agent.run("Build a deep learning neural network.", "AI", "req-v4-004")


def test_req_agent_too_long_raises():
    from agents import requirement_agent

    with pytest.raises(ValueError, match="500"):
        requirement_agent.run("Build a task manager. " * 30, "T", "req-v4-005")


def test_req_agent_clarify_clear():
    with patch("agents.requirement_agent.call_model", return_value="CLEAR"):
        from agents.requirement_agent import clarify

        result = clarify("Build a task manager with CRUD.", model="local")
    assert result is None


def test_req_agent_clarify_question():
    with patch("agents.requirement_agent.call_model", return_value="Do you need user authentication?"):
        from agents.requirement_agent import clarify

        result = clarify("Build a system.", model="local")
    assert result is not None
    assert result.endswith("?")


# ── TestGenAgent ──────────────────────────────────────────────────────────────


def test_testgen_agent_writes_file(tmp_path):
    import os

    os.environ["GENERATED_PROJECTS_DIR"] = str(tmp_path)
    import importlib

    import services.file_service as fs

    importlib.reload(fs)

    jid = "testgen-v4-001"
    job_dir = tmp_path / jid
    job_dir.mkdir()

    req = {"project_name": "App", "features": ["CRUD"]}
    bp = {
        "routes": [
            {"method": "GET", "path": "/items", "description": "List"},
            {"method": "POST", "path": "/items", "description": "Create"},
            {"method": "GET", "path": "/health", "description": "Health"},
        ],
        "db_tables": [{"name": "items"}],
    }
    mock_test = (
        "from fastapi.testclient import TestClient\n"
        "from backend.main import app\n"
        "import pytest\n\n"
        "@pytest.fixture(scope='module')\n"
        "def client():\n"
        "    with TestClient(app) as c:\n"
        "        yield c\n\n"
        "def test_health(client):\n"
        "    r = client.get('/health')\n"
        "    assert r.status_code == 200\n"
    )
    with patch("agents.test_gen_agent.call_model", return_value=mock_test):
        from agents import test_gen_agent

        files = test_gen_agent.run(req, bp, [], jid, model="local")

    assert any("test_app.py" in f for f in files)
    assert (job_dir / "tests" / "test_app.py").exists()
    os.environ["GENERATED_PROJECTS_DIR"] = "./test_generated_projects_v4"


def test_testgen_agent_fallback_writes_minimal_tests(tmp_path):
    import os

    os.environ["GENERATED_PROJECTS_DIR"] = str(tmp_path)
    import importlib

    import services.file_service as fs

    importlib.reload(fs)

    jid = "testgen-v4-002"
    (tmp_path / jid).mkdir()

    req = {"project_name": "App", "features": []}
    bp = {"routes": [{"method": "GET", "path": "/health", "description": "Health"}], "db_tables": []}

    with patch("agents.test_gen_agent.call_model", return_value="x"):  # too short → fallback
        from agents import test_gen_agent

        files = test_gen_agent.run(req, bp, [], jid, model="local")

    assert len(files) >= 2  # __init__.py + test_app.py written as fallback
    assert any("test_app.py" in f for f in files)
    os.environ["GENERATED_PROJECTS_DIR"] = "./test_generated_projects_v4"


# ── CleanupService ────────────────────────────────────────────────────────────


def test_cleanup_deletes_old_zips(tmp_path):
    import os

    os.environ["GENERATED_PROJECTS_DIR"] = str(tmp_path)
    import importlib

    import services.cleanup_service as cs

    importlib.reload(cs)

    # Create two ZIPs: one old (mtime in past), one recent
    old_zip = tmp_path / "old-job.zip"
    new_zip = tmp_path / "new-job.zip"
    old_zip.write_text("old")
    new_zip.write_text("new")

    # Set old_zip mtime to 2 hours ago (retention = 1h)
    old_time = time.time() - 7200
    os.utime(old_zip, (old_time, old_time))

    deleted = cs.run_once()
    assert deleted == 1
    assert not old_zip.exists()
    assert new_zip.exists()

    os.environ["GENERATED_PROJECTS_DIR"] = "./test_generated_projects_v4"


def test_cleanup_skips_fresh_zips(tmp_path):
    import os

    os.environ["GENERATED_PROJECTS_DIR"] = str(tmp_path)
    import importlib

    import services.cleanup_service as cs

    importlib.reload(cs)

    fresh = tmp_path / "fresh.zip"
    fresh.write_text("fresh")

    deleted = cs.run_once()
    assert deleted == 0
    assert fresh.exists()

    os.environ["GENERATED_PROJECTS_DIR"] = "./test_generated_projects_v4"


# ── ZIP Service ───────────────────────────────────────────────────────────────


def test_zip_creates_valid(tmp_path):
    import importlib
    import zipfile

    os.environ["GENERATED_PROJECTS_DIR"] = str(tmp_path)
    import services.zip_service as zm

    importlib.reload(zm)

    jid = "zip-v4-001"
    d = tmp_path / jid
    d.mkdir()
    (d / "main.py").write_text("print('hello')")
    (d / "README.md").write_text("# Test")

    zp = zm.create_zip(jid)
    assert zp.exists()
    assert zipfile.is_zipfile(str(zp))
    os.environ["GENERATED_PROJECTS_DIR"] = "./test_generated_projects_v4"


def test_zip_missing_raises(tmp_path):
    import importlib

    os.environ["GENERATED_PROJECTS_DIR"] = str(tmp_path)
    import services.zip_service as zm

    importlib.reload(zm)

    with pytest.raises(FileNotFoundError):
        zm.create_zip("nonexistent-job-xyz")
    os.environ["GENERATED_PROJECTS_DIR"] = "./test_generated_projects_v4"


# ── LLM Service ───────────────────────────────────────────────────────────────


def test_resolve_model_presets():
    from services.llm_service import resolve_model

    assert resolve_model("local") == os.getenv("MODEL_LOCAL", "gemma4:12b")
    assert resolve_model("cloud") == os.getenv("CLOUD_MODEL", "gemma-4-31b-it")
    assert resolve_model("unknown") == "unknown"


def test_clean_code_response_strips_fences():
    from services.llm_service import clean_code_response

    assert clean_code_response("```python\nprint('hi')\n```") == "print('hi')"


def test_clean_code_response_no_fences():
    from services.llm_service import clean_code_response

    assert clean_code_response("print('hello')") == "print('hello')"


def test_llm_retry_on_timeout():
    """LLM call retries up to MAX_RETRIES times on APITimeoutError."""
    from openai import APITimeoutError

    from services import llm_service

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = APITimeoutError(request=MagicMock())

    with patch.object(llm_service, "_client", return_value=mock_client):
        with pytest.raises(RuntimeError, match="failed after"):
            llm_service.call_model("test", model="local")


def test_singleton_client_is_same_object():
    from services.llm_service import _client

    c1 = _client()
    c2 = _client()
    assert c1 is c2


# ── Multi-Provider ──────────────────────────────────────────────────────────


def test_get_available_providers():
    from services.llm_service import get_available_providers

    providers = get_available_providers()
    names = {p["name"] for p in providers}
    assert "local" in names
    assert "cloud" in names


def test_health_includes_providers(client):
    d = client.get("/health").json()
    assert "providers" in d
    assert isinstance(d["providers"], list)
    names = {p["name"] for p in d["providers"]}
    assert "local" in names


def test_providers_endpoint(client):
    r = client.get("/providers")
    assert r.status_code == 200
    providers = r.json()["providers"]
    assert isinstance(providers, list)
    assert len(providers) >= 2


# ── Workspace CRUD ──────────────────────────────────────────────────────────


def test_workspace_create_file(client, tmp_path):
    import os

    base = Path(os.environ["GENERATED_PROJECTS_DIR"])
    jid = "wksp-test-001"
    (base / jid).mkdir(parents=True, exist_ok=True)
    r = client.post(f"/workspace/{jid}/files/newfile.py", json={"content": "x = 1\n"})
    assert r.status_code == 200
    assert r.json()["action"] == "created"
    assert (base / jid / "newfile.py").exists()
    shutil.rmtree(base / jid, ignore_errors=True)


def test_workspace_update_file(client, tmp_path):
    import os

    base = Path(os.environ["GENERATED_PROJECTS_DIR"])
    jid = "wksp-test-002"
    (base / jid).mkdir(parents=True, exist_ok=True)
    (base / jid / "main.py").write_text("old content")
    r = client.put(f"/workspace/{jid}/files/main.py", json={"content": "new content"})
    assert r.status_code == 200
    assert r.json()["action"] == "updated"
    assert (base / jid / "main.py").read_text() == "new content"
    shutil.rmtree(base / jid, ignore_errors=True)


def test_workspace_delete_file(client, tmp_path):
    import os

    base = Path(os.environ["GENERATED_PROJECTS_DIR"])
    jid = "wksp-test-003"
    (base / jid).mkdir(parents=True, exist_ok=True)
    (base / jid / "delete_me.py").write_text("to delete")
    r = client.delete(f"/workspace/{jid}/files/delete_me.py")
    assert r.status_code == 200
    assert r.json()["action"] == "deleted"
    assert not (base / jid / "delete_me.py").exists()
    shutil.rmtree(base / jid, ignore_errors=True)


def test_workspace_path_traversal_denied(client):
    import os
    import urllib.parse

    from services.file_service import BASE_DIR as BD

    base_path = os.environ["GENERATED_PROJECTS_DIR"]
    jid = "wksp-test-004"
    (Path(base_path) / jid).mkdir(parents=True, exist_ok=True)
    assert (Path(base_path) / jid).exists(), f"Dir should exist: {Path(base_path) / jid}"
    assert BD.exists(), f"BASE_DIR should exist: {BD}"
    trav_path = urllib.parse.quote("../../etc/passwd", safe="")
    r = client.post(f"/workspace/{jid}/files/{trav_path}", json={"content": "hack"})
    assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.json()}"
    shutil.rmtree(Path(base_path) / jid, ignore_errors=True)


# ── Memory / Insights ───────────────────────────────────────────────────────


def test_coding_preferences():
    from database.memory_store import get_coding_preferences, set_coding_preference

    set_coding_preference("framework:fastapi", "True", source="test", confidence=0.9)
    prefs = get_coding_preferences()
    assert any(p["pref_key"] == "framework:fastapi" for p in prefs)


def test_project_insights():
    from database.memory_store import get_project_insights, save_project_insight

    save_project_insight("test-job", "successful_generation", "All tests passed")
    insights = get_project_insights(insight_type="successful_generation")
    assert len(insights) >= 1
    assert insights[0]["summary"] == "All tests passed"


# ── Auto-Fix Service ────────────────────────────────────────────────────────


def test_autofix_no_project(client):
    r = client.post("/autofix/00000000-0000-0000-0000-000000000000", json={"model": "local"})
    assert r.status_code == 404


def test_autofix_no_project_dir(client, tmp_path):
    # Job exists in DB but no dir — autofix returns error
    from database.chroma_db import create_job

    jid = "autofix-test-001"
    create_job(jid)
    with patch("services.autofix_service.BASE_DIR", tmp_path):
        from services.autofix_service import run_autofix

        result = run_autofix(jid, model="local", max_attempts=1)
        assert result["status"] == "error"


# ── Sandbox Service ─────────────────────────────────────────────────────────


def test_sandbox_status(client):
    r = client.get("/sandbox/status")
    assert r.status_code == 200
    assert "available" in r.json()


def test_sandbox_run_subprocess():
    from services.sandbox_service import _run_subprocess

    result = _run_subprocess("print('hello')", None, 10)
    assert "hello" in result.get("stdout", "")


# ── Deployment Service ──────────────────────────────────────────────────────


def test_deploy_unregistered_job(client):
    r = client.post("/deploy/00000000-0000-0000-0000-000000000000", json={"target": "docker"})
    assert r.status_code == 404


def test_deploy_generates_docker(tmp_path):
    from unittest.mock import patch

    from services.deployment_service import deploy_project

    jid = "deploy-test-001"
    job_dir = tmp_path / jid
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "main.py").write_text("print('hello')")
    (job_dir / "requirements.txt").write_text("fastapi\n")

    with patch("services.deployment_service.BASE_DIR", tmp_path):
        result = deploy_project(jid, target="docker")
    assert result["status"] == "generated"
    assert "Dockerfile" in result["files"]


# ── Metrics ─────────────────────────────────────────────────────────────────


def test_metrics_endpoint(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    d = r.json()
    assert "total_tokens" in d
    assert "analytics" in d


# ── Fix patterns ────────────────────────────────────────────────────────────


def test_fix_patterns():
    from database.memory_store import get_fix_patterns, record_fix_pattern

    record_fix_pattern("import_error", "ModuleNotFoundError", "tests/*.py", "Add missing import")
    patterns = get_fix_patterns()
    assert len(patterns) >= 1
    assert patterns[0]["pattern_type"] == "import_error"


# ── Reusable components ─────────────────────────────────────────────────────


def test_reusable_components():
    from database.memory_store import get_reusable_components, save_reusable_component

    save_reusable_component("FastAPICRUD", "route", "def create(): pass", "CRUD route template", "fastapi,crud")
    comps = get_reusable_components(component_type="route")
    assert len(comps) >= 1
    assert comps[0]["name"] == "FastAPICRUD"


# ── Memory service ──────────────────────────────────────────────────────────


def test_memory_context():
    from services.memory_service import get_context_for_prompt

    ctx = get_context_for_prompt("build an app", job_id="test-job")
    assert isinstance(ctx, dict)


def test_learn_from_project():
    from services.memory_service import learn_from_project

    req = {"project_name": "Test", "features": ["login"]}
    bp = {"tech_stack": {"backend": "fastapi", "frontend": "react", "db": "postgresql"}, "file_count": 5}
    tr = {"passed": True, "collected": 3, "failures": []}
    result = learn_from_project("test-learn-001", req, bp, tr)
    assert result["learned"] is True


# ── Error classification ────────────────────────────────────────────────────


def test_classify_errors():
    from services.memory_service import _classify_error

    assert _classify_error("ImportError: No module named x") == "import_error"
    assert _classify_error("SyntaxError: invalid syntax") == "syntax_error"
    assert _classify_error("NameError: x not defined") == "name_error"
    assert _classify_error("TypeError: unsupported operand") == "type_error"
    assert _classify_error("AssertionError: expected 200") == "assertion_error"
    assert _classify_error("some random error") == "unknown"
