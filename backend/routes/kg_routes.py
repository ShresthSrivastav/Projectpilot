"""Knowledge Graph routes — extracted from main.py."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/kg", tags=["Knowledge Graph"])


class KGRequest(BaseModel):
    repo_path: str


class KGAnalyzeRequest(BaseModel):
    repo_path: str
    file_pattern: str | None = None


class KGImpactRequest(BaseModel):
    repo_path: str
    changed_files: list[str]


@router.post("/build")
async def kg_build(req: KGRequest):
    from services.knowledge_graph import build_knowledge_graph

    try:
        kg = build_knowledge_graph(req.repo_path)
        return {
            "file_count": len(kg.files),
            "relationship_count": len(kg.relationships),
            "summary": kg.get_architecture_summary(),
            "graph_id": id(kg),
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/impact")
async def kg_impact(req: KGImpactRequest):
    from services.knowledge_graph import build_knowledge_graph

    try:
        kg = build_knowledge_graph(req.repo_path)
        result = kg.impact_analysis(req.changed_files)
        return {
            "affected_files": result.affected_files,
            "impact_score": result.impact_score,
            "breaking_changes": result.breaking_changes,
            "recommendations": result.recommendations,
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/query")
async def kg_query(req: KGAnalyzeRequest):
    from services.knowledge_graph import build_knowledge_graph

    try:
        kg = build_knowledge_graph(req.repo_path)
        return {
            "apis": kg.query_apis(),
            "dependency_graph": kg.query_dependency_graph(module=req.file_pattern),
            "service_deps": kg.query_service_dependencies(),
            "test_mappings": kg.query_test_mappings(),
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/visualize")
async def kg_visualize(req: KGRequest):
    from services.knowledge_graph import build_knowledge_graph

    try:
        kg = build_knowledge_graph(req.repo_path)
        return {"mermaid": kg.visualize_mermaid(), "summary": kg.get_architecture_summary()}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/architecture")
async def kg_architecture(req: KGRequest):
    from services.knowledge_graph import build_knowledge_graph

    try:
        kg = build_knowledge_graph(req.repo_path)
        return kg.get_architecture_summary()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))