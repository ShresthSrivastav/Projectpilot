"""
TestGen Agent — generates a pytest test suite from the blueprint.

New in v4. Inserted between CodeAgent and DebugAgent.
Reads the blueprint routes + db_tables and asks the LLM to write
tests/test_app.py. DebugAgent already calls run_pytest() — this
agent feeds it the test files it needs.
"""
import logging
import time
from typing import Any

from database.chroma_db import log_to_db
from services.file_service import write_file
from services.llm_service import call_model, clean_code_response

logger = logging.getLogger(__name__)

_SYS = (
    "You are a Python testing expert. "
    "Write a complete pytest test file ONLY — no markdown fences, no explanations. "
    "IMPORTANT: Do NOT import from the generated project (no 'from backend.main import app'). "
    "The project module won't be installed. Instead define an inline FastAPI test app "
    "that mocks all endpoints using the route definitions below. "
    "Use FastAPI TestClient with a self-contained app defined IN this test file. "
    "Mock database calls with pytest fixtures using unittest.mock. "
    "Every test function must start with test_. "
    "Include at least one test per route listed."
)


def run(
    requirements: dict[str, Any],
    blueprint: dict[str, Any],
    generated_files: list[str],
    job_id: str,
    model: str = None,
) -> list[str]:
    log_to_db(job_id, "TestGenAgent", "Generating validation test suite…")

    routes = blueprint.get("routes", [])
    tables = blueprint.get("db_tables", [])
    features = requirements.get("features", [])
    project_name = requirements.get("project_name", "App")

    prompt = f"""Generate a complete pytest test file (tests/test_app.py) for: {project_name}
Features: {', '.join(features)}
Routes:
{chr(10).join(f"  {r.get('method')} {r.get('path')} — {r.get('description', '')}" for r in routes)}
DB Tables: {', '.join(t.get('name', '') for t in tables)}

CRITICAL REQUIREMENT:
- Do NOT import from the generated project (no 'from backend.main import app' or 'from backend import *')
- Instead, define a simple FastAPI test app inline OR use unittest.mock to mock the API layer
- Use FastAPI TestClient with a self-contained app defined IN this test file
- Test each route by sending requests to your inline app
- All tests must be independent (no shared state)
- Include at least one test per route listed above
- Mock database calls with pytest fixtures using unittest.mock
- Every test function must start with test_"""

    new_files: list[str] = []

    t0 = time.monotonic()
    try:
        content = clean_code_response(
            call_model(prompt, system_prompt=_SYS, model=model or "local",
                       job_id=job_id, agent="TestGenAgent")
        )
        elapsed = int((time.monotonic() - t0) * 1000)
        if len(content) < 100:
            raise ValueError(f"Generated test file too short ({len(content)} chars) after {elapsed}ms")

        write_file(job_id, "tests/__init__.py", "")
        write_file(job_id, "tests/test_app.py", content)
        new_files = ["tests/__init__.py", "tests/test_app.py"]
        log_to_db(job_id, "TestGenAgent", f"tests/test_app.py written ({len(content)} chars, {elapsed}ms).")

    except Exception as exc:
        elapsed = int((time.monotonic() - t0) * 1000)
        log_to_db(job_id, "TestGenAgent",
                  f"Test generation FAILED after {elapsed}ms: {exc}", "CRITICAL")

    return new_files


def _minimal_smoke_test(routes: list[dict]) -> str:
    return ""
