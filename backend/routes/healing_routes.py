"""Self-Healing routes — extracted from main.py."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/healing", tags=["Self-Healing"])


class HealRequest(BaseModel):
    job_id: str
    runtime_id: str = ""
    log_text: str
    project_dir: str | None = None
    max_retries: int = 3
    confidence_threshold: float = 0.6


@router.post("/start")
async def healing_start(req: HealRequest):
    from services.self_healing_service import get_healing_engine

    engine = get_healing_engine()
    session = engine.detect_and_heal(
        req.job_id,
        req.runtime_id,
        req.log_text,
        project_dir=req.project_dir,
        max_retries=req.max_retries,
        confidence_threshold=req.confidence_threshold,
    )
    return {"session_id": session.id, "status": session.status.value}


@router.get("/{session_id}")
async def healing_status(session_id: str):
    from services.self_healing_service import get_healing_engine

    engine = get_healing_engine()
    session = engine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Healing session not found")
    return session.to_dict()


@router.post("/rollback/{session_id}")
async def healing_rollback(session_id: str):
    from services.self_healing_service import get_healing_engine

    engine = get_healing_engine()
    ok = engine.rollback(session_id)
    return {"session_id": session_id, "rolled_back": ok}


@router.get("")
async def healing_list(job_id: str | None = None):
    from services.self_healing_service import get_healing_engine

    engine = get_healing_engine()
    return {"sessions": engine.list_sessions(job_id=job_id)}
