"""
Requirement Analysis Agent — parses raw prompt into structured JSON.

New in v4:
  - clarify() — asks one question before the pipeline if the prompt is vague
  - stack config support (backend_framework, frontend_framework, db)
"""

import json
import logging
import re
from typing import Any

from database.chroma_db import log_to_db, save_requirements
from services.llm_service import call_model

logger = logging.getLogger(__name__)

SUPPORTED_TYPES = {
    "student_management",
    "inventory_system",
    "blog_app",
    "task_manager",
    "employee_management",
    "crud_dashboard",
    "rest_api",
}
UNSUPPORTED_KEYWORDS = [
    "machine learning",
    "deep learning",
    "neural network",
    "ai model",
    "game engine",
    "video game",
    "unity",
    "unreal",
    "operating system",
    "kernel",
    "blockchain",
    "smart contract",
    "nft",
    "mobile app",
    "android",
    "ios",
    "react native",
    "flutter",
    "desktop gui",
    "tkinter",
    "qt",
]

_SYSTEM = """You are a software requirements analyst.
Given a project description, extract structured requirements.
Respond with valid JSON ONLY — no markdown, no explanation, no code fences.

Required shape:
{
  "project_name":  "string",
  "project_type":  "student_management|inventory_system|blog_app|task_manager|employee_management|crud_dashboard|rest_api",
  "features":      ["feature1", "feature2"],
  "modules":       ["module1", "module2"],
  "complexity":    "simple|medium|complex",
  "auth_required": true|false,
  "db_entities":   ["Entity1", "Entity2"]
}"""

_CLARIFY_SYSTEM = """You are a software requirements assistant.
Read the project description and decide if ONE important clarifying question would significantly improve the output.
If the description is already clear, respond with exactly: CLEAR
If a question is needed, respond with exactly one short question (max 15 words). No preamble."""


def _validate(prompt: str) -> None:
    if not prompt or not prompt.strip():
        raise ValueError("Prompt cannot be empty.")
    if len(prompt.strip()) > 500:
        raise ValueError("Prompt must be under 500 characters.")
    for kw in UNSUPPORTED_KEYWORDS:
        if kw in prompt.lower():
            raise ValueError(f"Unsupported project type: '{kw}'. ProjectPilot supports CRUD/web applications only.")


def _parse_json(text: str) -> dict[str, Any]:
    for fn in [
        lambda t: json.loads(t),
        lambda t: json.loads(re.search(r"```(?:json)?\s*(\{.*?\})\s*```", t, re.DOTALL).group(1)),
        lambda t: json.loads(re.search(r"\{.*\}", t, re.DOTALL).group(0)),
    ]:
        try:
            return fn(text)
        except Exception:
            continue
    raise ValueError(f"Could not extract JSON from model output: {text[:300]}")


def clarify(prompt: str, model: str = None) -> str | None:
    """
    Returns one clarifying question if the prompt is ambiguous, else None.
    Designed to be called BEFORE run_pipeline — the answer is appended to the prompt.
    """
    try:
        resp = call_model(prompt, system_prompt=_CLARIFY_SYSTEM, model=model or "cloud")
        resp = resp.strip()
        if resp.upper() == "CLEAR" or len(resp) < 5:
            return None
        # Sanity: must end with ?
        if not resp.endswith("?"):
            return None
        return resp
    except Exception:
        return None


def run(
    prompt: str,
    project_name: str,
    job_id: str,
    model: str = None,
    stack: dict[str, str] | None = None,
) -> dict[str, Any]:
    log_to_db(job_id, "RequirementAgent", f"Analysing prompt ({len(prompt)} chars).")
    _validate(prompt)

    user_msg = f"Project Name: {project_name or 'Auto-detect'}\nDescription: {prompt}\n\nExtract requirements as JSON."
    try:
        raw = call_model(
            user_msg, system_prompt=_SYSTEM, model=model or "cloud", job_id=job_id, agent="RequirementAgent"
        )
        log_to_db(job_id, "RequirementAgent", "LLM response received.")
    except RuntimeError as exc:
        log_to_db(job_id, "RequirementAgent", f"LLM call failed: {exc}", "ERROR")
        raise

    req = _parse_json(raw)

    if not req.get("features"):
        raise ValueError("No features extracted — please be more specific in your prompt.")
    if project_name:
        req["project_name"] = project_name
    if req.get("project_type") not in SUPPORTED_TYPES:
        req["project_type"] = "crud_dashboard"
        log_to_db(job_id, "RequirementAgent", "project_type defaulted to crud_dashboard.", "WARNING")

    # Attach stack config (tech stack selector)
    if stack:
        req["stack"] = stack
    else:
        req.setdefault(
            "stack",
            {
                "backend": "fastapi",
                "frontend": "streamlit",
                "db": "sqlite",
            },
        )

    save_requirements(job_id, req)
    log_to_db(
        job_id,
        "RequirementAgent",
        f"Done — {len(req.get('features', []))} features, "
        f"type={req.get('project_type')}, complexity={req.get('complexity')}.",
    )
    return req
