"""Evaluation routes — extracted from main.py."""

from fastapi import APIRouter, Body
from pydantic import BaseModel

from database.memory_store import (
    mem_list_evaluation_runs,
    mem_list_evaluation_reports,
    mem_get_leaderboard,
    mem_get_leaderboard_categories,
    mem_get_version_comparisons,
    mem_list_regressions,
    mem_save_evaluation_run,
    mem_save_evaluation_report,
)

router = APIRouter(prefix="/evaluation", tags=["Evaluation"])


@router.post("/run")
def trigger_evaluation_run(data: dict = Body(...)):
    from services.evaluation_scheduler import get_evaluation_scheduler

    scheduler = get_evaluation_scheduler()
    trigger_type = data.get("trigger_type", "on_demand")
    result = scheduler.trigger_run(schedule=trigger_type, triggered_by="api")
    return {"success": True, "run": result.to_dict()}


@router.get("/history")
def list_evaluation_runs(
    limit: int = 50,
    trigger_type: str | None = None,
    status: str | None = None,
):
    runs = mem_list_evaluation_runs(limit=limit, trigger_type=trigger_type, status=status)
    return {"runs": runs}


@router.get("/reports")
def list_evaluation_reports(
    report_type: str | None = None,
    limit: int = 20,
):
    reports = mem_list_evaluation_reports(report_type=report_type, limit=limit)
    return {"reports": reports}


@router.get("/leaderboards")
def get_leaderboard(
    category: str | None = None,
    sort_by: str = "score",
    limit: int = 20,
):
    entries = mem_get_leaderboard(category=category, sort_by=sort_by, limit=limit)
    categories = mem_get_leaderboard_categories()
    return {"entries": entries, "categories": categories}


@router.get("/comparison")
def get_version_comparison(
    from_version: str | None = None,
    to_version: str | None = None,
    limit: int = 20,
):
    comparisons = mem_get_version_comparisons(from_version=from_version, to_version=to_version, limit=limit)
    return {"comparisons": comparisons}


@router.get("/regressions")
def list_regressions(
    category: str | None = None,
    severity: str | None = None,
    dismissed: bool | None = None,
    limit: int = 100,
):
    regressions = mem_list_regressions(category=category, severity=severity, dismissed=dismissed, limit=limit)
    return {"regressions": regressions}
