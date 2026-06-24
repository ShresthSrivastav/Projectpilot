"""Browser Service — Playwright-based browser automation agent.

Capabilities:
  - Open websites with configurable timeouts
  - Navigate, click, fill forms, upload files
  - Capture screenshots and extract page content
  - Execute browser-based tests
  - Record and replay browser actions
  - Secure URL validation with allowlist/blocklist
"""

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Screenshot and artifact storage
SCREENSHOT_DIR = Path(os.getenv("SCREENSHOT_DIR", "./browser_artifacts"))
BROWSER_TIMEOUT = int(os.getenv("BROWSER_TIMEOUT", "30000"))
HEADLESS = os.getenv("BROWSER_HEADLESS", "true").lower() == "true"
ALLOWED_DOMAINS = os.getenv("BROWSER_ALLOWED_DOMAINS", "").split(",") if os.getenv("BROWSER_ALLOWED_DOMAINS") else None
BLOCKED_DOMAINS = os.getenv("BROWSER_BLOCKED_DOMAINS", "localhost:11434,169.254.0.0/16").split(",")

try:
    from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright not installed. Browser agent unavailable.")


@dataclass
class BrowserSession:
    session_id: str
    context: Any = None
    page: Any = None
    created_at: str = ""
    actions: list[dict] = field(default_factory=list)
    current_url: str = ""


_sessions: dict[str, BrowserSession] = {}
_playwright_instance = None


def _validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Invalid URL scheme: {parsed.scheme}. Only http/https allowed.")
    if not parsed.netloc:
        raise ValueError("URL must include a host.")
    host = parsed.hostname or ""
    for blocked in BLOCKED_DOMAINS:
        if blocked and (host == blocked.strip() or host.endswith("." + blocked.strip())):
            raise ValueError(f"Domain '{host}' is blocked for security.")
    if ALLOWED_DOMAINS and not any(
        host == d.strip() or host.endswith("." + d.strip()) for d in ALLOWED_DOMAINS if d.strip()
    ):
        raise ValueError(f"Domain '{host}' is not in the allowed list.")
    return url


def is_available() -> bool:
    return PLAYWRIGHT_AVAILABLE


def _ensure_playwright():
    global _playwright_instance
    if not PLAYWRIGHT_AVAILABLE:
        raise RuntimeError("Playwright is not installed. Run: pip install playwright && playwright install chromium")
    if _playwright_instance is None:
        _playwright_instance = sync_playwright().start()
    return _playwright_instance


def create_session() -> BrowserSession:
    pw = _ensure_playwright()
    session_id = str(uuid.uuid4())
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    browser = pw.chromium.launch(headless=HEADLESS)
    context = browser.new_context(
        viewport={"width": 1280, "height": 720},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    )
    page = context.new_page()
    session = BrowserSession(
        session_id=session_id,
        context=context,
        page=page,
        created_at=datetime.utcnow().isoformat(),
    )
    _sessions[session_id] = session
    logger.info("Browser session created: %s", session_id)
    return session


def close_session(session_id: str) -> bool:
    session = _sessions.pop(session_id, None)
    if session and session.context:
        try:
            session.context.close()
            return True
        except Exception as exc:
            logger.warning("Error closing session %s: %s", session_id, exc)
    return False


def get_session(session_id: str) -> BrowserSession | None:
    return _sessions.get(session_id)


def list_sessions() -> list[dict]:
    return [
        {
            "session_id": s.session_id,
            "created_at": s.created_at,
            "current_url": s.current_url,
            "actions": len(s.actions),
        }
        for s in _sessions.values()
    ]


def _log_action(session: BrowserSession, action: str, details: dict):
    entry = {"action": action, "timestamp": datetime.utcnow().isoformat(), "url": session.current_url, **details}
    session.actions.append(entry)
    logger.info("Browser action [%s]: %s %s", session.session_id[:8], action, json.dumps(details)[:200])


def navigate(session_id: str, url: str, timeout: int | None = None) -> dict:
    session = _get_valid_session(session_id)
    url = _validate_url(url)
    t = timeout or BROWSER_TIMEOUT
    resp = session.page.goto(url, timeout=t, wait_until="networkidle")
    session.current_url = session.page.url
    status = resp.status if resp else 0
    _log_action(session, "navigate", {"url": url, "status": status})
    return {"url": session.current_url, "status": status, "title": session.page.title()}


def click(session_id: str, selector: str, timeout: int | None = None) -> dict:
    session = _get_valid_session(session_id)
    t = timeout or BROWSER_TIMEOUT
    session.page.wait_for_selector(selector, timeout=t)
    session.page.click(selector)
    _log_action(session, "click", {"selector": selector})
    return {"selector": selector, "url": session.page.url}


def fill(session_id: str, selector: str, value: str, timeout: int | None = None) -> dict:
    session = _get_valid_session(session_id)
    t = timeout or BROWSER_TIMEOUT
    session.page.wait_for_selector(selector, timeout=t)
    session.page.fill(selector, value)
    _log_action(session, "fill", {"selector": selector, "value_length": len(value)})
    return {"selector": selector, "filled": True}


def select_option(session_id: str, selector: str, value: str) -> dict:
    session = _get_valid_session(session_id)
    session.page.wait_for_selector(selector, timeout=BROWSER_TIMEOUT)
    session.page.select_option(selector, value)
    _log_action(session, "select_option", {"selector": selector, "value": value})
    return {"selector": selector, "value": value}


def upload_file(session_id: str, selector: str, file_path: str) -> dict:
    session = _get_valid_session(session_id)
    full_path = Path(file_path)
    if not full_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    session.page.wait_for_selector(selector, timeout=BROWSER_TIMEOUT)
    session.page.set_input_files(selector, str(full_path.resolve()))
    _log_action(session, "upload_file", {"selector": selector, "file": file_path})
    return {"selector": selector, "file": file_path, "uploaded": True}


def screenshot(session_id: str, full_page: bool = True) -> dict:
    session = _get_valid_session(session_id)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{session_id}_{uuid.uuid4().hex[:8]}.png"
    filepath = SCREENSHOT_DIR / filename
    session.page.screenshot(path=str(filepath), full_page=full_page)
    _log_action(session, "screenshot", {"file": filename, "full_page": full_page})
    return {"file": filename, "path": str(filepath), "size_bytes": filepath.stat().st_size if filepath.exists() else 0}


def get_content(session_id: str) -> dict:
    session = _get_valid_session(session_id)
    content = session.page.content()
    text = session.page.inner_text("body")
    _log_action(session, "get_content", {"content_length": len(content)})
    return {"html_length": len(content), "text_preview": text[:5000], "title": session.page.title()}


def evaluate(session_id: str, script: str) -> dict:
    session = _get_valid_session(session_id)
    result = session.page.evaluate(script)
    _log_action(session, "evaluate", {"script": script[:100]})
    return {"result": str(result)[:5000]}


def wait_for_selector(session_id: str, selector: str, timeout: int | None = None, state: str = "visible") -> dict:
    session = _get_valid_session(session_id)
    t = timeout or BROWSER_TIMEOUT
    session.page.wait_for_selector(selector, timeout=t, state=state)
    _log_action(session, "wait_for_selector", {"selector": selector, "state": state})
    return {"selector": selector, "found": True}


def run_test(session_id: str, test_script: str) -> dict:
    session = _get_valid_session(session_id)
    steps = []
    passed = True
    error = ""
    try:
        for line in test_script.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|")
            action = parts[0].strip()
            args = [p.strip() for p in parts[1:]] if len(parts) > 1 else []
            step_result = _execute_test_step(session, action, args)
            steps.append({"action": action, "args": args, "result": step_result})
            if "error" in step_result:
                passed = False
                error = step_result["error"]
                break
    except Exception as exc:
        passed = False
        error = str(exc)
        steps.append({"action": "error", "error": error})
    _log_action(session, "run_test", {"steps": len(steps), "passed": passed})
    return {"passed": passed, "steps": steps, "error": error, "total_steps": len(steps)}


def _execute_test_step(session: BrowserSession, action: str, args: list[str]) -> dict:
    try:
        if action == "navigate" and args:
            return {"status": "ok", "url": session.page.url}
        elif action == "click" and args:
            session.page.click(args[0])
            return {"status": "ok"}
        elif action == "fill" and len(args) >= 2:
            session.page.fill(args[0], args[1])
            return {"status": "ok"}
        elif action == "assert_text" and args:
            content = session.page.inner_text("body")
            assert args[0] in content, f"Text '{args[0]}' not found on page"
            return {"status": "ok", "found": True}
        elif action == "assert_url" and args:
            assert args[0] in session.page.url, f"URL does not contain '{args[0]}'"
            return {"status": "ok"}
        elif action == "wait" and args:
            import time as _time

            _time.sleep(float(args[0]))
            return {"status": "ok"}
        elif action == "screenshot":
            SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
            fname = f"test_{uuid.uuid4().hex[:8]}.png"
            session.page.screenshot(path=str(SCREENSHOT_DIR / fname))
            return {"status": "ok", "file": fname}
        else:
            return {"status": "skipped", "reason": f"Unknown action: {action}"}
    except AssertionError as exc:
        return {"status": "fail", "error": str(exc)}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def get_action_log(session_id: str) -> list[dict]:
    session = _get_valid_session(session_id)
    return session.actions


def _get_valid_session(session_id: str) -> BrowserSession:
    session = _sessions.get(session_id)
    if not session:
        raise ValueError(f"Browser session not found: {session_id}")
    return session


def cleanup_all_sessions():
    for sid in list(_sessions.keys()):
        close_session(sid)
    global _playwright_instance
    if _playwright_instance:
        try:
            _playwright_instance.stop()
        except Exception:
            pass
        _playwright_instance = None
