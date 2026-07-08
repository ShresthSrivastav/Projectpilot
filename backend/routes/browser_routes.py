"""Browser agent routes — extracted from main.py."""

from fastapi import APIRouter, Body, HTTPException, Field
from pydantic import BaseModel

router = APIRouter(prefix="/browser", tags=["Browser"])


class BrowserOpenRequest(BaseModel):
    url: str
    timeout: int | None = None


class BrowserActionRequest(BaseModel):
    session_id: str
    action: str = Field(
        ..., description="navigate | click | fill | select | upload | screenshot | content | evaluate | wait"
    )
    selector: str | None = None
    value: str | None = None
    url: str | None = None
    script: str | None = None
    file_path: str | None = None
    timeout: int | None = None
    full_page: bool = True
    state: str = "visible"


class BrowserTestRequest(BaseModel):
    session_id: str
    test_script: str = Field(..., description="One action per line: action | arg1 | arg2")


class BrowserCloseRequest(BaseModel):
    session_id: str


@router.post("/open")
async def browser_open(req: BrowserOpenRequest):
    from services.browser_service import create_session, navigate

    try:
        session = create_session()
        result = navigate(session.session_id, req.url, timeout=req.timeout)
        result["session_id"] = session.session_id
        return result
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/action")
async def browser_action(req: BrowserActionRequest):
    from services.browser_service import (
        click,
        evaluate,
        fill,
        get_content,
        navigate,
        screenshot,
        select_option,
        upload_file,
        wait_for_selector,
    )

    try:
        if req.action == "navigate":
            if not req.url:
                raise HTTPException(status_code=400, detail="url required for navigate")
            return navigate(req.session_id, req.url, timeout=req.timeout)
        elif req.action == "click":
            if not req.selector:
                raise HTTPException(status_code=400, detail="selector required for click")
            return click(req.session_id, req.selector, timeout=req.timeout)
        elif req.action == "fill":
            if not req.selector or req.value is None:
                raise HTTPException(status_code=400, detail="selector and value required for fill")
            return fill(req.session_id, req.selector, req.value, timeout=req.timeout)
        elif req.action == "select":
            if not req.selector or req.value is None:
                raise HTTPException(status_code=400, detail="selector and value required for select")
            return select_option(req.session_id, req.selector, req.value)
        elif req.action == "upload":
            if not req.selector or not req.file_path:
                raise HTTPException(status_code=400, detail="selector and file_path required for upload")
            return upload_file(req.session_id, req.selector, req.file_path)
        elif req.action == "screenshot":
            return screenshot(req.session_id, full_page=req.full_page)
        elif req.action == "content":
            return get_content(req.session_id)
        elif req.action == "evaluate":
            if not req.script:
                raise HTTPException(status_code=400, detail="script required for evaluate")
            return evaluate(req.session_id, req.script)
        elif req.action == "wait":
            if not req.selector:
                raise HTTPException(status_code=400, detail="selector required for wait")
            return wait_for_selector(req.session_id, req.selector, timeout=req.timeout, state=req.state)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {req.action}")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)[:300])


@router.post("/screenshot")
async def browser_screenshot(session_id: str = Body(...), full_page: bool = Body(True)):
    from services.browser_service import screenshot as _screenshot

    try:
        return _screenshot(session_id, full_page=full_page)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/test")
async def browser_test(req: BrowserTestRequest):
    from services.browser_service import run_test

    try:
        result = run_test(req.session_id, req.test_script)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/close")
async def browser_close(req: BrowserCloseRequest):
    from services.browser_service import close_session

    ok = close_session(req.session_id)
    return {"session_id": req.session_id, "closed": ok}


@router.get("/sessions")
async def browser_list_sessions():
    from services.browser_service import list_sessions

    return {"sessions": list_sessions()}


@router.get("/sessions/{session_id}/actions")
async def browser_get_actions(session_id: str):
    from services.browser_service import get_action_log

    try:
        return {"actions": get_action_log(session_id)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))