"""Process Manager routes — extracted from main.py."""

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

router = APIRouter(prefix="/process", tags=["Process"])


class ProcessRunRequest(BaseModel):
    command: list[str] | None = None
    working_dir: str = ""
    env_vars: dict[str, str] | None = None
    timeout: int = 300
    runtime_type: str = ""
    serve: bool = False


@router.post("/run")
async def process_run(req: ProcessRunRequest):
    from services.process_manager import get_process_manager

    pm = get_process_manager()
    proc = pm.run(
        command=req.command,
        working_dir=req.working_dir,
        env_vars=req.env_vars,
        timeout=req.timeout,
        runtime_type=req.runtime_type,
        serve=req.serve,
    )
    return {"process_id": proc.id, "pid": proc.pid, "status": proc.status.value, "port": proc.port}


@router.get("/{process_id}")
async def process_status(process_id: str):
    from services.process_manager import get_process_manager

    pm = get_process_manager()
    proc = pm.get_process(process_id)
    if not proc:
        raise HTTPException(status_code=404, detail="Process not found")
    return {
        "process_id": proc.id,
        "pid": proc.pid,
        "status": proc.status.value,
        "stdout": proc.stdout[-2000:],
        "stderr": proc.stderr[-2000:],
    }


@router.get("/{process_id}/log")
async def process_log(process_id: str):
    from services.process_manager import get_process_manager

    pm = get_process_manager()
    log = pm.get_process_log(process_id)
    if not log:
        raise HTTPException(status_code=404, detail="Process log not found")
    return Response(log, media_type="text/plain")


@router.get("")
async def process_list():
    from services.process_manager import get_process_manager

    pm = get_process_manager()
    return {"processes": pm.list_processes()}
