from fastapi import APIRouter, Request

from database.memory_store import get_analytics_summary, get_project_analytics

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/overview")
async def analytics_overview(request: Request = None):
    ws_id = getattr(request.state, "workspace_id", "") if request else ""
    return get_analytics_summary(workspace_id=ws_id)


@router.get("/projects")
async def analytics_projects(request: Request = None):
    ws_id = getattr(request.state, "workspace_id", "") if request else ""
    return {"projects": get_project_analytics(workspace_id=ws_id, limit=50)}


@router.get("/project/{job_id}")
async def analytics_project(job_id: str):
    from services.analytics_service import get_project_stats

    return get_project_stats(job_id)
