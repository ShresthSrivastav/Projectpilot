"""Runtime Orchestrator routes — extracted from main.py."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/runtime", tags=["Runtime"])


class RuntimeCreateRequest(BaseModel):
    job_id: str
    name: str = ""
    runtime_type: str = "subprocess"
    image: str = "python:3.11-slim"
    command: list[str] | None = None
    env_vars: dict[str, str] | None = None
    port_mappings: dict[str, int] | None = None
    memory_limit: str = "256m"
    cpu_limit: float = 0.5
    timeout: int = 300


class RuntimeActionRequest(BaseModel):
    session_id: str


@router.post("/create")
async def runtime_create(req: RuntimeCreateRequest):
    from services.runtime_orchestrator import ExecutionEnvironment, RuntimeType, get_orchestrator

    env = ExecutionEnvironment(
        runtime_type=RuntimeType(req.runtime_type.lower())
        if req.runtime_type in ("docker", "subprocess")
        else RuntimeType.SUBPROCESS,
        image=req.image,
        command=req.command or [],
        env_vars=req.env_vars or {},
        port_mappings={int(k): v for k, v in (req.port_mappings or {}).items()},
        memory_limit=req.memory_limit,
        cpu_limit=req.cpu_limit,
        timeout=req.timeout,
    )
    orch = get_orchestrator()
    session = orch.create_runtime(req.job_id, name=req.name, env=env)
    return {"session_id": session.id, "status": session.status.value}


@router.post("/start")
async def runtime_start(req: RuntimeActionRequest):
    from services.runtime_orchestrator import get_orchestrator

    orch = get_orchestrator()
    try:
        session = orch.start_runtime(req.session_id)
        return {"session_id": session.id, "status": session.status.value, "port": session.port, "pid": session.pid}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/stop")
async def runtime_stop(req: RuntimeActionRequest):
    from services.runtime_orchestrator import get_orchestrator

    orch = get_orchestrator()
    try:
        session = orch.stop_runtime(req.session_id)
        return {"session_id": session.id, "status": session.status.value}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/restart")
async def runtime_restart(req: RuntimeActionRequest):
    from services.runtime_orchestrator import get_orchestrator

    orch = get_orchestrator()
    try:
        session = orch.restart_runtime(req.session_id)
        return {"session_id": session.id, "status": session.status.value}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/destroy")
async def runtime_destroy(req: RuntimeActionRequest):
    from services.runtime_orchestrator import get_orchestrator

    orch = get_orchestrator()
    try:
        orch.destroy_runtime(req.session_id)
        return {"session_id": req.session_id, "status": "destroyed"}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{session_id}")
async def runtime_status(session_id: str):
    from services.runtime_orchestrator import get_orchestrator

    orch = get_orchestrator()
    session = orch.get_runtime(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Runtime session not found")
    return session.to_dict()


@router.get("/{session_id}/logs")
async def runtime_logs(session_id: str, tail: int = 100):
    from services.runtime_orchestrator import get_orchestrator

    orch = get_orchestrator()
    try:
        logs = orch.get_logs(session_id, tail=tail)
        return {"session_id": session_id, "logs": logs}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{session_id}/metrics")
async def runtime_metrics(session_id: str):
    from services.runtime_orchestrator import get_orchestrator

    orch = get_orchestrator()
    try:
        metrics = orch.get_metrics(session_id)
        return {"session_id": session_id, "metrics": metrics}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("")
async def runtime_list(job_id: str | None = None):
    from services.runtime_orchestrator import get_orchestrator

    orch = get_orchestrator()
    return {"runtimes": orch.list_runtimes(job_id=job_id)}


@router.post("/recover/{session_id}")
async def runtime_recover(session_id: str):
    from services.runtime_orchestrator import get_orchestrator

    orch = get_orchestrator()
    session = orch.recover_failure(session_id)
    if not session:
        raise HTTPException(status_code=500, detail="Recovery failed")
    return {"session_id": session.id, "status": session.status.value}