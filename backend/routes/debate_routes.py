"""Multi-Agent Debate routes — extracted from main.py."""

from fastapi import APIRouter, HTTPException
from pydantic import Field
from pydantic import BaseModel

router = APIRouter(prefix="/debate", tags=["Debate"])


class DebateRequest(BaseModel):
    topic: str = Field(..., description="Programming task or question to debate")
    context: str = ""
    job_id: str = ""
    solvers: list[str] | None = None
    arbiter_model: str = "cloud"
    quality_threshold: float = 0.7


class DebateQueryRequest(BaseModel):
    session_id: str


@router.post("/start")
async def debate_start(req: DebateRequest):
    from services.debate_system import ConsensusMethod, DebateConfig, get_debate_system

    ds = get_debate_system()
    config = DebateConfig(
        solvers=req.solvers or ["local", "cloud", "local", "cloud"],
        arbiter_model=req.arbiter_model or "cloud",
        quality_threshold=req.quality_threshold or 0.7,
        consensus_method=ConsensusMethod.WEIGHTED,
    )
    session = ds.start_debate(req.topic, config=config, context=req.context, job_id=req.job_id)
    return {"session_id": session.id, "status": session.status}


@router.get("/status/{session_id}")
async def debate_status(session_id: str):
    from services.debate_system import get_debate_system

    ds = get_debate_system()
    session = ds.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Debate session not found")
    return session.to_dict()


@router.get("/sessions")
async def debate_list():
    from services.debate_system import get_debate_system

    ds = get_debate_system()
    return {"sessions": ds.list_sessions()}


@router.get("/quality/{session_id}")
async def debate_quality(session_id: str):
    from services.debate_system import get_debate_system

    ds = get_debate_system()
    return ds.evaluate_quality(session_id)
