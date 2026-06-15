"""Advanced Browser Validation — Playwright workflows, journey simulation, screenshot validation, regression testing."""
import json
import logging
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

VALIDATION_DIR = Path(os.getenv("VALIDATION_OUTPUT_DIR", "./validation_artifacts"))


@dataclass
class ValidationStep:
    action: str
    selector: Optional[str] = None
    value: Optional[str] = None
    url: Optional[str] = None
    script: Optional[str] = None
    screenshot_name: Optional[str] = None
    expected_text: Optional[str] = None
    expected_url: Optional[str] = None
    wait_time: float = 0.0
    timeout: int = 10000
    description: str = ""


@dataclass
class UserJourney:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    base_url: str = ""
    steps: List[ValidationStep] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


@dataclass
class ValidationResult:
    step_index: int
    success: bool
    action: str
    selector: Optional[str] = None
    error: Optional[str] = None
    screenshot_path: Optional[str] = None
    page_url: Optional[str] = None
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RegressionTest:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    journeys: List[str] = field(default_factory=list)
    screenshot_comparisons: List[Dict] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_run: Optional[float] = None
    last_status: str = "never_run"
    baseline_dir: Optional[str] = None
    threshold: float = 0.95


class BrowserValidationService:
    def __init__(self):
        self.journeys: Dict[str, UserJourney] = {}
        self.regression_tests: Dict[str, RegressionTest] = {}
        self.baselines: Dict[str, str] = {}
        self._lock = threading.Lock()
        VALIDATION_DIR.mkdir(parents=True, exist_ok=True)

    def create_journey(self, name: str, base_url: str, tags: Optional[List[str]] = None) -> UserJourney:
        journey = UserJourney(name=name, base_url=base_url, tags=tags or [])
        with self._lock:
            self.journeys[journey.id] = journey
        return journey

    def add_step(self, journey_id: str, step: ValidationStep) -> bool:
        with self._lock:
            if journey_id not in self.journeys:
                return False
            self.journeys[journey_id].steps.append(step)
        return True

    def get_journey(self, journey_id: str) -> Optional[UserJourney]:
        return self.journeys.get(journey_id)

    def list_journeys(self) -> List[Dict]:
        return [asdict(j) for j in self.journeys.values()]

    def delete_journey(self, journey_id: str) -> bool:
        with self._lock:
            return self.journeys.pop(journey_id, None) is not None

    def execute_journey(self, journey_id: str, headless: bool = True, base_url: Optional[str] = None) -> Dict[str, Any]:
        journey = self.journeys.get(journey_id)
        if not journey:
            return {"error": f"Journey {journey_id} not found", "success": False}

        from services.browser_service import (
            create_session, navigate, click, fill, select_option,
            screenshot, get_content, evaluate, close_session,
        )

        session = None
        results = []
        overall_success = True

        try:
            session = create_session(headless=headless)
            effective_base = base_url or journey.base_url

            for i, step in enumerate(journey.steps):
                t0 = time.monotonic()
                step_result = ValidationResult(step_index=i, success=False, action=step.action)
                try:
                    if step.action == "navigate":
                        url = step.url or effective_base
                        nav_result = navigate(session.session_id, url, timeout=step.timeout)
                        step_result.success = True
                        step_result.page_url = url

                    elif step.action == "click":
                        if step.selector:
                            click(session.session_id, step.selector, timeout=step.timeout)
                            step_result.success = True
                        else:
                            raise ValueError("selector required for click")

                    elif step.action == "fill":
                        if step.selector and step.value is not None:
                            fill(session.session_id, step.selector, step.value, timeout=step.timeout)
                            step_result.success = True
                        else:
                            raise ValueError("selector and value required for fill")

                    elif step.action == "select":
                        if step.selector and step.value is not None:
                            select_option(session.session_id, step.selector, step.value)
                            step_result.success = True
                        else:
                            raise ValueError("selector and value required for select")

                    elif step.action == "screenshot":
                        name = step.screenshot_name or f"step_{i:03d}"
                        screenshot_result = screenshot(session.session_id, full_page=True)
                        ss_path = screenshot_result.get("screenshot_path", "")
                        step_result.screenshot_path = ss_path
                        step_result.success = bool(ss_path)

                    elif step.action == "check_text":
                        if step.expected_text:
                            content = get_content(session.session_id)
                            text_content = content.get("content", "")
                            if step.expected_text in text_content:
                                step_result.success = True
                            else:
                                raise ValueError(f"Expected text '{step.expected_text}' not found")
                        else:
                            raise ValueError("expected_text required for check_text")

                    elif step.action == "check_url":
                        if step.expected_url:
                            current_url = evaluate(session.session_id, "window.location.href")
                            url_value = current_url.get("result", "")
                            if step.expected_url in url_value:
                                step_result.success = True
                            else:
                                raise ValueError(f"Expected URL '{step.expected_url}' not in current URL")
                        else:
                            raise ValueError("expected_url required for check_url")

                    elif step.action == "evaluate":
                        if step.script:
                            eval_result = evaluate(session.session_id, step.script)
                            step_result.success = True
                            step_result.metadata["result"] = str(eval_result.get("result", ""))[:500]
                        else:
                            raise ValueError("script required for evaluate")

                    elif step.action == "wait":
                        time.sleep(step.wait_time or 1.0)
                        step_result.success = True

                    else:
                        raise ValueError(f"Unknown action: {step.action}")

                except Exception as exc:
                    step_result.error = str(exc)[:300]
                    overall_success = False

                step_result.duration_ms = (time.monotonic() - t0) * 1000
                results.append(asdict(step_result))

            if session:
                close_session(session.session_id)

        except Exception as exc:
            overall_success = False
            if session:
                try:
                    close_session(session.session_id)
                except Exception:
                    pass

        return {
            "journey_id": journey_id,
            "journey_name": journey.name,
            "success": overall_success,
            "steps_total": len(journey.steps),
            "steps_passed": sum(1 for r in results if r["success"]),
            "steps_failed": sum(1 for r in results if not r["success"]),
            "results": results,
            "duration_ms": sum(r["duration_ms"] for r in results),
        }

    def auto_generate_tests(self, repo_path: str, base_url: str, name: str = "Auto-generated journey") -> UserJourney:
        journey = UserJourney(name=name, base_url=base_url)
        project_dir = Path(repo_path)
        if not project_dir.exists():
            return journey

        steps = []
        frontend_files = []
        for fpath in project_dir.rglob("*"):
            if fpath.suffix in (".html", ".py", ".js", ".ts", ".vue", ".svelte") and "__pycache__" not in str(fpath):
                try:
                    rel = str(fpath.relative_to(project_dir))
                    content = fpath.read_text(encoding="utf-8", errors="replace")
                    frontend_files.append({"path": rel, "content": content})
                except Exception:
                    pass

        for file_info in frontend_files[:10]:
            content = file_info["content"]
            rel_path = file_info["path"]

            if "login" in content.lower() or "signin" in content.lower() or 'type="password"' in content:
                steps.append(ValidationStep(action="navigate", url=f"{base_url}/login", description=f"Navigate to login page ({rel_path})"))
                steps.append(ValidationStep(action="fill", selector="input[name='username'],input[name='email']", value="testuser",
                                             description="Fill username"))
                steps.append(ValidationStep(action="fill", selector="input[type='password']", value="testpass",
                                             description="Fill password"))
                steps.append(ValidationStep(action="click", selector="button[type='submit']", description="Submit login"))
                steps.append(ValidationStep(action="check_url", expected_url="/dashboard", description="Verify redirect to dashboard"))

            if "form" in content.lower() or "<form" in content:
                steps.append(ValidationStep(action="navigate", url=f"{base_url}/register", description=f"Navigate to form ({rel_path})"))
                steps.append(ValidationStep(action="fill", selector="input:first-of-type", value="Test User",
                                             description="Fill first field"))
                steps.append(ValidationStep(action="click", selector="button[type='submit']", description="Submit form"))

            if content.count("/api/") > 0 or content.count('fetch(') > 0 or content.count('axios') > 0:
                steps.append(ValidationStep(action="navigate", url=base_url, description=f"Navigate to app root ({rel_path})"))
                steps.append(ValidationStep(action="screenshot", screenshot_name=f"app_root_{Path(rel_path).stem}", description="Take screenshot"))

        if steps:
            journey.steps = steps
            with self._lock:
                self.journeys[journey.id] = journey
            logger.info("Auto-generated %d steps for journey %s", len(steps), journey.id[:8])
        return journey

    def create_regression_test(self, name: str, journey_ids: Optional[List[str]] = None) -> RegressionTest:
        rt = RegressionTest(name=name, journeys=journey_ids or [])
        with self._lock:
            self.regression_tests[rt.id] = rt
        return rt

    def run_regression(self, regression_id: str, headless: bool = True) -> Dict[str, Any]:
        rt = self.regression_tests.get(regression_id)
        if not rt:
            return {"error": "Regression test not found", "success": False}

        journey_results = {}
        all_passed = True
        for jid in rt.journeys:
            result = self.execute_journey(jid, headless=headless)
            journey_results[jid] = result
            if not result.get("success", False):
                all_passed = False

        with self._lock:
            if regression_id in self.regression_tests:
                rt.last_run = time.time()
                rt.last_status = "passed" if all_passed else "failed"

        return {
            "regression_id": regression_id,
            "name": rt.name,
            "success": all_passed,
            "journey_results": journey_results,
            "total_journeys": len(rt.journeys),
            "passed_journeys": sum(1 for jr in journey_results.values() if jr.get("success")),
            "failed_journeys": sum(1 for jr in journey_results.values() if not jr.get("success")),
        }

    def list_regression_tests(self) -> List[Dict]:
        return [asdict(rt) for rt in self.regression_tests.values()]

    def get_regression_test(self, regression_id: str) -> Optional[RegressionTest]:
        return self.regression_tests.get(regression_id)

    def delete_regression_test(self, regression_id: str) -> bool:
        with self._lock:
            return self.regression_tests.pop(regression_id, None) is not None


_validation_service = BrowserValidationService()


def get_validation_service() -> BrowserValidationService:
    return _validation_service
