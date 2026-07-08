from fastapi import APIRouter, HTTPException

from database.chroma_db import get_blueprint, get_job

router = APIRouter(prefix="/diagram", tags=["Diagrams"])


@router.get("/{job_id}")
async def get_diagram(job_id: str):
    from services.diagram_service import generate_architecture_markdown

    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    bp = get_blueprint(job_id) or {}
    if not bp:
        bp = {"files": [], "routes": [], "db_tables": [], "tech_stack": {}, "dependencies": []}
    agents = [
        "RequirementAgent",
        "PlannerAgent",
        "CodeAgent",
        "TestGenAgent",
        "DebugAgent",
        "DocsAgent",
        "ValidationAgent",
        "ZipService",
    ]
    md = generate_architecture_markdown(bp, agents)
    return {"diagram_markdown": md, "job_id": job_id}


@router.get("/{job_id}/component")
async def get_component_diagram(job_id: str):
    from services.diagram_service import generate_component_diagram

    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    bp = get_blueprint(job_id) or {
        "files": [],
        "routes": [],
        "db_tables": [],
        "tech_stack": {"backend": "FastAPI", "frontend": "Streamlit", "db": "SQLite"},
    }
    return {"mermaid": generate_component_diagram(bp), "job_id": job_id}


@router.get("/{job_id}/er")
async def get_er_diagram(job_id: str):
    from services.diagram_service import generate_er_diagram

    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    bp = get_blueprint(job_id) or {"files": [], "routes": [], "db_tables": [], "tech_stack": {}}
    return {"mermaid": generate_er_diagram(bp), "job_id": job_id}
