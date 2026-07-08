"""Container Manager routes — extracted from main.py."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/container", tags=["Container"])


class ContainerCreateRequest(BaseModel):
    image: str = "python:3.11-slim"
    command: list[str] | None = None
    env_vars: dict[str, str] | None = None
    port_mappings: dict[str, int] | None = None
    memory_limit: str = "256m"
    cpu_limit: float = 0.5
    network_enabled: bool = True
    volumes: list[str] | None = None
    name: str = ""


class ContainerActionRequest(BaseModel):
    container_id: str


@router.post("/create")
async def container_create(req: ContainerCreateRequest):
    from services.container_manager import get_container_manager

    cm = get_container_manager()
    container = cm.create_container(
        image=req.image,
        command=req.command,
        env_vars=req.env_vars,
        port_mappings={int(k): v for k, v in (req.port_mappings or {}).items()},
        memory_limit=req.memory_limit,
        cpu_limit=req.cpu_limit,
        network_enabled=req.network_enabled,
        volumes=req.volumes,
        name=req.name,
    )
    return {"container_id": container.id, "docker_id": container.docker_id, "status": container.status}


@router.post("/start")
async def container_start(req: ContainerActionRequest):
    from services.container_manager import get_container_manager

    cm = get_container_manager()
    try:
        container = cm.start_container(req.container_id)
        return {"container_id": req.container_id, "status": container.status}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/stop")
async def container_stop(req: ContainerActionRequest):
    from services.container_manager import get_container_manager

    cm = get_container_manager()
    try:
        container = cm.stop_container(req.container_id)
        return {"container_id": req.container_id, "status": container.status}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/restart")
async def container_restart(req: ContainerActionRequest):
    from services.container_manager import get_container_manager

    cm = get_container_manager()
    try:
        container = cm.restart_container(req.container_id)
        return {"container_id": req.container_id, "status": container.status}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/destroy")
async def container_destroy(req: ContainerActionRequest):
    from services.container_manager import get_container_manager

    cm = get_container_manager()
    try:
        cm.destroy_container(req.container_id)
        return {"container_id": req.container_id, "status": "destroyed"}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{container_id}/logs")
async def container_logs(container_id: str, tail: int = 100):
    from services.container_manager import get_container_manager

    cm = get_container_manager()
    try:
        logs = cm.get_logs(container_id, tail=tail)
        return {"container_id": container_id, "logs": logs}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{container_id}/stats")
async def container_stats(container_id: str):
    from services.container_manager import get_container_manager

    cm = get_container_manager()
    try:
        stats = cm.get_stats(container_id)
        return {"container_id": container_id, "stats": stats}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{container_id}/health")
async def container_health(container_id: str):
    from services.container_manager import get_container_manager

    cm = get_container_manager()
    healthy = cm.health_check(container_id)
    return {"container_id": container_id, "healthy": healthy}