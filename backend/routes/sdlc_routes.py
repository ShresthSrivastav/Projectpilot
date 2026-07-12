"""SDLC Pipeline routes — extracted from main.py."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/sdlc", tags=["SDLC Pipeline"])


class SDLCStartRequest(BaseModel):
    job_id: str
    prompt: str
    model: str = "cloud"


@router.post("/start")
async def sdlc_start(req: SDLCStartRequest):
    from services.sdlc_pipeline import get_sdlc_engine

    engine = get_sdlc_engine()
    pipeline = engine.run_pipeline(req.job_id, req.prompt, req.model)
    return {"pipeline_id": pipeline.id, "job_id": req.job_id, "stage": pipeline.stage.value, "status": pipeline.status}


@router.get("/{pipeline_id}")
async def sdlc_status(pipeline_id: str):
    from services.sdlc_pipeline import get_sdlc_engine

    engine = get_sdlc_engine()
    pipeline = engine.get_pipeline(pipeline_id)
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return pipeline.to_dict()


@router.post("/resume/{pipeline_id}")
async def sdlc_resume(pipeline_id: str):
    from services.sdlc_pipeline import get_sdlc_engine

    engine = get_sdlc_engine()
    pipeline = engine.resume(pipeline_id)
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return {"pipeline_id": pipeline.id, "stage": pipeline.stage.value, "status": pipeline.status}


@router.get("")
async def sdlc_list(job_id: str | None = None):
    from services.sdlc_pipeline import get_sdlc_engine

    engine = get_sdlc_engine()
    return {"pipelines": engine.list_pipelines(job_id=job_id)}
