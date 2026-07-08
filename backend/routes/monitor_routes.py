"""Runtime Monitor routes — extracted from main.py."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/monitor", tags=["Monitor"])


class MonitorStartRequest(BaseModel):
    runtime_id: str
    interval: float = 5.0


@router.post("/start")
async def monitor_start(req: MonitorStartRequest):
    from services.runtime_monitor import get_monitor

    monitor = get_monitor()
    monitor.start_collecting(req.runtime_id, interval=req.interval)
    return {"runtime_id": req.runtime_id, "collecting": True}


@router.post("/stop/{runtime_id}")
async def monitor_stop(runtime_id: str):
    from services.runtime_monitor import get_monitor

    monitor = get_monitor()
    monitor.stop_collecting(runtime_id)
    return {"runtime_id": runtime_id, "collecting": False}


@router.get("/{runtime_id}/metrics")
async def monitor_metrics(runtime_id: str, since: float | None = None, limit: int = 100):
    from services.runtime_monitor import get_monitor

    monitor = get_monitor()
    return {"runtime_id": runtime_id, "metrics": monitor.get_metrics(runtime_id, since=since, limit=limit)}


@router.get("/{runtime_id}/aggregate")
async def monitor_aggregate(runtime_id: str):
    from services.runtime_monitor import get_monitor

    monitor = get_monitor()
    return {"runtime_id": runtime_id, "aggregate": monitor.get_aggregate(runtime_id)}


@router.get("/{runtime_id}/trend")
async def monitor_trend(runtime_id: str, window: int = 10):
    from services.runtime_monitor import get_monitor

    monitor = get_monitor()
    return {"runtime_id": runtime_id, "trend": monitor.get_trend(runtime_id, window=window)}


@router.get("/anomalies")
async def monitor_anomalies(limit: int = 50):
    from services.runtime_monitor import get_monitor

    monitor = get_monitor()
    return {"anomalies": monitor.get_anomalies(limit=limit)}


@router.get("/summary")
async def monitor_summary():
    from services.runtime_monitor import get_monitor

    monitor = get_monitor()
    return monitor.get_summary()