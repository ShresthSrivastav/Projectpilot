"""Task graph + knowledge graph + cost + visualizer routes — extracted from main.py."""

import json

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/graph", tags=["Graph Engine"])


class GraphBuildRequest(BaseModel):
    prompt: str
    job_id: str
    model: str = "cloud"
    stack: dict | None = None


class GraphExecuteRequest(BaseModel):
    graph_id: str
    max_workers: int = 4


@router.post("/build")
async def graph_build(req: GraphBuildRequest):
    from services.graph_engine import PlanBuilder
    from database.memory_store import save_graph_session

    builder = PlanBuilder()
    graph = builder.build_standard_plan(req.prompt, req.job_id, req.model, req.stack)
    save_graph_session(graph.id, req.job_id, json.dumps(graph.to_dict()), "built")
    return {
        "graph_id": graph.id,
        "tasks": [t.to_dict() for t in graph.tasks.values()],
        "topological_order": graph.get_topological_order(),
        "critical_path": [t.id for t in graph.get_critical_path()],
        "visualization": graph.visualize_mermaid(),
    }


@router.post("/execute")
async def graph_execute(req: GraphExecuteRequest):
    from database.memory_store import get_graph_session
    from services.graph_engine import GraphExecutor, TaskGraph

    saved = get_graph_session(req.graph_id)
    if not saved:
        raise HTTPException(status_code=404, detail="Graph not found")
    data = json.loads(saved["graph_data"])
    graph = TaskGraph(graph_id=req.graph_id)
    for tid, tdata in data.get("tasks", {}).items():
        from services.graph_engine import Task, TaskPriority

        t = Task(
            id=tid,
            name=tdata.get("name", ""),
            deps=tdata.get("deps", []),
            dependents=tdata.get("dependents", []),
            agent_name=tdata.get("agent_name", ""),
            kwargs=tdata.get("kwargs", {}),
            priority=TaskPriority(tdata.get("priority", 2)),
        )
        graph.tasks[tid] = t
    executor = GraphExecutor(graph, max_workers=req.max_workers)
    result = executor.execute()
    save_graph_session(req.graph_id, "", json.dumps(graph.to_dict()), "executed")
    return {"graph_id": req.graph_id, "status": graph.to_dict(), "execution": result}


@router.get("/{graph_id}")
async def graph_status(graph_id: str):
    from database.memory_store import get_graph_session

    saved = get_graph_session(graph_id)
    if not saved:
        raise HTTPException(status_code=404, detail="Graph not found")
    return saved


@router.get("/{graph_id}/visualize")
async def graph_visualize(graph_id: str):
    from database.memory_store import get_graph_session
    from services.graph_engine import TaskGraph

    saved = get_graph_session(graph_id)
    if not saved:
        raise HTTPException(status_code=404, detail="Graph not found")
    data = json.loads(saved["graph_data"])
    graph = TaskGraph(graph_id=graph_id)
    for tid, tdata in data.get("tasks", {}).items():
        from services.graph_engine import Task

        graph.tasks[tid] = Task.from_dict(tdata)
    return {
        "mermaid": graph.visualize_mermaid(),
        "topological_order": graph.get_topological_order(),
        "critical_path": [t.id for t in graph.get_critical_path()],
    }


@router.get("/{graph_id}/checkpoints")
async def graph_checkpoints(graph_id: str):
    from services.graph_engine import TaskGraph

    g = TaskGraph(graph_id=graph_id)
    return {"checkpoints": g.list_checkpoints()}


@router.post("/{graph_id}/resume/{checkpoint_id}")
async def graph_resume(graph_id: str, checkpoint_id: str, max_workers: int = 4):
    from services.graph_engine import GraphExecutor, TaskGraph

    g = TaskGraph(graph_id=graph_id)
    loaded = g.load_checkpoint(checkpoint_id)
    if not loaded:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    executor = GraphExecutor(loaded, max_workers=max_workers)
    result = executor.execute()
    return {"graph_id": graph_id, "status": loaded.to_dict(), "execution": result}


list_router = APIRouter(prefix="/graphs", tags=["Graph Engine"])


@list_router.get("")
async def graph_list():
    from database.memory_store import list_graph_sessions

    return {"graphs": list_graph_sessions()}
