from typing import Any

from fastapi import APIRouter, Body, HTTPException

router = APIRouter(prefix="/supervisor", tags=["Supervisor"])


@router.post("/run-agent/{agent_name}")
async def supervisor_run_agent(agent_name: str, context: dict[str, Any] = Body(..., embed=True)):
    from services.supervisor_service import Supervisor

    s = Supervisor()
    try:
        result = s.delegate(agent_name, context)
        return {"agent": agent_name, "status": "ok", "result": result}
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
