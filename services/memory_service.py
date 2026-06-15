"""Memory Service — long-term cross-project learning and retrieval.

Provides high-level API for storing and retrieving:
- Coding preferences learned across projects
- Reusable component patterns
- Fix patterns that were successful
- Project insights and learnings
"""
import json
import logging
from typing import Any, Dict, List, Optional

from database.memory_store import (
    get_coding_preferences, set_coding_preference,
    get_reusable_components, save_reusable_component,
    get_fix_patterns, record_fix_pattern,
    get_project_insights, save_project_insight,
)

logger = logging.getLogger(__name__)


def learn_from_project(job_id: str, requirements: Dict, blueprint: Dict, test_results: Dict) -> Dict[str, Any]:
    insights = {}
    try:
        tech_stack = blueprint.get("tech_stack", {})
        backend = tech_stack.get("backend", "fastapi")
        frontend = tech_stack.get("frontend", "streamlit")
        db = tech_stack.get("db", "sqlite")
        key = f"stack:{backend}:{frontend}:{db}"
        set_coding_preference(key, json.dumps(tech_stack), source=job_id, confidence=0.5)
        insights["stack_preference"] = key

        test_passed = test_results.get("passed", False)
        if test_passed:
            insight_summary = f"Project {job_id} completed with all tests passing"
            save_project_insight(job_id, "successful_generation", insight_summary,
                                 json.dumps({"test_results": test_results}))
        else:
            failures = test_results.get("failures", [])
            if failures:
                insight_summary = f"Project {job_id} had {len(failures)} test failures"
                save_project_insight(job_id, "test_failures", insight_summary,
                                     json.dumps({"failures": failures[:5]}))

        feature_count = len(requirements.get("features", []))
        file_count = blueprint.get("file_count", 0)
        if feature_count > 0 and file_count > 0:
            ratio = round(file_count / feature_count, 1)
            insight_summary = f"Typical complexity: {ratio} files per feature"
            save_project_insight(job_id, "complexity_pattern", insight_summary,
                                 json.dumps({"features": feature_count, "files": file_count, "ratio": ratio}))

        insights["learned"] = True
    except Exception as exc:
        logger.warning("learn_from_project failed: %s", exc)
        insights["learned"] = False
        insights["error"] = str(exc)
    return insights


def get_context_for_prompt(prompt: str, job_id: Optional[str] = None) -> Dict[str, Any]:
    context = {}
    try:
        prefs = get_coding_preferences(limit=10)
        if prefs:
            context["coding_preferences"] = prefs

        patterns = get_fix_patterns(limit=5)
        if patterns:
            context["fix_patterns"] = patterns

        components = get_reusable_components(limit=5)
        if components:
            context["reusable_components"] = components

        if job_id:
            insights = get_project_insights(limit=5)
            if insights:
                context["project_insights"] = insights
    except Exception as exc:
        logger.warning("get_context_for_prompt failed: %s", exc)
    return context


def record_successful_fix(error_text: str, file_pattern: str, fix_desc: str) -> None:
    error_type = _classify_error(error_text)
    record_fix_pattern(error_type, error_text, file_pattern, fix_desc)


def _classify_error(error_text: str) -> str:
    error_text = error_text.lower()
    if "importerror" in error_text or "modulenotfound" in error_text:
        return "import_error"
    if "assertionerror" in error_text or "assert " in error_text:
        return "assertion_error"
    if "syntaxerror" in error_text or "syntax" in error_text:
        return "syntax_error"
    if "nameerror" in error_text:
        return "name_error"
    if "typeerror" in error_text:
        return "type_error"
    if "valueerror" in error_text:
        return "value_error"
    if "attributeerror" in error_text:
        return "attribute_error"
    if "keyerror" in error_text:
        return "key_error"
    if "indexerror" in error_text:
        return "index_error"
    if "timeouterror" in error_text or "timeout" in error_text:
        return "timeout_error"
    return "unknown"
