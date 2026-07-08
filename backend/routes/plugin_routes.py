"""Plugin, Marketplace, Agent, Workflow, and Ecosystem routes — extracted from main.py."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

from database.memory_store import (
    mem_delete_custom_agent,
    mem_delete_custom_workflow,
    mem_delete_plugin,
    mem_list_custom_agents,
    mem_list_custom_workflows,
    mem_save_custom_agent,
    mem_save_custom_workflow,
    mem_save_marketplace_package,
    mem_save_plugin,
)
from services.marketplace_service import get_marketplace_service
from services.plugin_registry import get_plugin_registry

router = APIRouter(prefix="/plugins", tags=["Plugins"])


class _PluginManifest:
    """Minimal inline replacement for sdk.plugin_sdk.base_plugin.PluginManifest (SDK removed)."""

    def __init__(self, name="", version="", author="", description="", compatibility="", plugin_type="", permissions=None):
        self.name = name
        self.version = version
        self.author = author
        self.description = description
        self.compatibility = compatibility
        self.plugin_type = plugin_type
        self.permissions = permissions or []

    def to_dict(self):
        return {
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "compatibility": self.compatibility,
            "plugin_type": self.plugin_type,
            "permissions": self.permissions,
        }


# ── Plugin Registry ──────────────────────────────────────────────────────


@router.post("/install")
async def plugin_install(
    source: str = Body(...),
    name: str | None = Body(None),
    version: str | None = Body(None),
    author: str | None = Body(None),
    description: str | None = Body(None),
    plugin_type: str | None = Body(None),
    permissions: list[str] | None = Body(None),
):
    registry = get_plugin_registry()
    manifest = None
    if name:
        manifest = _PluginManifest(
            name=name,
            version=version or "1.0.0",
            author=author or "",
            description=description or "",
            plugin_type=plugin_type or "tool",
            permissions=permissions or [],
        )
    try:
        entry = registry.install_plugin(source, manifest=manifest, permissions=permissions)
        mem_save_plugin(entry.to_dict())
        return entry.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=f"Source file not found: {e}")


@router.post("/uninstall")
async def plugin_uninstall(data: dict = Body(...)):
    plugin_id = data.get("plugin_id", "")
    registry = get_plugin_registry()
    ok = registry.uninstall_plugin(plugin_id)
    mem_delete_plugin(plugin_id)
    return {"uninstalled": ok}


@router.post("/enable")
async def plugin_enable(data: dict = Body(...)):
    plugin_id = data.get("plugin_id", "")
    registry = get_plugin_registry()
    ok = registry.enable_plugin(plugin_id)
    entry = registry.get_plugin(plugin_id)
    if entry:
        mem_save_plugin(entry.to_dict())
    return {"enabled": ok}


@router.post("/disable")
async def plugin_disable(data: dict = Body(...)):
    plugin_id = data.get("plugin_id", "")
    registry = get_plugin_registry()
    ok = registry.disable_plugin(plugin_id)
    entry = registry.get_plugin(plugin_id)
    if entry:
        mem_save_plugin(entry.to_dict())
    return {"disabled": ok}


@router.get("")
async def plugin_list(plugin_type: str | None = None, enabled_only: bool = False):
    registry = get_plugin_registry()
    entries = registry.list_plugins(plugin_type=plugin_type, enabled_only=enabled_only)
    return {"plugins": [e.to_dict() for e in entries]}


@router.get("/details")
async def plugin_details(plugin_id: str):
    registry = get_plugin_registry()
    entry = registry.get_plugin(plugin_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Plugin not found")
    return entry.to_dict()


# ── Marketplace ──────────────────────────────────────────────────────────


@router.get("/marketplace")
async def plugin_marketplace_search(
    query: str = "",
    package_type: str | None = None,
    tag: str | None = None,
    author: str | None = None,
    sort_by: str = "downloads",
    limit: int = 50,
):
    mkt = get_marketplace_service()
    results = mkt.search_packages(
        query=query,
        package_type=package_type,
        tag=tag,
        author=author,
        sort_by=sort_by,
        limit=limit,
    )
    return {"packages": [p.to_dict() for p in results], "count": len(results)}


@router.post("/marketplace/publish")
async def marketplace_publish(
    name: str = Body(...),
    version: str = Body(...),
    author: str = Body(...),
    description: str = Body(...),
    source_path: str = Body(...),
    package_type: str = Body("plugin"),
    tags: list[str] | None = Body(None),
    readme: str = Body(""),
    compatibility: str = Body(">=11.0.0"),
):
    manifest = _PluginManifest(
        name=name,
        version=version,
        author=author,
        description=description,
        compatibility=compatibility,
    )
    mkt = get_marketplace_service()
    pkg = mkt.publish_package(
        name=name,
        version=version,
        author=author,
        description=description,
        source_path=source_path,
        package_type=package_type,
        tags=tags or [],
        readme=readme,
        manifest=manifest,
    )
    db_data = pkg.to_dict()
    db_data["manifest_json"] = manifest.to_dict()
    db_data["tags"] = tags or []
    mem_save_marketplace_package(db_data)
    return pkg.to_dict()


@router.get("/marketplace/package")
async def marketplace_package_details(package_id: str):
    mkt = get_marketplace_service()
    pkg = mkt.get_package(package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    return pkg.to_dict()


@router.post("/marketplace/rate")
async def marketplace_rate(data: dict = Body(...)):
    mkt = get_marketplace_service()
    pkg = mkt.rate_package(data.get("package_id", ""), data.get("rating", 0.0))
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    return pkg.to_dict()


@router.post("/marketplace/install")
async def marketplace_install(data: dict = Body(...)):
    mkt = get_marketplace_service()
    result = mkt.install_package(data.get("package_id", ""), data.get("target_dir", "plugins"))
    if not result:
        raise HTTPException(status_code=404, detail="Package not found")
    return {"installed_at": result}


@router.get("/marketplace/list")
async def marketplace_list(package_type: str | None = None, verified_only: bool = False):
    mkt = get_marketplace_service()
    results = mkt.list_packages(package_type=package_type, verified_only=verified_only)
    return {"packages": [p.to_dict() for p in results], "count": len(results)}


# ── Custom Agents ────────────────────────────────────────────────────────


@router.post("/agents/register")
async def agent_register(
    name: str = Body(...),
    source: str = Body(...),
    version: str = Body("1.0.0"),
    description: str = Body(""),
    capabilities: list[dict] | None = Body(None),
    hooks: dict[str, str] | None = Body(None),
    config: dict | None = Body(None),
):
    agent_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    agent_data = {
        "id": agent_id,
        "name": name,
        "version": version,
        "description": description,
        "source": source,
        "capabilities": capabilities or [],
        "hooks": hooks or {},
        "config": config or {},
        "enabled": True,
        "created_at": now,
        "updated_at": now,
    }
    mem_save_custom_agent(agent_data)
    return agent_data


@router.get("/agents/custom")
async def agent_list(enabled_only: bool = False):
    agents = mem_list_custom_agents(enabled_only=enabled_only)
    return {"agents": agents, "count": len(agents)}


@router.post("/agents/delete")
async def agent_delete(data: dict = Body(...)):
    agent_id = data.get("agent_id", "")
    ok = mem_delete_custom_agent(agent_id)
    return {"deleted": ok}


# ── Custom Workflows ─────────────────────────────────────────────────────


@router.post("/workflows/register")
async def workflow_register(
    name: str = Body(...),
    source: str = Body(...),
    version: str = Body("1.0.0"),
    description: str = Body(""),
    steps: list[dict] | None = Body(None),
    config: dict | None = Body(None),
):
    workflow_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    workflow_data = {
        "id": workflow_id,
        "name": name,
        "version": version,
        "description": description,
        "source": source,
        "steps": steps or [],
        "status": "pending",
        "config": config or {},
        "enabled": True,
        "created_at": now,
        "updated_at": now,
    }
    mem_save_custom_workflow(workflow_data)
    return workflow_data


@router.get("/workflows")
async def workflow_list(enabled_only: bool = False):
    workflows = mem_list_custom_workflows(enabled_only=enabled_only)
    return {"workflows": workflows, "count": len(workflows)}


@router.post("/workflows/delete")
async def workflow_delete(data: dict = Body(...)):
    workflow_id = data.get("workflow_id", "")
    ok = mem_delete_custom_workflow(workflow_id)
    return {"deleted": ok}


# ── Ecosystem Health ─────────────────────────────────────────────────────


@router.get("/ecosystem/health")
async def ecosystem_health():
    registry = get_plugin_registry()
    mkt = get_marketplace_service()
    plugins = registry.list_plugins()
    packages = mkt.list_packages()
    agents = mem_list_custom_agents()
    workflows = mem_list_custom_workflows()
    return {
        "status": "ok",
        "version": "13.0.0",
        "plugins_installed": len(plugins),
        "plugins_enabled": len([p for p in plugins if p.enabled]),
        "marketplace_packages": len(packages),
        "custom_agents": len(agents),
        "custom_workflows": len(workflows),
    }