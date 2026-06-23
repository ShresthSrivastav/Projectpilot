"""Blueprint Coverage Enforcement — ensures ≥95% of planned files/routes/tables are generated.

This service:
  1. Calculates coverage ratio (generated_files / planned_files)
  2. Identifies missing files, routes, and tables
  3. Auto-generates missing code via LLM
  4. Re-validates after each regeneration
  5. Loops until coverage ≥ 95% or retry budget exhausted
"""

import json
import logging
import time
from pathlib import Path
from typing import Any

from database.chroma_db import log_to_db
from services.file_service import BASE_DIR, write_file, read_file
from services.generation_verifier import verify_all_files
from services.llm_service import call_model, clean_code_response

logger = logging.getLogger(__name__)

MAX_COVERAGE_ATTEMPTS = 5
MIN_COVERAGE = 0.95

_COVERAGE_SYS = (
    "You are an expert Python developer. "
    "Generate ONLY the requested file — complete, runnable code. "
    "No markdown fences, no explanations, no placeholders."
)


def calculate_coverage(
    generated_files: list[str],
    planned_files: list[dict],
) -> dict[str, Any]:
    """Calculate file coverage ratio.

    Args:
        generated_files: List of relative paths that were generated.
        planned_files: List of dicts from blueprint with 'path' key.

    Returns:
        {
            "coverage": float (0-1),
            "generated_count": int,
            "planned_count": int,
            "missing_files": list[str],
        }
    """
    planned_paths = [f.get("path", "") for f in planned_files if f.get("path")]
    generated_set = set(generated_files)

    missing = [p for p in planned_paths if p not in generated_set]
    planned_count = len(planned_paths) or 1  # avoid division by zero
    generated_count = len(generated_files)
    coverage = min(1.0, generated_count / planned_count)

    return {
        "coverage": coverage,
        "generated_count": generated_count,
        "planned_count": planned_count,
        "missing_files": missing,
    }


def calculate_route_coverage(
    main_py_text: str,
    planned_routes: list[dict],
) -> dict[str, Any]:
    """Calculate route coverage in backend/main.py.

    Returns:
        {
            "coverage": float,
            "total_routes": int,
            "missing_routes": list[str],
        }
    """
    missing = []
    for route in planned_routes:
        method = route.get("method", "GET").lower()
        path = route.get("path", "/")
        import re
        pattern = re.compile(
            rf'@(?:app|router)\.{method}\s*\(\s*["\'].*?{re.escape(path)}["\']',
            re.IGNORECASE,
        )
        if not pattern.search(main_py_text):
            if path != "/health" or f'@app.get("/health")' not in main_py_text:
                missing.append(f"{method.upper()} {path}")

    total = len(planned_routes) or 1
    present = total - len(missing)
    coverage = min(1.0, present / total)

    return {
        "coverage": coverage,
        "total_routes": len(planned_routes),
        "missing_routes": missing,
    }


def calculate_table_coverage(
    models_py_text: str,
    planned_tables: list[dict],
) -> dict[str, Any]:
    """Calculate table coverage in database/models.py.

    Returns:
        {
            "coverage": float,
            "total_tables": int,
            "missing_tables": list[str],
        }
    """
    import re
    missing = []
    for table in planned_tables:
        name = table.get("name", "")
        if not name:
            continue
        pattern = re.compile(rf"class\s+{re.escape(name)}\s*\(", re.IGNORECASE)
        if not pattern.search(models_py_text):
            missing.append(name)

    total = len(planned_tables) or 1
    present = total - len(missing)
    coverage = min(1.0, present / total)

    return {
        "coverage": coverage,
        "total_tables": len(planned_tables),
        "missing_tables": missing,
    }


def enforce_coverage(
    job_id: str,
    generated_files: list[str],
    blueprint: dict,
    requirements: dict,
    model: str = "local",
) -> dict[str, Any]:
    """Enforce blueprint coverage. Regenerates missing files until ≥95%.

    Returns:
        {
            "success": bool,
            "coverage": float,
            "files_generated": list[str],
            "issues_resolved": list[str],
            "issues_remaining": list[str],
            "attempts": int,
        }
    """
    log_to_db(job_id, "BlueprintCoverage", "Enforcing blueprint coverage...")
    job_dir = BASE_DIR / job_id
    files_generated: list[str] = list(generated_files)
    issues_resolved: list[str] = []
    issues_remaining: list[str] = []

    for attempt in range(1, MAX_COVERAGE_ATTEMPTS + 1):
        log_to_db(job_id, "BlueprintCoverage", f"Coverage check attempt {attempt}/{MAX_COVERAGE_ATTEMPTS}")

        # File coverage
        file_cov = calculate_coverage(files_generated, blueprint.get("files", []))
        planned_files = blueprint.get("files", [])

        # Route coverage
        main_py = job_dir / "backend" / "main.py"
        main_text = main_py.read_text(errors="replace") if main_py.exists() else ""
        route_cov = calculate_route_coverage(main_text, blueprint.get("routes", []))

        # Table coverage
        models_py = job_dir / "database" / "models.py"
        models_text = models_py.read_text(errors="replace") if models_py.exists() else ""
        table_cov = calculate_table_coverage(models_text, blueprint.get("db_tables", []))

        combined = min(file_cov["coverage"], route_cov["coverage"], table_cov["coverage"])
        log_to_db(job_id, "BlueprintCoverage",
                  f"Coverage: files={file_cov['coverage']:.0%}, "
                  f"routes={route_cov['coverage']:.0%}, "
                  f"tables={table_cov['coverage']:.0%}")

        if combined >= MIN_COVERAGE:
            log_to_db(job_id, "BlueprintCoverage", f"Coverage threshold met ({combined:.0%} >= {MIN_COVERAGE:.0%})")
            return {
                "success": True,
                "coverage": combined,
                "files_generated": files_generated,
                "issues_resolved": issues_resolved,
                "issues_remaining": [],
                "attempts": attempt,
            }

        # Generate missing files
        for missing_file in file_cov["missing_files"]:
            issues_remaining.append(f"Missing file: {missing_file}")
            new_file = _generate_missing_file(job_id, missing_file, blueprint, requirements, model, job_dir)
            if new_file:
                files_generated.append(new_file)
                issues_resolved.append(f"Generated missing file: {missing_file}")

        # Generate missing routes
        for missing_route in route_cov["missing_routes"]:
            issues_remaining.append(f"Missing route: {missing_route}")
            if _regenerate_backend_for_routes(job_id, route_cov["missing_routes"], blueprint, requirements, model, job_dir):
                issues_resolved.append(f"Regenerated backend for route: {missing_route}")

        # Generate missing tables
        for missing_table in table_cov["missing_tables"]:
            issues_remaining.append(f"Missing table: {missing_table}")
            if _regenerate_models_for_tables(job_id, table_cov["missing_tables"], blueprint, requirements, model, job_dir):
                issues_resolved.append(f"Regenerated models for table: {missing_table}")

        if not file_cov["missing_files"] and not route_cov["missing_routes"] and not table_cov["missing_tables"]:
            log_to_db(job_id, "BlueprintCoverage", "No missing items to regenerate, but coverage still low")
            break

    # Final check
    file_cov = calculate_coverage(files_generated, blueprint.get("files", []))
    main_py = job_dir / "backend" / "main.py"
    main_text = main_py.read_text(errors="replace") if main_py.exists() else ""
    route_cov = calculate_route_coverage(main_text, blueprint.get("routes", []))
    models_py = job_dir / "database" / "models.py"
    models_text = models_py.read_text(errors="replace") if models_py.exists() else ""
    table_cov = calculate_table_coverage(models_text, blueprint.get("db_tables", []))
    final_coverage = min(file_cov["coverage"], route_cov["coverage"], table_cov["coverage"])

    log_to_db(job_id, "BlueprintCoverage",
              f"Coverage enforcement complete: {final_coverage:.0%} "
              f"({'PASSED' if final_coverage >= MIN_COVERAGE else 'FAILED'})")

    return {
        "success": final_coverage >= MIN_COVERAGE,
        "coverage": final_coverage,
        "files_generated": files_generated,
        "issues_resolved": issues_resolved,
        "issues_remaining": issues_remaining,
        "attempts": min(attempt, MAX_COVERAGE_ATTEMPTS),
    }


def _generate_missing_file(
    job_id: str,
    file_path: str,
    blueprint: dict,
    requirements: dict,
    model: str,
    job_dir: Path,
) -> str | None:
    """Generate a missing file using LLM."""
    log_to_db(job_id, "BlueprintCoverage", f"Generating missing file: {file_path}")

    # Determine file type for prompt
    feats = ", ".join(requirements.get("features", []))
    routes_json = json.dumps(blueprint.get("routes", []), indent=2)
    tables_json = json.dumps(blueprint.get("db_tables", []), indent=2)

    if file_path.endswith("__init__.py"):
        content = "# auto-generated\n"
        write_file(job_id, file_path, content)
        return file_path

    prompt = f"""Generate the complete file: {file_path}

Project: {requirements.get('project_name', 'App')}
Features: {feats}
Type: {requirements.get('project_type')}

Routes: {routes_json}
DB Tables: {tables_json}

Output ONLY the complete file content — no markdown, no explanations."""

    try:
        content = clean_code_response(
            call_model(prompt, system_prompt=_COVERAGE_SYS, model=model,
                       job_id=job_id, agent="BlueprintCoverage")
        )
        if len(content.strip()) < 20:
            logger.warning("Generated content too short for %s", file_path)
            return None
        write_file(job_id, file_path, content)
        log_to_db(job_id, "BlueprintCoverage", f"Generated: {file_path} ({len(content)} chars)")
        return file_path
    except Exception as exc:
        logger.error("Failed to generate %s: %s", file_path, exc)
        return None


def _regenerate_backend_for_routes(
    job_id: str,
    missing_routes: list[str],
    blueprint: dict,
    requirements: dict,
    model: str,
    job_dir: Path,
) -> bool:
    """Regenerate backend/main.py to include missing routes."""
    log_to_db(job_id, "BlueprintCoverage", f"Regenerating backend for {len(missing_routes)} missing route(s)")

    existing = ""
    try:
        existing = read_file(job_id, "backend/main.py")
    except Exception:
        pass

    prompt = f"""Update the backend/main.py to add these missing routes:
{chr(10).join(missing_routes)}

EXISTING CODE (update it — do not rewrite from scratch):
{existing[:5000]}

Project: {requirements.get('project_name', 'App')}
Features: {', '.join(requirements.get('features', []))}

Add the missing route implementations while preserving ALL existing code.
Output ONLY the updated main.py content — complete file."""

    try:
        content = clean_code_response(
            call_model(prompt, model=model, job_id=job_id, agent="BlueprintCoverage")
        )
        if len(content.strip()) < 100:
            return False
        write_file(job_id, "backend/main.py", content)
        log_to_db(job_id, "BlueprintCoverage", f"Backend regenerated ({len(content)} chars)")
        return True
    except Exception as exc:
        logger.error("Failed to regenerate backend: %s", exc)
        return False


def _regenerate_models_for_tables(
    job_id: str,
    missing_tables: list[str],
    blueprint: dict,
    requirements: dict,
    model: str,
    job_dir: Path,
) -> bool:
    """Regenerate database/models.py to include missing tables."""
    log_to_db(job_id, "BlueprintCoverage", f"Regenerating models for {len(missing_tables)} missing table(s)")

    existing = ""
    try:
        existing = read_file(job_id, "database/models.py")
    except Exception:
        pass

    prompt = f"""Update database/models.py to add these missing SQLAlchemy models:
{chr(10).join(missing_tables)}

EXISTING CODE (update it — preserve all existing models):
{existing[:5000]}

Add new model classes for the missing tables. Rules:
- Import Base from database.db
- Use Column(String(36), primary_key=True) for UUID ids
- Add __repr__ method
Output ONLY the complete updated models.py content."""

    try:
        content = clean_code_response(
            call_model(prompt, model=model, job_id=job_id, agent="BlueprintCoverage")
        )
        if len(content.strip()) < 100:
            return False
        write_file(job_id, "database/models.py", content)
        log_to_db(job_id, "BlueprintCoverage", f"Models regenerated ({len(content)} chars)")
        return True
    except Exception as exc:
        logger.error("Failed to regenerate models: %s", exc)
        return False
