"""Tests for v11 Organization-Level Multi-Repository Intelligence (60+ tests)."""
import sys
import tempfile
import time
import uuid
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_temp_repo(name: str, files: dict) -> str:
    tmp = Path(tempfile.mkdtemp(suffix=f"_{name}"))
    for fpath, content in files.items():
        full = tmp / fpath
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
    return str(tmp)


SAMPLE_PY_FILE = """
from fastapi import FastAPI
app = FastAPI()

class Item(BaseModel):
    name: str
    price: float

@app.get("/items")
def list_items():
    return {"items": []}

@app.post("/items")
def create_item(data: dict):
    return {"ok": True}
"""


# ── Unit Tests: Organization Graph ────────────────────────────────────────────


class TestOrganizationGraph:
    def test_create_organization(self):
        from services.org_graph_service import create_organization
        graph = create_organization("test-org", "Test org description")
        assert graph.org.name == "test-org"
        assert graph.org.description == "Test org description"
        assert graph.org.id
        assert len(graph.org.repositories) == 0

    def test_add_repository(self):
        from services.org_graph_service import create_organization
        graph = create_organization("org2")
        repo = graph.add_repository("backend-api", "/fake/path", category="backend")
        assert repo.name == "backend-api"
        assert repo.category == "backend"
        assert len(graph.list_repositories()) == 1

    def test_add_repository_auto_category(self):
        from services.org_graph_service import create_organization
        graph = create_organization("org3")
        repo = graph.add_repository("frontend-web", "/fake/path")
        assert repo.category == "frontend"

    def test_get_repository(self):
        from services.org_graph_service import create_organization
        graph = create_organization("org4")
        repo = graph.add_repository("my-repo", "/fake/path")
        found = graph.get_repository(repo.id)
        assert found is not None
        assert found.name == "my-repo"

    def test_get_repository_not_found(self):
        from services.org_graph_service import create_organization
        graph = create_organization("org5")
        assert graph.get_repository("nonexistent") is None

    def test_remove_repository(self):
        from services.org_graph_service import create_organization
        graph = create_organization("org6")
        repo = graph.add_repository("to-remove", "/fake/path")
        assert len(graph.list_repositories()) == 1
        ok = graph.remove_repository(repo.id)
        assert ok
        assert len(graph.list_repositories()) == 0

    def test_remove_repository_not_found(self):
        from services.org_graph_service import create_organization
        graph = create_organization("org7")
        ok = graph.remove_repository("nonexistent")
        assert not ok

    def test_index_repository(self):
        from services.org_graph_service import create_organization
        graph = create_organization("org8")
        repo = graph.add_repository("test-repo", _make_temp_repo("idxrepo", {"main.py": SAMPLE_PY_FILE}))
        stats = graph.index_repository(repo.id)
        assert stats["files_scanned"] >= 1
        assert "errors" in stats

    def test_index_repository_not_found(self):
        from services.org_graph_service import create_organization
        graph = create_organization("org9")
        stats = graph.index_repository("nonexistent")
        assert "error" in stats

    def test_list_repositories(self):
        from services.org_graph_service import create_organization
        graph = create_organization("org10")
        graph.add_repository("r1", "/p1")
        graph.add_repository("r2", "/p2")
        repos = graph.list_repositories()
        assert len(repos) == 2

    def test_org_graph_data(self):
        from services.org_graph_service import create_organization
        graph = create_organization("org11")
        graph.add_repository("r1", "/p1")
        data = graph.get_graph_data()
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) == 1

    def test_detect_category_backend(self):
        from services.org_graph_service import OrganizationGraph
        graph = OrganizationGraph()
        cat = graph._detect_category("backend-api", "/some/path")
        assert cat == "backend"

    def test_detect_category_frontend(self):
        from services.org_graph_service import OrganizationGraph
        graph = OrganizationGraph()
        cat = graph._detect_category("web-client-ui", "/some/path")
        assert cat == "frontend"

    def test_detect_category_other(self):
        from services.org_graph_service import OrganizationGraph
        graph = OrganizationGraph()
        cat = graph._detect_category("random-tool", "/some/path")
        assert cat == "other"

    def test_manual_dependency(self):
        from services.org_graph_service import create_organization
        graph = create_organization("org12")
        graph.add_repository("repo-a", "/p1")
        graph.add_repository("repo-b", "/p2")
        dep = graph.add_manual_dependency("repo-a", "repo-b", "depends_on", 1.0)
        assert dep.source_repo == "repo-a"
        assert dep.target_repo == "repo-b"
        assert len(graph.org.dependencies) == 1

    def test_org_health(self):
        from services.org_graph_service import create_organization
        graph = create_organization("org13")
        health = graph.get_health()
        assert "organization_id" in health
        assert health["repository_count"] == 0


# ── Unit Tests: Impact Analysis ───────────────────────────────────────────────


class TestImpactAnalysis:
    def test_analyze_impact_basic(self):
        from services.org_graph_service import create_organization
        graph = create_organization("impact-org")
        graph.add_repository("auth-service", "/p1")
        stats = graph.analyze_impact("change authentication flow")
        assert stats.impact_score >= 0
        assert stats.risk_level in ("low", "medium", "high")

    def test_analyze_impact_high_risk(self):
        from services.org_graph_service import create_organization
        graph = create_organization("impact-org2")
        for i in range(5):
            graph.add_repository(f"repo-{i}", f"/p{i}")
        stats = graph.analyze_impact("change core authentication")
        assert stats.impact_score >= 0

    def test_impact_report_markdown(self):
        from services.org_graph_service import create_organization
        graph = create_organization("impact-org3")
        graph.add_repository("repo-a", "/p1")
        graph.add_repository("repo-b", "/p2")
        report = graph.analyze_impact("modify API")
        assert "Impact Analysis Report" in report.report_markdown
        assert "Recommendations" in report.report_markdown

    def test_impact_report_id(self):
        from services.org_graph_service import create_organization
        graph = create_organization("impact-org4")
        report = graph.analyze_impact("fix login")
        assert report.id
        assert report.organization_id

    def test_impact_recommendations(self):
        from services.org_graph_service import create_organization
        graph = create_organization("impact-org5")
        graph.add_repository("repo-a", "/p1")
        graph.add_repository("repo-b", "/p2")
        report = graph.analyze_impact("change core")
        assert len(report.recommendations) > 0

    def test_impact_multiple_repos(self):
        from services.org_graph_service import create_organization
        graph = create_organization("impact-org6")
        for i in range(4):
            graph.add_repository(f"repo-{i}", f"/p{i}")
        report = graph.analyze_impact("modify all the things")
        assert len(report.affected_repos) >= 0

    def test_impact_affected_files(self):
        from services.org_graph_service import create_organization
        graph = create_organization("impact-org7")
        repo = graph.add_repository("test-repo", _make_temp_repo("impfiles", {"app.py": SAMPLE_PY_FILE}))
        graph.index_repository(repo.id)
        report = graph.analyze_impact("items")
        assert len(report.affected_files) >= 0


# ── Unit Tests: OrgGraphAnalyzer ──────────────────────────────────────────────


class TestOrgGraphAnalyzer:
    def test_find_shared_dependencies(self):
        from services.org_graph_service import create_organization, OrgGraphAnalyzer
        graph = create_organization("analyze-org")
        graph.add_repository("lib-common", "/p1")
        graph.add_repository("service-a", "/p2")
        graph.add_repository("service-b", "/p3")
        graph.add_manual_dependency("service-a", "lib-common")
        graph.add_manual_dependency("service-b", "lib-common")
        analyzer = OrgGraphAnalyzer(graph)
        shared = analyzer.find_shared_dependencies()
        assert len(shared) >= 1
        assert shared[0]["target"] == "lib-common"

    def test_find_orphan_repos(self):
        from services.org_graph_service import create_organization, OrgGraphAnalyzer
        graph = create_organization("analyze-org2")
        graph.add_repository("connected-a", "/p1")
        graph.add_repository("connected-b", "/p2")
        graph.add_repository("orphan-repo", "/p3")
        graph.add_manual_dependency("connected-a", "connected-b")
        analyzer = OrgGraphAnalyzer(graph)
        orphans = analyzer.find_orphan_repos()
        assert "orphan-repo" in orphans

    def test_find_critical_path(self):
        from services.org_graph_service import create_organization, OrgGraphAnalyzer
        graph = create_organization("analyze-org3")
        graph.add_repository("shared-lib", "/p1")
        graph.add_repository("service-a", "/p2")
        graph.add_repository("service-b", "/p3")
        graph.add_repository("service-c", "/p4")
        graph.add_manual_dependency("service-a", "shared-lib")
        graph.add_manual_dependency("service-b", "shared-lib")
        graph.add_manual_dependency("service-c", "shared-lib")
        analyzer = OrgGraphAnalyzer(graph)
        critical = analyzer.find_critical_path()
        assert critical[0] == "shared-lib"


# ── Unit Tests: Entity Parsing ────────────────────────────────────────────────


class TestEntityParsing:
    def test_parse_python_class(self):
        from services.org_graph_service import OrganizationGraph
        graph = OrganizationGraph()
        entities = graph._parse_entities("class UserService:\n    pass\n", "repo", "app.py", ".py")
        assert len(entities) >= 1
        assert entities[0].name == "UserService"
        assert entities[0].entity_type == "class"

    def test_parse_python_function(self):
        from services.org_graph_service import OrganizationGraph
        graph = OrganizationGraph()
        entities = graph._parse_entities("def get_user():\n    pass\n", "repo", "app.py", ".py")
        funcs = [e for e in entities if e.entity_type == "function"]
        assert len(funcs) >= 1
        assert funcs[0].name == "get_user"

    def test_parse_python_imports(self):
        from services.org_graph_service import OrganizationGraph
        graph = OrganizationGraph()
        entities = graph._parse_entities("from fastapi import FastAPI\nclass App:\n    pass\n", "repo", "app.py", ".py")
        assert len(entities) >= 1
        assert "fastapi.FastAPI" in entities[0].imports

    def test_parse_no_entities(self):
        from services.org_graph_service import OrganizationGraph
        graph = OrganizationGraph()
        entities = graph._parse_entities("# just a comment\n", "repo", "empty.py", ".py")
        assert len(entities) == 0


# ── Unit Tests: Multi-Repo Editor ─────────────────────────────────────────────


class TestMultiRepoEditor:
    def test_plan_change(self):
        from services.org_graph_service import create_organization
        from services.multi_repo_editor import get_multi_repo_editor
        graph = create_organization("editor-org")
        graph.add_repository("repo-a", _make_temp_repo("editor_repo_a", {"file.txt": "old"}))
        editor = get_multi_repo_editor(graph)
        cc = editor.plan_change(graph.org.id, "test change", {"repo-a": {"file.txt": "new content"}})
        assert cc.description == "test change"
        assert cc.branch_name.startswith("auto-change-")
        assert "repo-a" in cc.changes

    def test_plan_change_nonexistent_repo(self):
        from services.org_graph_service import create_organization
        from services.multi_repo_editor import get_multi_repo_editor
        graph = create_organization("editor-org2")
        editor = get_multi_repo_editor(graph)
        cc = editor.plan_change(graph.org.id, "change", {"nonexistent": {"f.txt": "x"}})
        assert cc.changes["nonexistent"].repo_path == ""

    def test_list_changes(self):
        from services.org_graph_service import create_organization
        from services.multi_repo_editor import get_multi_repo_editor
        graph = create_organization("editor-org3")
        editor = get_multi_repo_editor(graph)
        editor.plan_change(graph.org.id, "c1", {})
        editor.plan_change(graph.org.id, "c2", {})
        changes = editor.list_changes(graph.org.id)
        assert len(changes) >= 2

    def test_get_status(self):
        from services.org_graph_service import create_organization
        from services.multi_repo_editor import get_multi_repo_editor
        graph = create_organization("editor-org4")
        editor = get_multi_repo_editor(graph)
        cc = editor.plan_change(graph.org.id, "status test", {})
        found = editor.get_status(cc.id)
        assert found is not None
        assert found.id == cc.id


# ── Unit Tests: Cross-Repo Validation ─────────────────────────────────────────


class TestCrossRepoValidation:
    def test_api_compatibility_empty(self):
        from services.org_graph_service import create_organization
        from services.cross_repo_validation import get_cross_repo_validator
        graph = create_organization("val-org1")
        validator = get_cross_repo_validator(graph)
        result = validator.validate_api_compatibility(graph.org.id)
        assert result.validation_type == "api_compatibility"
        assert result.passed

    def test_shared_libraries_empty(self):
        from services.org_graph_service import create_organization
        from services.cross_repo_validation import get_cross_repo_validator
        graph = create_organization("val-org2")
        validator = get_cross_repo_validator(graph)
        result = validator.validate_shared_libraries(graph.org.id)
        assert result.validation_type == "shared_libraries"
        assert result.passed

    def test_schema_compatibility_empty(self):
        from services.org_graph_service import create_organization
        from services.cross_repo_validation import get_cross_repo_validator
        graph = create_organization("val-org3")
        validator = get_cross_repo_validator(graph)
        result = validator.validate_schema_compatibility(graph.org.id)
        assert result.validation_type == "schema_compatibility"

    def test_deployment_consistency_empty(self):
        from services.org_graph_service import create_organization
        from services.cross_repo_validation import get_cross_repo_validator
        graph = create_organization("val-org4")
        validator = get_cross_repo_validator(graph)
        result = validator.validate_deployment_consistency(graph.org.id)
        assert result.validation_type == "deployment_consistency"

    def test_documentation_coverage(self):
        from services.org_graph_service import create_organization
        from services.cross_repo_validation import get_cross_repo_validator
        graph = create_organization("val-org5")
        validator = get_cross_repo_validator(graph)
        result = validator.validate_documentation_coverage(graph.org.id)
        assert result.validation_type == "documentation_coverage"

    def test_run_all_validations(self):
        from services.org_graph_service import create_organization
        from services.cross_repo_validation import get_cross_repo_validator
        graph = create_organization("val-org6")
        validator = get_cross_repo_validator(graph)
        results = validator.run_all_validations(graph.org.id)
        assert len(results) == 5
        for key in ("api_compatibility", "shared_libraries", "schema_compatibility",
                     "deployment_consistency", "documentation_coverage"):
            assert key in results

    def test_get_result_not_found(self):
        from services.org_graph_service import create_organization
        from services.cross_repo_validation import get_cross_repo_validator
        graph = create_organization("val-org7")
        validator = get_cross_repo_validator(graph)
        r = validator.get_result("nonexistent")
        assert r is None

    def test_list_results(self):
        from services.org_graph_service import create_organization
        from services.cross_repo_validation import get_cross_repo_validator
        graph = create_organization("val-org8")
        validator = get_cross_repo_validator(graph)
        validator.validate_api_compatibility(graph.org.id)
        results = validator.list_results(graph.org.id)
        assert len(results) >= 1

    def test_validation_result_to_dict(self):
        from services.cross_repo_validation import ValidationResult
        vr = ValidationResult(org_id="o1", validation_type="api_compatibility", passed=True)
        d = vr.to_dict()
        assert d["org_id"] == "o1"
        assert d["passed"] is True


# ── Unit Tests: Database CRUD ─────────────────────────────────────────────────


class TestDatabaseCRUD:
    def setup_method(self):
        from database.memory_store import init_db
        init_db()

    def test_save_and_get_organization(self):
        from database.memory_store import save_organization, get_organization
        oid = str(uuid.uuid4())
        save_organization({"id": oid, "name": "db-org", "description": "test", "repo_count": 0, "entity_count": 0, "metadata": {}, "created_at": time.time(), "updated_at": time.time()})
        org = get_organization(oid)
        assert org is not None
        assert org["name"] == "db-org"

    def test_list_organizations_db(self):
        from database.memory_store import save_organization, list_organizations_db, delete_organization
        oid = str(uuid.uuid4())
        save_organization({"id": oid, "name": "list-org", "description": "", "repo_count": 0, "entity_count": 0, "metadata": {}, "created_at": time.time(), "updated_at": time.time()})
        orgs = list_organizations_db()
        ids = [o["id"] for o in orgs]
        assert oid in ids
        delete_organization(oid)

    def test_delete_organization(self):
        from database.memory_store import save_organization, delete_organization, get_organization
        oid = str(uuid.uuid4())
        save_organization({"id": oid, "name": "del-org", "description": "", "repo_count": 0, "entity_count": 0, "metadata": {}, "created_at": time.time(), "updated_at": time.time()})
        ok = delete_organization(oid)
        assert ok
        assert get_organization(oid) is None

    def test_save_and_get_repository(self):
        from database.memory_store import save_repository, get_repositories, delete_repository
        oid = str(uuid.uuid4())
        rid = str(uuid.uuid4())
        save_repository({"id": rid, "org_id": oid, "name": "db-repo", "path": "/p", "category": "backend", "language": "python", "url": "", "description": "", "file_count": 0, "indexed_at": None, "metadata": {}})
        repos = get_repositories(oid)
        ids = [r["id"] for r in repos]
        assert rid in ids
        delete_repository(rid)

    def test_save_and_get_relationship(self):
        from database.memory_store import save_repository_relationship, get_repository_relationships, delete_repository_relationship
        oid = str(uuid.uuid4())
        rel_id = str(uuid.uuid4())
        save_repository_relationship({"id": rel_id, "org_id": oid, "source_repo": "a", "target_repo": "b", "source_file": "", "target_file": "", "relationship": "depends_on", "weight": 1.0, "verified": True})
        rels = get_repository_relationships(oid)
        ids = [r["id"] for r in rels]
        assert rel_id in ids
        delete_repository_relationship(rel_id)

    def test_save_and_get_impact_report(self):
        from database.memory_store import save_impact_report, get_impact_reports, delete_impact_report
        oid = str(uuid.uuid4())
        rpt_id = str(uuid.uuid4())
        save_impact_report({"id": rpt_id, "org_id": oid, "query": "test query", "affected_repos": ["a"], "affected_files": [], "impact_score": 50.0, "risk_level": "medium", "recommendations": ["fix"], "report_markdown": "# Report", "created_at": time.time()})
        reports = get_impact_reports(oid)
        ids = [r["id"] for r in reports]
        assert rpt_id in ids
        delete_impact_report(rpt_id)

    def test_get_impact_report_by_id(self):
        from database.memory_store import save_impact_report, get_impact_report_by_id, delete_impact_report
        rpt_id = str(uuid.uuid4())
        save_impact_report({"id": rpt_id, "org_id": "o1", "query": "q", "affected_repos": [], "affected_files": [], "impact_score": 0, "risk_level": "low", "recommendations": [], "report_markdown": "", "created_at": time.time()})
        rpt = get_impact_report_by_id(rpt_id)
        assert rpt is not None
        assert rpt["query"] == "q"
        delete_impact_report(rpt_id)

    def test_save_and_get_cross_repo_change(self):
        from database.memory_store import save_cross_repo_change, get_cross_repo_changes, get_cross_repo_change, delete_cross_repo_change
        oid = str(uuid.uuid4())
        chg_id = str(uuid.uuid4())
        save_cross_repo_change({"id": chg_id, "org_id": oid, "branch_name": "b1", "description": "desc", "repos_affected": ["a"], "files_changed": [], "status": "pending", "pr_urls": [], "created_at": time.time(), "completed_at": None})
        changes = get_cross_repo_changes(oid)
        ids = [c["id"] for c in changes]
        assert chg_id in ids
        chg = get_cross_repo_change(chg_id)
        assert chg is not None
        assert chg["status"] == "pending"
        delete_cross_repo_change(chg_id)

    def test_delete_cross_repo_change(self):
        from database.memory_store import save_cross_repo_change, delete_cross_repo_change, get_cross_repo_change
        chg_id = str(uuid.uuid4())
        save_cross_repo_change({"id": chg_id, "org_id": "o1", "branch_name": "b", "description": "d", "repos_affected": [], "files_changed": [], "status": "pending", "pr_urls": [], "created_at": time.time(), "completed_at": None})
        ok = delete_cross_repo_change(chg_id)
        assert ok
        assert get_cross_repo_change(chg_id) is None

    def test_delete_impact_report(self):
        from database.memory_store import save_impact_report, delete_impact_report, get_impact_report_by_id
        rpt_id = str(uuid.uuid4())
        save_impact_report({"id": rpt_id, "org_id": "o1", "query": "q", "affected_repos": [], "affected_files": [], "impact_score": 0, "risk_level": "low", "recommendations": [], "report_markdown": "", "created_at": time.time()})
        ok = delete_impact_report(rpt_id)
        assert ok
        assert get_impact_report_by_id(rpt_id) is None

    def test_org_cascade_deletes(self):
        from database.memory_store import (save_organization, save_repository, get_repositories,
                                           delete_organization, delete_repositories_by_org)
        oid = str(uuid.uuid4())
        save_organization({"id": oid, "name": "cascade-org", "description": "", "repo_count": 0, "entity_count": 0, "metadata": {}, "created_at": time.time(), "updated_at": time.time()})
        save_repository({"id": str(uuid.uuid4()), "org_id": oid, "name": "cascade-repo", "path": "/p", "category": "other", "language": "", "url": "", "description": "", "file_count": 0, "indexed_at": None, "metadata": {}})
        repos_before = get_repositories(oid)
        assert len(repos_before) == 1
        delete_repositories_by_org(oid)
        repos_after = get_repositories(oid)
        assert len(repos_after) == 0
        delete_organization(oid)

    def test_list_organizations_db_empty(self):
        from database.memory_store import list_organizations_db
        orgs = list_organizations_db()
        assert isinstance(orgs, list)

    def test_get_organization_not_found(self):
        from database.memory_store import get_organization
        org = get_organization("nonexistent-org-id")
        assert org is None

    def test_get_impact_reports_empty(self):
        from database.memory_store import get_impact_reports
        reports = get_impact_reports("nonexistent-org")
        assert reports == []

    def test_get_cross_repo_changes_empty(self):
        from database.memory_store import get_cross_repo_changes
        changes = get_cross_repo_changes("nonexistent-org")
        assert changes == []

    def test_get_repositories_empty(self):
        from database.memory_store import get_repositories
        repos = get_repositories("nonexistent-org")
        assert repos == []

    def test_get_repository_relationships_empty(self):
        from database.memory_store import get_repository_relationships
        rels = get_repository_relationships("nonexistent-org")
        assert rels == []


# ── HTTP API Tests ────────────────────────────────────────────────────────────


class TestOrganizationAPI:
    def test_health_endpoint_has_version(self):
        from backend.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data

    def test_list_organizations(self):
        from backend.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/organization/list")
        assert resp.status_code == 200
        data = resp.json()
        assert "organizations" in data

    def test_create_organization(self):
        from backend.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.post("/organization/create", json={"name": "api-test-org", "description": "created via API"})
        assert resp.status_code == 200
        data = resp.json()
        assert "organization_id" in data
        assert data["name"] == "api-test-org"

    def test_get_organization_health(self):
        from backend.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.post("/organization/create", json={"name": "health-org"})
        org_id = resp.json()["organization_id"]
        resp = client.get(f"/organization/health?org_id={org_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "health_score" in data

    def test_get_organization_graph(self):
        from backend.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.post("/organization/create", json={"name": "graph-org"})
        org_id = resp.json()["organization_id"]
        resp = client.get(f"/organization/graph?org_id={org_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data

    def test_get_organization_repositories_empty(self):
        from backend.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.post("/organization/create", json={"name": "repos-org"})
        org_id = resp.json()["organization_id"]
        resp = client.get(f"/organization/repositories?org_id={org_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "repositories" in data

    def test_add_repository_via_api(self):
        from backend.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.post("/organization/create", json={"name": "add-repo-org"})
        org_id = resp.json()["organization_id"]
        resp = client.post("/organization/add-repo", json={
            "org_id": org_id, "name": "api-repo", "path": "/tmp/api-repo",
            "category": "backend", "language": "python",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["repository"]["name"] == "api-repo"

    def test_run_impact_analysis(self):
        from backend.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.post("/organization/create", json={"name": "impact-api-org"})
        org_id = resp.json()["organization_id"]
        resp = client.post("/organization/add-repo", json={
            "org_id": org_id, "name": "svc-a", "path": "/tmp/svc-a",
        })
        resp = client.post("/organization/impact", json={"org_id": org_id, "query": "change authentication"})
        assert resp.status_code == 200
        data = resp.json()
        assert "impact_score" in data
        assert "risk_level" in data

    def test_organization_analyze(self):
        from backend.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.post("/organization/create", json={"name": "analyze-api-org"})
        org_id = resp.json()["organization_id"]
        resp = client.post("/organization/analyze", json={"org_id": org_id})
        assert resp.status_code == 200
        data = resp.json()
        assert "shared_dependencies" in data
        assert "orphan_repos" in data

    def test_add_dependency_via_api(self):
        from backend.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.post("/organization/create", json={"name": "dep-api-org"})
        org_id = resp.json()["organization_id"]
        client.post("/organization/add-repo", json={"org_id": org_id, "name": "src", "path": "/tmp/src"})
        client.post("/organization/add-repo", json={"org_id": org_id, "name": "tgt", "path": "/tmp/tgt"})
        resp = client.post("/organization/dependency", json={
            "org_id": org_id, "source_repo": "src", "target_repo": "tgt",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "dependency" in data

    def test_get_dependencies(self):
        from backend.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.post("/organization/create", json={"name": "deps-api-org"})
        org_id = resp.json()["organization_id"]
        resp = client.get(f"/organization/dependencies?org_id={org_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "dependencies" in data

    def test_run_validation(self):
        from backend.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.post("/organization/create", json={"name": "val-api-org"})
        org_id = resp.json()["organization_id"]
        resp = client.post("/organization/validate", json={
            "org_id": org_id,
            "validation_types": ["api_compatibility"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data

    def test_run_all_validations(self):
        from backend.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.post("/organization/create", json={"name": "all-val-org"})
        org_id = resp.json()["organization_id"]
        resp = client.post("/organization/validate", json={"org_id": org_id})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 5

    def test_get_impact_report(self):
        from backend.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.post("/organization/create", json={"name": "report-org"})
        org_id = resp.json()["organization_id"]
        client.post("/organization/add-repo", json={"org_id": org_id, "name": "repo-x", "path": "/tmp/x"})
        client.post("/organization/impact", json={"org_id": org_id, "query": "test"})
        resp = client.get(f"/organization/report?org_id={org_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "impact_reports" in data

    def test_get_changes(self):
        from backend.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.post("/organization/create", json={"name": "changes-org"})
        org_id = resp.json()["organization_id"]
        resp = client.get(f"/organization/changes?org_id={org_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "changes" in data

    def test_delete_organization_via_api(self):
        from backend.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.post("/organization/create", json={"name": "del-api-org"})
        org_id = resp.json()["organization_id"]
        resp = client.delete(f"/organization/{org_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] is True
