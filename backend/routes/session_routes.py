"""Session Manager routes — extracted from main.py."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/sessions", tags=["Sessions"])


class SessionCreateRequest(BaseModel):
    job_id: str
    name: str = ""
    session_type: str = "pipeline"
    tasks: list[str] | None = None


@router.post("/create")
async def session_create(req: SessionCreateRequest):
    from services.session_manager import get_session_manager

    sm = get_session_manager()
    session = sm.create_session(req.job_id, name=req.name, session_type=req.session_type, tasks=req.tasks)
    return {"session_id": session.id, "status": session.status.value}


@router.get("/{session_id}")
async def session_status(session_id: str):
    from services.session_manager import get_session_manager

    sm = get_session_manager()
    session = sm.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.to_dict()


@router.post("/{session_id}/pause")
async def session_pause(session_id: str):
    from services.session_manager import get_session_manager

    sm = get_session_manager()
    session = sm.pause_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "status": session.status.value}


@router.post("/{session_id}/resume")
async def session_resume(session_id: str):
    from services.session_manager import get_session_manager

    sm = get_session_manager()
    session = sm.resume_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "status": session.status.value}


@router.post("/{session_id}/complete")
async def session_complete(session_id: str):
    from services.session_manager import get_session_manager

    sm = get_session_manager()
    session = sm.complete_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "status": session.status.value}


@router.get("")
async def session_list(job_id: str | None = None):
    from services.session_manager import get_session_manager

    sm = get_session_manager()
    return {"sessions": sm.list_sessions(job_id=job_id)}