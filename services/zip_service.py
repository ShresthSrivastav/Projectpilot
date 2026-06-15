"""ZIP service — packages generated project into downloadable ZIP."""
import logging, os, shutil
from pathlib import Path

logger = logging.getLogger(__name__)
BASE_DIR = Path(os.getenv("GENERATED_PROJECTS_DIR", "./generated_projects"))

def create_zip(job_id: str) -> Path:
    job_dir = BASE_DIR / job_id
    if not job_dir.exists(): raise FileNotFoundError(f"Job directory not found: {job_dir}")
    try:
        shutil.make_archive(str(BASE_DIR / job_id), "zip", str(BASE_DIR), job_id)
        logger.info("ZIP created: %s", BASE_DIR / f"{job_id}.zip")
    except Exception as exc:
        raise RuntimeError(f"Failed to create ZIP: {exc}") from exc
    return BASE_DIR / f"{job_id}.zip"

def get_zip_path(job_id: str) -> Path: return BASE_DIR / f"{job_id}.zip"
def zip_exists(job_id: str) -> bool: return get_zip_path(job_id).exists()
