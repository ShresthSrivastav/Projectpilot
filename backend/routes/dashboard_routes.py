"""Dashboard routes — extracted from main.py."""

import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/status")
async def dashboard_status():
    from services.dashboard_service import get_dashboard_status

    return get_dashboard_status()


@router.get("/timeline")
async def dashboard_timeline(limit: int = 100):
    from services.dashboard_service import get_timeline

    return {"events": get_timeline(limit=limit)}


@router.get("/agents")
async def dashboard_agents():
    from services.dashboard_service import get_all_agents

    return {"agents": get_all_agents()}


@router.get("/agents/{name}")
async def dashboard_agent(name: str):
    from fastapi import HTTPException
    from services.dashboard_service import get_agent

    agent = get_agent(name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    return agent


@router.get("/graph")
async def dashboard_graph(agent: str | None = None):
    from services.dashboard_service import get_execution_graph

    return get_execution_graph(agent_name=agent)


@router.get("/memory")
async def dashboard_memory():
    from services.dashboard_service import track_memory_usage

    return track_memory_usage()


@router.websocket("/stream")
async def dashboard_websocket(websocket: WebSocket):
    from services.dashboard_service import get_dashboard_status, subscribe, unsubscribe

    await websocket.accept()

    def _on_event(event):
        try:
            import anyio

            anyio.from_thread.run(
                websocket.send_json,
                {
                    "type": event.event_type,
                    "data": event.data,
                    "timestamp": event.timestamp,
                },
            )
        except Exception:
            pass

    subscribe(_on_event)
    try:
        await websocket.send_json({"type": "initial", "data": get_dashboard_status(), "timestamp": time.time()})
        while True:
            try:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_json({"type": "pong"})
            except WebSocketDisconnect:
                break
    except Exception:
        pass
    finally:
        unsubscribe(_on_event)


# ── Dashboard Extensions (v10) ───────────────────────────────────────────


@router.get("/runtimes")
async def dashboard_runtimes():
    from services.runtime_orchestrator import get_orchestrator

    orch = get_orchestrator()
    return {"runtimes": orch.list_runtimes()}


@router.get("/deployments")
async def dashboard_deployments():
    from services.deployment_orchestrator import get_deployment_orchestrator

    orch = get_deployment_orchestrator()
    return {"deployments": orch.list_sessions()}


@router.get("/healings")
async def dashboard_healings():
    from services.self_healing_service import get_healing_engine

    engine = get_healing_engine()
    return {"healings": engine.list_sessions()}


@router.get("/learning")
async def dashboard_learning():
    from services.learning_engine import get_learning_engine

    engine = get_learning_engine()
    return engine.get_statistics()


@router.get("/infrastructure")
async def dashboard_infrastructure():
    from services.runtime_monitor import get_monitor

    monitor = get_monitor()
    return monitor.get_summary()