"""Documentation Generator routes — extracted from main.py."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/docs", tags=["Documentation"])


class DocsGenerateRequest(BaseModel):
    output_dir: str | None = None


@router.post("/generate")
async def docs_generate(req: DocsGenerateRequest):
    from services.docs_generator_service import generate_all

    result = generate_all(output_dir=req.output_dir)
    return {"generated": result}


@router.get("/status")
async def docs_status():
    from services.docs_generator_service import DOCS_DIR

    docs = []
    if DOCS_DIR.exists():
        for fp in sorted(DOCS_DIR.rglob("*.md")):
            docs.append(str(fp.relative_to(DOCS_DIR.parent)))
    return {"docs_dir": str(DOCS_DIR), "files": docs}