"""Global test configuration — ensures clean state between tests."""

import pytest


@pytest.fixture(autouse=True, scope="session")
def _clean_memory_store():
    """Clear memory store data at start of session to ensure clean initial state."""
    from database.memory_store import _get_conn

    try:
        conn = _get_conn()
        tables = [
            "evaluation_runs",
            "evaluation_reports",
            "regressions",
            "leaderboards",
            "version_history",
            "version_comparisons",
            "learning_feedback",
            "learning_feedback_patterns",
            "learning_feedback_recommendations",
            "campaigns",
            "campaign_runs",
            "scheduler_metadata",
        ]
        for table in tables:
            try:
                conn.execute(f"DELETE FROM {table}")
            except Exception:
                pass
        conn.commit()
    except Exception:
        pass
