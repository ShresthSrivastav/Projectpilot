"""Benchmark Campaign routes — extracted from main.py."""

from fastapi import APIRouter, Body

router = APIRouter(prefix="/campaign", tags=["Campaign"])


@router.post("/run")
def campaign_run(data: dict = Body(...)):
    """Create and execute a benchmark campaign."""
    from services.benchmark_campaign_service import get_benchmark_campaign_service

    service = get_benchmark_campaign_service()
    domains = data.get("domains")
    runs_per_domain = data.get("runs_per_domain", 10)
    name = data.get("name", "")
    parallel = data.get("parallel", True)
    max_workers = data.get("max_workers", 4)
    model = data.get("model", "local")
    skip_run = data.get("skip_run", False)

    campaign = service.create_campaign(
        domains=domains,
        runs_per_domain=runs_per_domain,
        name=name,
        parallel=parallel,
        max_workers=max_workers,
        model=model,
    )

    if not skip_run:
        campaign = service.run_campaign(campaign["id"])

    return {"success": True, "campaign": campaign}


@router.get("/status")
def campaign_status(campaign_id: str):
    """Get campaign status with run details."""
    from services.benchmark_campaign_service import get_benchmark_campaign_service

    service = get_benchmark_campaign_service()
    campaign = service.get_campaign_status(campaign_id)
    if campaign is None:
        return {"success": False, "error": "Campaign not found"}
    return {"success": True, "campaign": campaign}


@router.get("/results")
def campaign_results(
    campaign_id: str,
    domain: str | None = None,
):
    """Get campaign run results."""
    from services.benchmark_campaign_service import get_benchmark_campaign_service

    service = get_benchmark_campaign_service()
    results = service.get_campaign_results(campaign_id, domain=domain)
    return {"success": True, "results": results}


@router.get("/report")
def campaign_report(
    campaign_id: str,
    report_type: str = "aggregate",
):
    """Get campaign report (aggregate, leaderboard, or domain report)."""
    from services.benchmark_campaign_service import get_benchmark_campaign_service

    service = get_benchmark_campaign_service()
    if report_type == "leaderboard":
        report = service.get_campaign_leaderboard(campaign_id)
    elif report_type == "aggregate":
        report = service.get_campaign_report(campaign_id, report_type="aggregate")
    else:
        report = service.get_domain_report(campaign_id, report_type)
    if report is None:
        return {"success": False, "error": f"No {report_type} report found"}
    return {"success": True, "report": report}


@router.post("/resume")
def campaign_resume(data: dict = Body(...)):
    """Resume an interrupted campaign."""
    from services.benchmark_campaign_service import get_benchmark_campaign_service

    service = get_benchmark_campaign_service()
    campaign_id = data.get("campaign_id")
    if not campaign_id:
        return {"success": False, "error": "campaign_id required"}
    try:
        campaign = service.resume_interrupted_campaign(campaign_id)
        return {"success": True, "campaign": campaign}
    except ValueError as e:
        return {"success": False, "error": str(e)}


@router.get("/list")
def campaign_list(limit: int = 50):
    """List all campaigns."""
    from services.benchmark_campaign_service import get_benchmark_campaign_service

    service = get_benchmark_campaign_service()
    campaigns = service.list_campaigns(limit=limit)
    return {"success": True, "campaigns": campaigns}


@router.get("/detect-interrupted")
def campaign_detect_interrupted():
    """Detect interrupted campaigns."""
    from services.benchmark_campaign_service import get_benchmark_campaign_service

    service = get_benchmark_campaign_service()
    interrupted = service.detect_interrupted_campaigns()
    return {"success": True, "interrupted_campaigns": interrupted}
