"""Deployment Orchestrator routes — extracted from main.py."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/deployment", tags=["Deployment"])


class DeployOrchestrateRequest(BaseModel):
    job_id: str
    project_dir: str
    target: str = "docker"
    health_check_url: str | None = None
    run_browser_validation: bool = False


@router.post("/start")
async def deployment_start(req: DeployOrchestrateRequest):
    from services.deployment_orchestrator import get_deployment_orchestrator

    orch = get_deployment_orchestrator()
    session = orch.deploy(req.job_id, req.project_dir, req.target, req.health_check_url, req.run_browser_validation)
    return {"session_id": session.id, "status": session.status.value, "target": session.target.value}


@router.get("/{session_id}")
async def deployment_status(session_id: str):
    from services.deployment_orchestrator import get_deployment_orchestrator

    orch = get_deployment_orchestrator()
    session = orch.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Deployment session not found")
    return session.to_dict()


@router.post("/rollback/{session_id}")
async def deployment_rollback(session_id: str):
    from services.deployment_orchestrator import get_deployment_orchestrator

    orch = get_deployment_orchestrator()
    ok = orch.rollback(session_id)
    return {"session_id": session_id, "rolled_back": ok}


@router.get("")
async def deployment_list(job_id: str | None = None):
    from services.deployment_orchestrator import get_deployment_orchestrator

    orch = get_deployment_orchestrator()
    return {"sessions": orch.list_sessions(job_id=job_id)}
