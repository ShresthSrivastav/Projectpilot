"""Organization routes — extracted from main.py."""

from fastapi import APIRouter, Body, HTTPException
from pydantic import Field
from pydantic import BaseModel

from database.memory_store import (
    delete_organization as mem_del_organization,
    delete_repository as mem_del_repository,
    delete_repositories_by_org,
    delete_impact_reports_by_org,
    delete_cross_repo_changes_by_org,
    delete_repository_relationships_by_org,
    save_impact_report as mem_save_impact_report,
    save_organization as mem_save_organization,
    save_repository as mem_save_repository,
    get_repository_relationships,
    save_repository_relationship,
    get_impact_reports as mem_get_impact_reports,
    get_impact_report_by_id as mem_get_impact_report,
    get_cross_repo_changes as mem_get_cross_repo_changes,
    save_cross_repo_change as mem_save_cross_repo_change,
)

router = APIRouter(prefix="/organization", tags=["Organization"])


class OrgCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = ""


class OrgAddRepoRequest(BaseModel):
    org_id: str
    name: str
    path: str
    category: str = ""
    language: str = ""
    url: str = ""
    description: str = ""


class OrgAnalyzeRequest(BaseModel):
    org_id: str
    model: str = "cloud"


class OrgImpactRequest(BaseModel):
    org_id: str
    query: str = Field(..., min_length=3, max_length=500)


class OrgModifyRequest(BaseModel):
    org_id: str
    description: str = Field(..., min_length=3, max_length=500)
    changes: dict[str, dict[str, str]]
    github_token: str = ""
    repo_full_names: dict[str, str] = {}


class OrgValidateRequest(BaseModel):
    org_id: str
    validation_types: list[str] | None = None


@router.post("/create")
async def organization_create(req: OrgCreateRequest):
    from services.org_graph_service import create_organization

    graph = create_organization(req.name, req.description)
    mem_save_organization(
        {
            "id": graph.org.id,
            "name": graph.org.name,
            "description": graph.org.description,
            "repo_count": 0,
            "entity_count": 0,
            "metadata": {},
            "created_at": graph.org.created_at,
            "updated_at": graph.org.updated_at,
        }
    )
    return {"organization_id": graph.org.id, "name": graph.org.name}


@router.post("/add-repo")
async def organization_add_repo(req: OrgAddRepoRequest):
    from services.org_graph_service import get_organization

    graph = get_organization(req.org_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Organization not found")
    repo = graph.add_repository(
        name=req.name,
        path=req.path,
        category=req.category,
        language=req.language,
        url=req.url,
        description=req.description,
    )
    mem_save_repository(
        {
            "id": repo.id,
            "org_id": req.org_id,
            "name": repo.name,
            "path": repo.path,
            "category": repo.category,
            "language": repo.language,
            "url": repo.url,
            "description": repo.description,
            "file_count": 0,
            "indexed_at": None,
            "metadata": {},
        }
    )
    return {"repository": repo.to_dict()}


@router.post("/index")
async def organization_index(req: OrgAnalyzeRequest):
    from services.org_graph_service import get_organization

    graph = get_organization(req.org_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Organization not found")
    results = {}
    for repo in graph.list_repositories():
        stats = graph.index_repository(repo.id)
        results[repo.name] = stats
    mem_save_organization(
        {
            "id": graph.org.id,
            "name": graph.org.name,
            "description": graph.org.description,
            "repo_count": len(graph.list_repositories()),
            "entity_count": len(graph.org.entities),
            "metadata": {},
            "created_at": graph.org.created_at,
            "updated_at": graph.org.updated_at,
        }
    )
    return {"organization_id": req.org_id, "index_results": results}


@router.get("/graph")
async def organization_graph(org_id: str):
    from services.org_graph_service import get_organization

    graph = get_organization(org_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Organization not found")
    return graph.get_graph_data()


@router.get("/repositories")
async def organization_repositories(org_id: str):
    from services.org_graph_service import get_organization

    graph = get_organization(org_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Organization not found")
    repos = [r.to_dict() for r in graph.list_repositories()]
    return {"repositories": repos}


@router.post("/analyze")
async def organization_analyze(req: OrgAnalyzeRequest):
    from services.org_graph_service import OrgGraphAnalyzer, get_organization

    graph = get_organization(req.org_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Organization not found")
    analyzer = OrgGraphAnalyzer(graph)
    return {
        "shared_dependencies": analyzer.find_shared_dependencies(),
        "orphan_repos": analyzer.find_orphan_repos(),
        "critical_path": analyzer.find_critical_path(),
    }


@router.post("/impact")
async def organization_impact(req: OrgImpactRequest):
    from services.org_graph_service import get_organization

    graph = get_organization(req.org_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Organization not found")
    report = graph.analyze_impact(req.query)
    mem_save_impact_report(
        {
            "id": report.id,
            "org_id": req.org_id,
            "query": report.query,
            "affected_repos": report.affected_repos,
            "affected_files": report.affected_files,
            "impact_score": report.impact_score,
            "risk_level": report.risk_level,
            "recommendations": report.recommendations,
            "report_markdown": report.report_markdown,
            "created_at": report.created_at,
        }
    )
    return report.to_dict()


@router.post("/modify")
async def organization_modify(req: OrgModifyRequest):
    from services.multi_repo_editor import get_multi_repo_editor
    from services.org_graph_service import get_organization

    graph = get_organization(req.org_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Organization not found")
    editor = get_multi_repo_editor(graph)
    cc = editor.plan_change(req.org_id, req.description, req.changes)
    result = editor.apply_changes(cc.id)
    if req.github_token and req.repo_full_names:
        result = editor.create_prs(cc.id, github_token=req.github_token, repo_full_names=req.repo_full_names)
    mem_save_cross_repo_change(result.to_dict())
    return result.to_dict()


@router.get("/report")
async def organization_report(org_id: str, report_id: str | None = None):
    if report_id:
        report = mem_get_impact_report(report_id)
        if not report:
            raise HTTPException(status_code=404, detail="Impact report not found")
        return report
    reports = mem_get_impact_reports(org_id)
    return {"impact_reports": reports}


@router.get("/changes")
async def organization_changes(org_id: str):
    changes = mem_get_cross_repo_changes(org_id)
    return {"changes": changes}


@router.get("/health")
async def organization_health(org_id: str):
    from services.org_graph_service import get_organization

    graph = get_organization(org_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Organization not found")
    return graph.get_health()


@router.post("/validate")
async def organization_validate(req: OrgValidateRequest):
    from services.cross_repo_validation import get_cross_repo_validator
    from services.org_graph_service import get_organization

    graph = get_organization(req.org_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Organization not found")
    validator = get_cross_repo_validator(graph)
    if req.validation_types:
        results = {}
        for vt in req.validation_types:
            method = getattr(validator, f"validate_{vt}", None)
            if method:
                results[vt] = method(req.org_id).to_dict()
    else:
        raw = validator.run_all_validations(req.org_id)
        results = {k: v.to_dict() for k, v in raw.items()}
    return {"org_id": req.org_id, "results": results}


@router.get("/list")
async def organization_list():
    from services.org_graph_service import list_organizations

    return {"organizations": list_organizations()}


@router.post("/dependency")
async def organization_add_dependency(
    org_id: str = Body(...),
    source_repo: str = Body(...),
    target_repo: str = Body(...),
    relationship: str = Body("depends_on"),
    weight: float = Body(1.0),
):
    from services.org_graph_service import get_organization

    graph = get_organization(org_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Organization not found")
    dep = graph.add_manual_dependency(source_repo, target_repo, relationship, weight)
    save_repository_relationship(
        {
            "id": dep.id,
            "org_id": org_id,
            "source_repo": dep.source_repo,
            "target_repo": dep.target_repo,
            "source_file": dep.source_file,
            "target_file": dep.target_file,
            "relationship": dep.relationship,
            "weight": dep.weight,
            "verified": dep.verified,
        }
    )
    return {"dependency": dep.to_dict()}


@router.get("/dependencies")
async def organization_dependencies(org_id: str):
    return {"dependencies": get_repository_relationships(org_id)}


@router.delete("/repo")
async def organization_delete_repo(org_id: str = Body(...), repo_id: str = Body(...)):
    from services.org_graph_service import get_organization

    graph = get_organization(org_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Organization not found")
    ok = graph.remove_repository(repo_id)
    mem_del_repository(repo_id)
    return {"deleted": ok}


@router.delete("/{org_id}")
async def organization_delete(org_id: str):
    from services.org_graph_service import get_organization

    graph = get_organization(org_id)
    if graph:
        graph._save()
    mem_del_organization(org_id)
    delete_repository_relationships_by_org(org_id)
    delete_impact_reports_by_org(org_id)
    delete_cross_repo_changes_by_org(org_id)
    delete_repositories_by_org(org_id)
    return {"deleted": True}
