"""File service — manages generated_projects directory."""
import logging, os
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)
BASE_DIR = Path(os.getenv("GENERATED_PROJECTS_DIR", "./generated_projects"))

def _ensure_base_dir(): BASE_DIR.mkdir(parents=True, exist_ok=True)

def _resolve_path(job_id: str, relative_path: str = "") -> Path:
    job_dir = (BASE_DIR / job_id).resolve()
    if BASE_DIR.resolve() not in job_dir.parents and job_dir != BASE_DIR.resolve():
        raise ValueError(f"Invalid job_id: {job_id}")
    if not relative_path:
        return job_dir
    target = (job_dir / relative_path).resolve()
    try:
        target.relative_to(job_dir)
    except ValueError:
        raise ValueError(f"Path traversal denied: {relative_path}")
    return target

def create_job_directory(job_id: str) -> Path:
    _ensure_base_dir()
    d = _resolve_path(job_id)
    d.mkdir(parents=True, exist_ok=True)
    logger.info("Created job directory: %s", d); return d

def write_file(job_id: str, relative_path: str, content: str) -> Path:
    t = _resolve_path(job_id, relative_path)
    t.parent.mkdir(parents=True, exist_ok=True)
    t.write_text(content, encoding="utf-8"); return t

def read_file(job_id: str, relative_path: str) -> str:
    t = _resolve_path(job_id, relative_path)
    if not t.exists(): raise FileNotFoundError(f"File not found: {t}")
    return t.read_text(encoding="utf-8")

def list_files(job_id: str) -> List[Path]:
    d = _resolve_path(job_id)
    if not d.exists():
        return []
    resolved_base = d.resolve()
    return [p.resolve() for p in resolved_base.rglob("*") if p.is_file()]

def get_job_dir(job_id: str) -> Path: return _resolve_path(job_id)
