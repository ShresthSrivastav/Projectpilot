"""Autonomous iteration routes — extracted from main.py."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/autonomous", tags=["Autonomous"])


class AutonomousStartRequest(BaseModel):
    job_id: str
    max_iterations: int = 10
    quality_threshold: float = 0.85
    model: str = "cloud"


@router.post("/start")
async def autonomous_start(req: AutonomousStartRequest):
    from services.autonomous_service import AutonomousConfig, get_autonomous_engine

    engine = get_autonomous_engine()
    config = AutonomousConfig(
        max_iterations=req.max_iterations or 10,
        quality_threshold=req.quality_threshold or 0.85,
        model=req.model or "cloud",
    )
    session = engine.start_session(req.job_id, config=config)
    return {"session_id": session.id, "job_id": req.job_id, "status": session.status}


@router.get("/status/{session_id}")
async def autonomous_status(session_id: str):
    from services.autonomous_service import get_autonomous_engine

    engine = get_autonomous_engine()
    session = engine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.to_dict()


@router.get("/history/{session_id}")
async def autonomous_history(session_id: str):
    from services.autonomous_service import get_autonomous_engine

    engine = get_autonomous_engine()
    return engine.get_iteration_history(session_id)


@router.get("/sessions")
async def autonomous_list():
    from services.autonomous_service import get_autonomous_engine

    engine = get_autonomous_engine()
    return {"sessions": engine.list_sessions()}


@router.get("/metrics/{job_id}")
async def autonomous_metrics(job_id: str):
    from database.memory_store import get_cost_summary, get_iteration_history

    cost = get_cost_summary(job_id)
    history = get_iteration_history(job_id)
    return {"job_id": job_id, "cost": cost, "iteration_history": history}
