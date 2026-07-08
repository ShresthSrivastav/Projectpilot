import json
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Body, File, Form, HTTPException, Request, UploadFile

from backend.routes.helpers import RAG_UPLOAD_DIR

router = APIRouter(prefix="/rag", tags=["RAG"])


@router.post("/upload")
async def rag_upload(file: UploadFile = File(...), tags: str | None = Form(None), request: Request = None):
    from services.rag_service import upload_document

    ws_id = getattr(request.state, "workspace_id", "") if request else ""
    uid = getattr(request.state, "user_id", "") if request else ""
    if file.filename:
        safe_name = Path(file.filename).name
    else:
        safe_name = f"upload_{uuid.uuid4().hex[:8]}"
    MAX_SIZE = 50 * 1024 * 1024
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 50 MB).")
    RAG_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    save_path = RAG_UPLOAD_DIR / safe_name
    save_path.write_bytes(content)
    tag_list = json.loads(tags) if tags else []
    result = upload_document(save_path, tags=tag_list, workspace_id=ws_id, uploaded_by=uid)
    os.remove(str(save_path))
    return result


@router.post("/query")
async def rag_query(
    text: str = Body(..., embed=True),
    top_k: int = Body(5, embed=True),
    tags: list[str] | None = Body(None, embed=True),
    request: Request = None,
):
    from services.rag_service import query

    ws_id = getattr(request.state, "workspace_id", "") if request else ""
    results = query(text, top_k=top_k, tags=tags, workspace_id=ws_id)
    return {"results": results}


@router.get("/list")
async def rag_list(request: Request = None):
    from services.rag_service import list_documents

    ws_id = getattr(request.state, "workspace_id", "") if request else ""
    return {"documents": list_documents(workspace_id=ws_id)}


@router.delete("/{doc_id}")
async def rag_delete(doc_id: str, request: Request = None):
    from services.rag_service import delete_document

    ws_id = getattr(request.state, "workspace_id", "") if request else ""
    ok = delete_document(doc_id, workspace_id=ws_id)
    return {"deleted": ok}
