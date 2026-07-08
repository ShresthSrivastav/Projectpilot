"""Benchmark Suite routes — extracted from main.py."""

from fastapi import APIRouter, HTTPException, Field
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

router = APIRouter(prefix="/benchmarks", tags=["Benchmarks"])


class BenchmarkRunRequest(BaseModel):
    domain: str = Field(..., min_length=1, max_length=50)
    model: str = "local"
    iteration: int = 1


class BenchmarkCompareRequest(BaseModel):
    run_id_1: str
    run_id_2: str


LIST_SUPPORTED_DOMAINS = [
    "hotel_booking", "ecommerce", "blog_cms", "task_manager",
    "expense_tracker", "chat_app", "lms", "property_management",
]


@router.get("/domains")
async def benchmark_domains():
    from services.benchmark_service import get_benchmark_service

    svc = get_benchmark_service()
    return {"domains": svc.list_domains()}


@router.get("/domain/{domain}")
async def benchmark_domain_info(domain: str):
    from services.benchmark_service import get_benchmark_service

    svc = get_benchmark_service()
    info = svc.get_domain_info(domain)
    if not info:
        raise HTTPException(status_code=404, detail=f"Domain '{domain}' not found")
    return info


@router.post("/run")
async def benchmark_run(req: BenchmarkRunRequest):
    from services.benchmark_service import get_benchmark_service

    svc = get_benchmark_service()
    try:
        result = svc.run_benchmark(domain=req.domain, model=req.model, iteration=req.iteration)
        return {"run_id": result.run_id, "result_id": result.id, "domain": result.domain, "status": result.status.value}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/result/{run_id}")
async def benchmark_result(run_id: str):
    from services.benchmark_service import get_benchmark_service

    svc = get_benchmark_service()
    result = svc.get_result(run_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Benchmark run '{run_id}' not found")
    return result.to_dict()


@router.get("/results")
async def benchmark_results(domain: str | None = None, limit: int = 50):
    from services.benchmark_service import get_benchmark_service

    svc = get_benchmark_service()
    return {"results": svc.list_results(domain=domain, limit=limit)}


@router.get("/leaderboard")
async def benchmark_leaderboard(domain: str | None = None, limit: int = 20):
    from services.benchmark_service import get_benchmark_service

    svc = get_benchmark_service()
    return {"leaderboard": svc.get_leaderboard(domain=domain, limit=limit)}


@router.post("/compare")
async def benchmark_compare(req: BenchmarkCompareRequest):
    from services.benchmark_service import get_benchmark_service

    svc = get_benchmark_service()
    try:
        return svc.compare_runs(req.run_id_1, req.run_id_2)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/report/{run_id}")
async def benchmark_report(run_id: str, format: str = "json"):
    from services.benchmark_service import get_benchmark_service

    svc = get_benchmark_service()
    try:
        report = svc.generate_report(run_id, format=format)
        media_type = "text/markdown" if format == "markdown" else "application/json"
        return PlainTextResponse(report, media_type=media_type)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/trends")
async def benchmark_trends(domain: str | None = None):
    from services.benchmark_service import get_benchmark_service

    svc = get_benchmark_service()
    return svc.get_trend_data(domain=domain)


@router.get("/statistics")
async def benchmark_statistics():
    from services.benchmark_service import get_benchmark_service

    svc = get_benchmark_service()
    return svc.get_statistics()