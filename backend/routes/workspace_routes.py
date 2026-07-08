"""Workspace file management routes — extracted from main.py."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.file_service import BASE_DIR

router = APIRouter(prefix="/workspace", tags=["Workspace"])


def _resolve_job_path(job_id: str) -> Path:
    p = (BASE_DIR / job_id).resolve()
    if BASE_DIR.resolve() not in p.parents and p != BASE_DIR.resolve():
        raise HTTPException(status_code=403, detail="Invalid job_id.")
    return p


def _validate_file_path(base: Path, relative: str) -> Path:
    target = (base.resolve() / relative).resolve()
    try:
        target.relative_to(base.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Path traversal denied.")
    return target


class WorkspaceFileCreate(BaseModel):
    content: str


@router.post("/{job_id}/files/{path:path}")
async def workspace_create_file(job_id: str, path: str, req: WorkspaceFileCreate):
    job_dir = _resolve_job_path(job_id)
    full = _validate_file_path(job_dir, path)
    if full.exists():
        raise HTTPException(status_code=409, detail="File already exists. Use PUT to update.")
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(req.content, encoding="utf-8")
    return {"job_id": job_id, "path": path, "action": "created", "chars": len(req.content)}


@router.put("/{job_id}/files/{path:path}")
async def workspace_update_file(job_id: str, path: str, req: WorkspaceFileCreate):
    job_dir = _resolve_job_path(job_id)
    full = _validate_file_path(job_dir, path)
    if not full.exists():
        raise HTTPException(status_code=404, detail="File not found.")
    original = full.read_text(encoding="utf-8")
    full.write_text(req.content, encoding="utf-8")
    from difflib import unified_diff

    diff = list(
        unified_diff(
            original.splitlines(keepends=True),
            req.content.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )
    return {
        "job_id": job_id,
        "path": path,
        "action": "updated",
        "chars": len(req.content),
        "diff": "".join(diff[-1000:]),
    }


@router.delete("/{job_id}/files/{path:path}")
async def workspace_delete_file(job_id: str, path: str):
    job_dir = _resolve_job_path(job_id)
    full = _validate_file_path(job_dir, path)
    if not full.exists():
        raise HTTPException(status_code=404, detail="File not found.")
    full.unlink()
    return {"job_id": job_id, "path": path, "action": "deleted"}
