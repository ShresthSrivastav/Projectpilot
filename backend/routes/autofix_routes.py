"""Auto-Fix, Sandbox, Memory, Deploy, Logs, Cost, Visualizer routes — extracted from main.py."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database.chroma_db import get_job

router = APIRouter(tags=["Utilities"])


# ── Auto-Fix ─────────────────────────────────────────────────────────────


class AutoFixRequest(BaseModel):
    model: str | None = "local"
    max_attempts: int = 5


@router.post("/autofix/{job_id}")
async def autofix_project(job_id: str, req: AutoFixRequest):
    from services.autofix_service import run_autofix

    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    result = run_autofix(job_id, model=req.model or "local", max_attempts=req.max_attempts)
    return result


# ── Sandbox ──────────────────────────────────────────────────────────────


class SandboxRunRequest(BaseModel):
    code: str
    requirements: list[str] | None = None
    timeout: int = 60


@router.post("/sandbox/run")
async def sandbox_run(req: SandboxRunRequest):
    from services.sandbox_service import run_python

    result = run_python(req.code, requirements=req.requirements, timeout=req.timeout)
    return result


@router.get("/sandbox/status")
async def sandbox_status():
    from services.sandbox_service import is_available

    return {"available": is_available()}


# ── Memory ───────────────────────────────────────────────────────────────


@router.get("/memory/context/{job_id}")
async def memory_context(job_id: str):
    from services.memory_service import get_context_for_prompt

    ctx = get_context_for_prompt("", job_id=job_id)
    return ctx


@router.get("/memory/insights")
async def memory_insights(insight_type: str | None = None, limit: int = 50):
    from database.memory_store import get_project_insights

    insights = get_project_insights(insight_type=insight_type, limit=limit)
    return {"insights": insights}


# ── Deploy ───────────────────────────────────────────────────────────────


class DeployRequest(BaseModel):
    target: str = "docker"
    model: str | None = "local"


@router.post("/deploy/{job_id}")
async def deploy_project(job_id: str, req: DeployRequest):
    from services.deployment_service import deploy_project

    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    result = deploy_project(job_id, target=req.target, model=req.model or "local")
    return result


# ── Logs Analyzer ────────────────────────────────────────────────────────


class LogAnalyzeRequest(BaseModel):
    log_text: str
    use_llm: bool = False


@router.post("/logs/analyze")
async def logs_analyze(req: LogAnalyzeRequest):
    from services.log_analyzer import get_log_analyzer

    analyzer = get_log_analyzer()
    result = analyzer.analyze(req.log_text, use_llm=req.use_llm)
    return result.to_dict()


@router.get("/logs/statistics")
async def logs_statistics():
    from services.log_analyzer import get_log_analyzer

    analyzer = get_log_analyzer()
    return analyzer.get_statistics()


# ── Cost Tracking ────────────────────────────────────────────────────────


@router.get("/cost/total")
async def cost_total():
    from database.memory_store import get_cost_summary

    return get_cost_summary()


@router.get("/cost/{job_id}")
async def cost_by_job(job_id: str):
    from database.memory_store import get_cost_summary

    return get_cost_summary(job_id)


# ── Visualizer ───────────────────────────────────────────────────────────


@router.get("/visualizer/graphs")
async def visualizer_graphs():
    from database.memory_store import list_graph_sessions

    return {"graphs": list_graph_sessions(limit=50)}


@router.get("/visualizer/debates")
async def visualizer_debates():
    from services.debate_system import get_debate_system

    ds = get_debate_system()
    return {"debates": ds.list_sessions()}


@router.get("/visualizer/autonomous")
async def visualizer_autonomous():
    from services.autonomous_service import get_autonomous_engine

    engine = get_autonomous_engine()
    return {"sessions": engine.list_sessions()}


@router.get("/visualizer/progress/{job_id}")
async def visualizer_progress(job_id: str):
    from database.chroma_db import get_job
    from database.memory_store import get_cost_summary, get_iteration_history

    job = get_job(job_id)
    history = get_iteration_history(job_id)
    cost = get_cost_summary(job_id)
    return {
        "job_id": job_id,
        "project_name": (job or {}).get("project_name", ""),
        "status": (job or {}).get("status", ""),
        "iteration_history": history,
        "cost": cost,
    }


@router.get("/visualizer/timeline/{job_id}")
async def visualizer_timeline(job_id: str):
    from services.dashboard_service import get_timeline

    return {"timeline": get_timeline(limit=200, job_id=job_id)}