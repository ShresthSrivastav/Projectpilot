"""Browser Validation routes — extracted from main.py."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/validation", tags=["Browser Validation"])


class CreateJourneyRequest(BaseModel):
    name: str
    base_url: str
    tags: list[str] | None = None


class AddStepRequest(BaseModel):
    journey_id: str
    action: str
    selector: str | None = None
    value: str | None = None
    url: str | None = None
    script: str | None = None
    screenshot_name: str | None = None
    expected_text: str | None = None
    expected_url: str | None = None
    wait_time: float = 0.0
    timeout: int = 10000
    description: str = ""


class ExecuteJourneyRequest(BaseModel):
    journey_id: str
    headless: bool = True
    base_url: str | None = None


class AutoGenerateRequest(BaseModel):
    repo_path: str
    base_url: str
    name: str = "Auto-generated journey"


class RegressionRequest(BaseModel):
    name: str
    journey_ids: list[str] | None = None


class RunRegressionRequest(BaseModel):
    regression_id: str
    headless: bool = True


@router.post("/journey/create")
async def validation_create_journey(req: CreateJourneyRequest):
    from services.browser_validation_service import get_validation_service

    vs = get_validation_service()
    journey = vs.create_journey(req.name, req.base_url, req.tags)
    return {"journey_id": journey.id, "name": journey.name, "step_count": 0}


@router.post("/journey/step")
async def validation_add_step(req: AddStepRequest):
    from services.browser_validation_service import ValidationStep, get_validation_service

    vs = get_validation_service()
    step = ValidationStep(
        action=req.action,
        selector=req.selector,
        value=req.value,
        url=req.url,
        script=req.script,
        screenshot_name=req.screenshot_name,
        expected_text=req.expected_text,
        expected_url=req.expected_url,
        wait_time=req.wait_time,
        timeout=req.timeout,
        description=req.description,
    )
    ok = vs.add_step(req.journey_id, step)
    if not ok:
        raise HTTPException(status_code=404, detail="Journey not found")
    return {"ok": True, "journey_id": req.journey_id}


@router.post("/journey/execute")
async def validation_execute_journey(req: ExecuteJourneyRequest):
    from services.browser_validation_service import get_validation_service

    vs = get_validation_service()
    return vs.execute_journey(req.journey_id, headless=req.headless, base_url=req.base_url)


@router.post("/auto-generate")
async def validation_auto_generate(req: AutoGenerateRequest):
    from services.browser_validation_service import get_validation_service

    vs = get_validation_service()
    journey = vs.auto_generate_tests(req.repo_path, req.base_url, req.name)
    return {"journey_id": journey.id, "name": journey.name, "steps": len(journey.steps)}


@router.post("/regression/create")
async def validation_create_regression(req: RegressionRequest):
    from services.browser_validation_service import get_validation_service

    vs = get_validation_service()
    rt = vs.create_regression_test(req.name, req.journey_ids)
    return {"regression_id": rt.id, "name": rt.name}


@router.post("/regression/run")
async def validation_run_regression(req: RunRegressionRequest):
    from services.browser_validation_service import get_validation_service

    vs = get_validation_service()
    return vs.run_regression(req.regression_id, headless=req.headless)


@router.get("/journeys")
async def validation_list_journeys():
    from services.browser_validation_service import get_validation_service

    vs = get_validation_service()
    return {"journeys": vs.list_journeys()}


@router.get("/regression-tests")
async def validation_list_regression():
    from services.browser_validation_service import get_validation_service

    vs = get_validation_service()
    return {"regression_tests": vs.list_regression_tests()}


@router.delete("/journey/{journey_id}")
async def validation_delete_journey(journey_id: str):
    from services.browser_validation_service import get_validation_service

    vs = get_validation_service()
    ok = vs.delete_journey(journey_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Journey not found")
    return {"deleted": True}