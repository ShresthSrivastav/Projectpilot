from fastapi import APIRouter, Request

from services.llm_service import (
    CLOUD_MODEL,
    get_available_models,
    get_available_providers,
    get_pull_status,
    is_available,
    is_cloud_available,
)

router = APIRouter(tags=["System"])


@router.get("/health")
async def health():
    available = is_available()
    models = get_available_models() if available else []
    pull_state = get_pull_status()
    models_ready = all(v == "ready" for v in pull_state.values()) if pull_state else False
    return {
        "status": "ok",
        "ollama_online": available,
        "models_ready": models_ready,
        "pull_status": pull_state,
        "available_models": models,
        "cloud_available": is_cloud_available(),
        "cloud_model": CLOUD_MODEL,
        "providers": get_available_providers(),
        "version": "13.0.0",
    }


@router.get("/metrics")
async def metrics(request: Request = None):
    import time as _time

    from database.memory_store import get_analytics_summary, get_cost_summary
    from services.llm_service import get_token_count

    ws_id = getattr(request.state, "workspace_id", "") if request else ""
    tokens = get_token_count()
    analytics = get_analytics_summary(workspace_id=ws_id)
    cost = get_cost_summary(workspace_id=ws_id)
    return {
        "total_tokens": tokens,
        "analytics": analytics,
        "cost": cost,
        "timestamp": _time.time(),
        "workspace_id": ws_id,
    }


@router.get("/providers")
async def list_providers():
    return {"providers": get_available_providers()}
