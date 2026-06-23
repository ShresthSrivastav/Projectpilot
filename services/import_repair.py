"""Import Repair Service — detects and auto-fixes import failures.

When import validation fails, this service:
  1. Parses all imports from generated Python files
  2. Checks each import against the actual module tree
  3. Auto-generates missing modules (empty __init__.py or stub files)
  4. For unresolvable imports, proposes fixes via LLM
  5. Re-validates the import graph until clean
"""

import ast
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from database.chroma_db import log_to_db
from services.file_service import BASE_DIR
from services.llm_service import call_model

logger = logging.getLogger(__name__)

MAX_REPAIR_ATTEMPTS = 3
STDLIB_MODULES: set[str] | None = None


def _get_stdlib_modules() -> set[str]:
    global STDLIB_MODULES
    if STDLIB_MODULES is None:
        STDLIB_MODULES = set(sys.stdlib_module_names)
    return STDLIB_MODULES


def get_all_imports(job_dir: Path) -> dict[str, list[str]]:
    """Parse all imports from Python files in job_dir.

    Returns:
        {file_path: [import_string, ...]}
    """
    imports: dict[str, list[str]] = {}
    for py_file in sorted(job_dir.rglob("*.py")):
        if "__pycache__" in py_file.parts:
            continue
        rel = str(py_file.relative_to(job_dir))
        try:
            text = py_file.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(text, filename=rel)
            file_imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        file_imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        file_imports.append(node.module)
            imports[rel] = file_imports
        except SyntaxError:
            imports[rel] = ["<syntax_error>"]
        except Exception as exc:
            imports[rel] = [f"<error: {exc}>"]
    return imports


def validate_import_graph(job_dir: Path, job_id: str = "") -> dict[str, Any]:
    """Validate that all imports in generated code can be resolved.

    Returns:
        {
            "valid": bool,
            "unresolved": {file: [module, ...]},
            "syntax_errors": [file, ...],
            "details": str,
        }
    """
    stdlib = _get_stdlib_modules()
    unresolved: dict[str, list[str]] = {}
    syntax_errors: list[str] = []
    all_imports = get_all_imports(job_dir)

    for rel_path, file_imports in all_imports.items():
        if file_imports == ["<syntax_error>"]:
            syntax_errors.append(rel_path)
            continue
        for mod in file_imports:
            if not mod:
                continue
            # Skip stdlib modules
            top_level = mod.split(".")[0]
            if top_level in stdlib:
                continue
            # Skip known third-party packages
            if _is_known_third_party(top_level):
                continue
            # Check if module exists on disk or can be resolved
            if not _module_exists(job_dir, mod, rel_path):
                unresolved.setdefault(rel_path, []).append(mod)

    valid = len(unresolved) == 0 and len(syntax_errors) == 0

    result: dict[str, Any] = {
        "valid": valid,
        "unresolved": unresolved,
        "syntax_errors": syntax_errors,
        "files_checked": len(all_imports),
        "details": "",
    }

    if not valid:
        parts = []
        if unresolved:
            parts.append(f"Unresolved imports: {sum(len(v) for v in unresolved.values())}")
        if syntax_errors:
            parts.append(f"Syntax errors: {len(syntax_errors)}")
        result["details"] = "; ".join(parts)

    return result


def auto_repair_imports(
    job_dir: Path,
    job_id: str,
    model: str = "local",
) -> dict[str, Any]:
    """Attempt to auto-repair import failures.

    Strategy:
      1. Create missing __init__.py for package directories
      2. Generate stub modules for missing local imports
      3. For complex failures, use LLM to generate missing module
      4. Re-validate after each repair

    Returns:
        {
            "success": bool,
            "repairs_applied": [str, ...],
            "remaining_issues": {file: [module, ...]},
            "attempts": int,
        }
    """
    log_to_db(job_id, "ImportRepair", "Starting import repair...")

    repairs_applied: list[str] = []
    remaining: dict[str, list[str]] = {}
    attempts = 0

    for attempt in range(1, MAX_REPAIR_ATTEMPTS + 1):
        attempts = attempt
        validation = validate_import_graph(job_dir, job_id)
        if validation["valid"]:
            log_to_db(job_id, "ImportRepair", f"Import graph clean after {attempt} repair(s)")
            return {
                "success": True,
                "repairs_applied": repairs_applied,
                "remaining_issues": {},
                "attempts": attempts,
            }

        unresolved = validation.get("unresolved", {})
        if not unresolved and not validation.get("syntax_errors"):
            log_to_db(job_id, "ImportRepair", "No unresolved imports to repair")
            break

        log_to_db(job_id, "ImportRepair",
                  f"Attempt {attempt}: {sum(len(v) for v in unresolved.values())} unresolved import(s)")

        # Phase 1: Create missing __init__.py files
        new_init = _create_missing_inits(job_dir, unresolved)
        repairs_applied.extend(new_init)

        # Phase 2: Generate stub modules for missing local imports
        new_stubs = _generate_stubs(job_dir, unresolved)
        repairs_applied.extend(new_stubs)

        # Phase 3: Use LLM for complex repairs
        if new_init or new_stubs:
            log_to_db(job_id, "ImportRepair", f"Repaired {len(new_init) + len(new_stubs)} import(s), re-validating...")
            continue

        # Phase 4: LLM-based repair for remaining issues
        llm_repairs = _llm_repair(job_dir, unresolved, job_id, model)
        repairs_applied.extend(llm_repairs)

    # Final check
    final = validate_import_graph(job_dir, job_id)
    remaining = final.get("unresolved", {})
    success = final["valid"]

    if success:
        log_to_db(job_id, "ImportRepair", f"Import repair successful after {attempts} attempt(s)")
    else:
        log_to_db(job_id, "ImportRepair",
                  f"Import repair incomplete: {sum(len(v) for v in remaining.values())} remaining", "WARNING")

    return {
        "success": success,
        "repairs_applied": repairs_applied,
        "remaining_issues": remaining,
        "attempts": attempts,
    }


def _module_exists(job_dir: Path, module_name: str, source_file: str) -> bool:
    """Check if a module exists relative to job_dir or is already installed."""
    # Check if it's a relative import (starts with .)
    if module_name.startswith("."):
        source_dir = (job_dir / source_file).parent
        parts = module_name.lstrip(".").split(".")
        depth = len(module_name) - len(parts[0]) - 1 if len(parts) > 0 else len(module_name) - len(module_name.lstrip("."))
        check_dir = source_dir
        for _ in range(depth):
            check_dir = check_dir.parent
        candidate = check_dir / "/".join(parts) if parts else check_dir
        return (candidate / "__init__.py").exists() or (candidate.with_name(candidate.name + ".py")).exists()

    # Absolute import — check relative to job_dir
    parts = module_name.split(".")
    candidate_py = job_dir / f"{'/'.join(parts)}.py"
    candidate_init = job_dir / "/".join(parts) / "__init__.py"

    if candidate_py.exists() or candidate_init.exists():
        return True

    # Check if it can be imported in subprocess
    try:
        result = subprocess.run(
            [sys.executable, "-c", f"import {module_name}"],
            capture_output=True, text=True, timeout=10,
            cwd=str(job_dir),
        )
        return result.returncode == 0
    except Exception:
        return False


def _is_known_third_party(name: str) -> bool:
    """Check if the top-level module is a known third-party package."""
    known = {
        "fastapi", "flask", "sqlalchemy", "pydantic", "uvicorn", "streamlit",
        "requests", "httpx", "pytest", "jose", "passlib", "bcrypt", "pyjwt",
        "cryptography", "dotenv", "aiofiles", "multipart", "pypdf", "altair",
        "pyflakes", "github", "git", "yaml", "jinja2", "markdown", "bs4",
        "lxml", "pillow", "numpy", "pandas", "redis", "celery", "docker",
        "boto3", "google", "anthropic", "openai", "chromadb", "sentence_transformers",
        "starlette", "click", "typer", "rich", "tqdm", "psutil",
    }
    return name in known


def _create_missing_inits(job_dir: Path, unresolved: dict[str, list[str]]) -> list[str]:
    """Create __init__.py for any directory that's missing it."""
    created = []
    for rel_path, modules in unresolved.items():
        source_dir = (job_dir / rel_path).parent
        # Ensure parent dirs have __init__.py
        current = source_dir
        while current != job_dir and job_dir in current.parents:
            init_file = current / "__init__.py"
            if not init_file.exists():
                try:
                    init_file.write_text("# auto-generated\n")
                    created.append(str(init_file.relative_to(job_dir)))
                except Exception:
                    pass
            current = current.parent
    return created


def _generate_stubs(job_dir: Path, unresolved: dict[str, list[str]]) -> list[str]:
    """Generate stub modules for missing local imports."""
    created = []
    processed = set()
    for rel_path, modules in unresolved.items():
        for mod in modules:
            if mod in processed:
                continue
            processed.add(mod)
            parts = mod.split(".")
            if len(parts) < 1:
                continue
            # Check if it's a submodule of the project
            stub_path = job_dir / f"{'/'.join(parts)}.py"
            init_path = job_dir / "/".join(parts[:-1]) / "__init__.py" if len(parts) > 1 else job_dir / "__init__.py"
            pkg_dir = job_dir / "/".join(parts)

            if stub_path.exists() or init_path.exists() or pkg_dir.exists():
                continue

            # Check if this looks like a missing internal module (not external)
            # External modules won't be stubbed
            source_dir = (job_dir / rel_path).parent if rel_path != "__init__.py" else job_dir
            rel_source = str(source_dir.relative_to(job_dir)) if source_dir != job_dir else ""
            if not mod.startswith(tuple(rel_source.split("/") if rel_source else [])):
                continue

            try:
                stub_path.parent.mkdir(parents=True, exist_ok=True)
                stub_path.write_text(f"# Auto-generated stub for {mod}\n")
                created.append(str(stub_path.relative_to(job_dir)))
            except Exception:
                pass
    return created


def _llm_repair(
    job_dir: Path,
    unresolved: dict[str, list[str]],
    job_id: str,
    model: str,
) -> list[str]:
    """Use LLM to fix import issues by generating missing modules."""
    created = []
    for rel_path, modules in unresolved.items():
        for mod in modules:
            if _module_exists(job_dir, mod, rel_path):
                continue
            # Try LLM to generate the missing module
            try:
                prompt = (
                    f"Generate a minimal Python module for '{mod}' that satisfies imports from '{rel_path}'. "
                    f"Output ONLY the complete module code — no markdown, no explanations."
                )
                content = call_model(prompt, model=model, job_id=job_id, agent="ImportRepair")
                content = content.strip().strip("`").strip()
                if content.startswith("python"):
                    content = content[6:].strip()

                parts = mod.split(".")
                if len(parts) > 1:
                    pkg_dir = job_dir / "/".join(parts[:-1])
                    pkg_dir.mkdir(parents=True, exist_ok=True)
                    init_file = pkg_dir / "__init__.py"
                    if not init_file.exists():
                        init_file.write_text("# auto-generated\n")
                        created.append(str(init_file.relative_to(job_dir)))
                    stub = pkg_dir / f"{parts[-1]}.py"
                else:
                    stub = job_dir / f"{mod}.py"

                if not stub.exists():
                    stub.write_text(content)
                    created.append(str(stub.relative_to(job_dir)))
                    log_to_db(job_id, "ImportRepair", f"LLM generated: {stub.relative_to(job_dir)}")
            except Exception as exc:
                logger.warning("LLM import repair failed for %s: %s", mod, exc)
    return created
