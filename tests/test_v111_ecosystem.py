"""v11.1 Plugin & Agent SDK Ecosystem — 85 tests covering SDK, registry, marketplace, APIs, DB, security."""
import os
import sys
import tempfile
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.memory_store import (
    init_db, mem_save_plugin, mem_get_plugin, mem_list_plugins, mem_delete_plugin,
    mem_save_marketplace_package, mem_get_marketplace_package,
    mem_search_marketplace_packages, mem_delete_marketplace_package,
    mem_save_custom_agent, mem_list_custom_agents, mem_delete_custom_agent,
    mem_save_custom_workflow, mem_list_custom_workflows, mem_delete_custom_workflow,
)
from services.plugin_registry import PluginRegistry, PluginEntry
from services.marketplace_service import MarketplaceService
from sdk.plugin_sdk.base_plugin import BasePlugin, PluginManifest, PluginType
from sdk.agent_sdk.base_agent import BaseAgent, AgentCapability
from sdk.workflow_sdk.base_workflow import WorkflowStep, WorkflowStatus
from sdk.benchmark_sdk.base_benchmark import BenchmarkCriteria, BenchmarkTest
from sdk.deployment_sdk.base_deployment import DeploymentConfig, DeploymentResult
from sdk.validation_sdk.base_validator import ValidationRule, ValidationReport
from sdk.examples.example_plugin import CodeQualityValidator
from sdk.examples.example_agent import DocGenAgent
from sdk.examples.example_workflow import CICDPipelineWorkflow
from sdk.examples.example_benchmark_pack import FlutterBenchmarkPack
from sdk.examples.example_deployment_target import KubernetesTarget
from sdk.examples.example_validator import APISchemaValidator


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    from backend.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def reset_memory_db():
    """Ensure a clean in-memory (or file-based) DB for each test."""
    init_db()


@pytest.fixture
def temp_plugin_file():
    """Create a temporary plugin .py file."""
    content = '''"""Test Plugin"""
# name: test-plugin
# version: 1.0.0
# author: Test
# description: A test plugin
# type: tool

from sdk.plugin_sdk.base_plugin import BasePlugin, PluginManifest

class TestPlugin(BasePlugin):
    def __init__(self, config=None):
        super().__init__(config)
        self.manifest = PluginManifest(name="test-plugin", version="1.0.0")
    def install(self) -> bool: return True
    def uninstall(self) -> bool: return True
    def configure(self, config) -> bool: return True
    def validate(self) -> bool: return True
'''
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(content)
        path = f.name
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def clean_registry():
    reg = PluginRegistry(storage_dir=tempfile.mkdtemp())
    reg._plugins.clear()
    reg._plugin_instances.clear()
    return reg


@pytest.fixture
def clean_marketplace():
    mkt = MarketplaceService(storage_dir=tempfile.mkdtemp())
    mkt._packages.clear()
    return mkt


# ═══════════════════════════════════════════════════════════════════════════
# SDK Base Class Unit Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestPluginSDK:
    def test_plugin_manifest_defaults(self):
        m = PluginManifest()
        assert m.name == ""
        assert m.version == "1.0.0"
        assert m.plugin_type == "tool"

    def test_plugin_manifest_custom(self):
        m = PluginManifest(name="myplugin", version="2.0.0", plugin_type="validator", author="me")
        assert m.name == "myplugin"
        assert m.author == "me"

    def test_plugin_manifest_to_dict(self):
        m = PluginManifest(name="p", version="1.0", dependencies=["dep1"])
        d = m.to_dict()
        assert d["name"] == "p"
        assert d["dependencies"] == ["dep1"]

    def test_plugin_manifest_to_yaml(self):
        m = PluginManifest(name="p", permissions=["read:files"])
        y = m.to_yaml()
        assert "name: p" in y
        assert "read:files" in y

    def test_plugin_manifest_from_dict(self):
        m = PluginManifest.from_dict({"name": "x", "version": "3.0", "author": "a"})
        assert m.name == "x"
        assert m.author == "a"

    def test_base_plugin_install_uninstall(self):
        class TestPlugin(BasePlugin):
            def install(self) -> bool: return True
            def uninstall(self) -> bool: return True
            def configure(self, config) -> bool: return True
            def validate(self) -> bool: return True
        p = TestPlugin()
        assert p.install()
        assert p.uninstall()
        assert not p.is_enabled
        p.enable()
        assert p.is_enabled
        p.disable()
        assert not p.is_enabled

    def test_plugin_type_enum(self):
        assert PluginType.TOOL.value == "tool"
        assert PluginType.VALIDATOR.value == "validator"
        assert PluginType.WORKFLOW.value == "workflow"

    def test_example_plugin(self):
        p = CodeQualityValidator()
        assert p.install()
        assert p.manifest.name == "code-quality-validator"
        assert p.validate()

    def test_example_plugin_validate_code(self):
        p = CodeQualityValidator()
        good_code = "def foo():\n    pass\n"
        result = p.validate_code(good_code)
        assert result["valid"]

        bad_code = "def foo():\n    " + "x" * 200 + "\n"
        result = p.validate_code(bad_code)
        assert any(i["type"] == "style" for i in result["issues"])  # long line issue


class TestAgentSDK:
    def test_agent_capability(self):
        c = AgentCapability(name="test", description="Test capability")
        assert c.name == "test"

    def test_base_agent_interface(self):
        class TestAgent(BaseAgent):
            def initialize(self) -> bool: return True
            def plan(self, ctx) -> dict: return {"steps": []}
            def execute(self, plan) -> dict: return {"status": "done"}
            def validate(self, result) -> bool: return True
            def cleanup(self) -> None: pass
        a = TestAgent(config={"key": "val"})
        assert a.initialize()
        assert a.plan({}) == {"steps": []}
        assert a.validate({})
        a.cleanup()

    def test_agent_manifest(self):
        a = DocGenAgent()
        m = a.get_manifest()
        assert m["name"] == "docgen-agent"
        assert len(m["capabilities"]) == 2

    def test_agent_state(self):
        a = DocGenAgent()
        a.set_state("key1", "val1")
        assert a.get_state()["key1"] == "val1"

    def test_example_agent(self):
        a = DocGenAgent()
        assert a.initialize()
        plan = a.plan({"project_path": "/tmp/test"})
        assert len(plan["steps"]) == 3
        result = a.execute(plan)
        assert result["status"] == "completed"
        assert a.validate(result)
        a.cleanup()


class TestWorkflowSDK:
    def test_workflow_step(self):
        s = WorkflowStep(name="lint", deps=["build"], retries=2)
        d = s.to_dict()
        assert d["name"] == "lint"
        assert d["deps"] == ["build"]

    def test_workflow_status_enum(self):
        assert WorkflowStatus.PENDING.value == "pending"
        assert WorkflowStatus.COMPLETED.value == "completed"

    def test_base_workflow(self):
        w = CICDPipelineWorkflow()
        graph = w.build_graph()
        assert "lint" in graph
        assert "test" in graph
        assert graph["test"].deps == ["lint"]

    def test_workflow_checkpoints(self):
        w = CICDPipelineWorkflow()
        cpid = w.save_checkpoint({"step": "test"})
        assert w.load_checkpoint(cpid) == {"step": "test"}
        assert len(w.list_checkpoints()) == 1

    def test_workflow_execute(self):
        w = CICDPipelineWorkflow()
        result = w.execute()
        assert result["status"] == "completed"

    def test_workflow_monitor(self):
        w = CICDPipelineWorkflow()
        m = w.monitor()
        assert "workflow_id" in m
        assert m["status"] == "pending"

    def test_workflow_rollback_recover(self):
        w = CICDPipelineWorkflow()
        assert w.rollback()
        assert w.status == WorkflowStatus.ROLLED_BACK
        assert w.recover()
        assert w.status == WorkflowStatus.PENDING


class TestBenchmarkSDK:
    def test_benchmark_criteria(self):
        c = BenchmarkCriteria(name="speed", weight=2.0)
        assert c.to_dict()["name"] == "speed"
        c2 = BenchmarkCriteria.from_dict({"name": "mem", "weight": 1.5})
        assert c2.name == "mem"

    def test_benchmark_test(self):
        t = BenchmarkTest(name="test1", command="pytest", timeout=30)
        assert t.command == "pytest"

    def test_example_benchmark_pack(self):
        bp = FlutterBenchmarkPack()
        assert len(bp.tests) == 2
        assert len(bp.criteria) == 2
        assert bp.domain == "flutter_ui"

    def test_benchmark_pack_evaluate(self):
        bp = FlutterBenchmarkPack()
        results = {"render_time": {"value": 10}, "memory_usage": {"value": 40}}
        score = bp.evaluate(results)
        assert score["total_score"] == 1.0

    def test_benchmark_pack_evaluate_fail(self):
        bp = FlutterBenchmarkPack()
        results = {"render_time": {"value": 20}, "memory_usage": {"value": 60}}
        score = bp.evaluate(results)
        assert score["total_score"] < 1.0

    def test_benchmark_load_requirements(self):
        bp = FlutterBenchmarkPack()
        req = bp.load_requirements()
        assert "Flutter" in req


class TestDeploymentSDK:
    def test_deployment_config(self):
        c = DeploymentConfig(target="aws", region="eu-west-1")
        assert c.target == "aws"

    def test_deployment_result(self):
        r = DeploymentResult(success=True, url="https://example.com")
        d = r.to_dict()
        assert d["success"]
        assert d["url"] == "https://example.com"

    def test_example_deployment(self):
        dt = KubernetesTarget()
        result = dt.deploy()
        assert result.success
        assert dt.verify(result)
        assert dt.rollback(result)

    def test_deployment_validate_config(self):
        c = DeploymentConfig()
        dt = KubernetesTarget(c)
        errors = dt.validate_config()
        assert "project_dir is required" in errors


class TestValidationSDK:
    def test_validation_rule(self):
        r = ValidationRule(name="check-1", severity="error")
        assert r.name == "check-1"

    def test_validation_report(self):
        r = ValidationReport(passed=True, summary="All ok")
        d = r.to_dict()
        assert d["passed"]

    def test_example_validator(self):
        v = APISchemaValidator()
        report = v.validate({})
        assert not report.passed

    def test_validator_empty_doc_passes(self):
        v = APISchemaValidator()
        report = v.validate({"openapi": "3.0.0", "paths": {}})
        assert report.passed

    def test_validator_bad_openapi(self):
        v = APISchemaValidator()
        report = v.validate({"openapi": "2.0.0", "paths": {}})
        assert not report.passed

    def test_validator_warns_missing_schema(self):
        v = APISchemaValidator()
        doc = {
            "openapi": "3.0.0",
            "paths": {
                "/api/test": {
                    "get": {
                        "responses": {"200": {"description": "ok"}}
                    }
                }
            }
        }
        report = v.validate(doc)
        assert len(report.warnings) > 0


# ═══════════════════════════════════════════════════════════════════════════
# Plugin Registry Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestPluginRegistry:
    def test_registry_singleton(self):
        r1 = PluginRegistry()
        r2 = PluginRegistry()
        assert r1 is r2

    def test_install_plugin_file(self, temp_plugin_file, clean_registry):
        reg = clean_registry
        entry = reg.install_plugin(temp_plugin_file)
        assert entry.manifest.name == "test-plugin"
        assert entry.enabled

    def test_install_with_manifest(self, temp_plugin_file, clean_registry):
        reg = clean_registry
        manifest = PluginManifest(name="custom", version="2.0.0", plugin_type="validator", entry_point=temp_plugin_file)
        entry = reg.install_plugin(temp_plugin_file, manifest=manifest)
        assert entry.manifest.name == "custom"

    def test_list_plugins(self, temp_plugin_file, clean_registry):
        reg = clean_registry
        reg.install_plugin(temp_plugin_file)
        plugins = reg.list_plugins()
        assert len(plugins) == 1

    def test_list_plugins_by_type(self, temp_plugin_file, clean_registry):
        reg = clean_registry
        reg.install_plugin(temp_plugin_file)
        plugins = reg.list_plugins(plugin_type="tool")
        assert len(plugins) == 1
        plugins = reg.list_plugins(plugin_type="validator")
        assert len(plugins) == 0

    def test_list_enabled_only(self, temp_plugin_file, clean_registry):
        reg = clean_registry
        entry = reg.install_plugin(temp_plugin_file)
        plugins = reg.list_plugins(enabled_only=True)
        assert len(plugins) == 1
        reg.disable_plugin(entry.id)
        plugins = reg.list_plugins(enabled_only=True)
        assert len(plugins) == 0

    def test_enable_disable_plugin(self, temp_plugin_file, clean_registry):
        reg = clean_registry
        entry = reg.install_plugin(temp_plugin_file)
        assert reg.enable_plugin(entry.id)
        assert reg.get_plugin(entry.id).enabled
        assert reg.disable_plugin(entry.id)
        assert not reg.get_plugin(entry.id).enabled

    def test_uninstall_plugin(self, temp_plugin_file, clean_registry):
        reg = clean_registry
        entry = reg.install_plugin(temp_plugin_file)
        pid = entry.id
        assert reg.uninstall_plugin(pid)
        assert reg.get_plugin(pid) is None

    def test_get_plugin(self, temp_plugin_file, clean_registry):
        reg = clean_registry
        entry = reg.install_plugin(temp_plugin_file)
        found = reg.get_plugin(entry.id)
        assert found is not None
        assert found.id == entry.id

    def test_verify_compatibility(self, clean_registry):
        reg = clean_registry
        manifest = PluginManifest(name="comp", compatibility=">=11.1.0")
        entry = PluginEntry(id="test", manifest=manifest)
        reg._plugins["test"] = entry
        assert reg.verify_compatibility("test")

    def test_verify_compatibility_fails(self, clean_registry):
        reg = clean_registry
        manifest = PluginManifest(name="comp", compatibility=">=12.0.0")
        entry = PluginEntry(id="test", manifest=manifest)
        reg._plugins["test"] = entry
        assert not reg.verify_compatibility("test")

    def test_validate_manifest(self, clean_registry):
        reg = clean_registry
        errors = reg._validate_manifest(PluginManifest(entry_point="test.py"))
        errors2 = reg._validate_manifest(PluginManifest(name="valid", entry_point="test.py", plugin_type="tool"))
        assert len(errors) > 0  # missing name
        assert len(errors2) == 0

    def test_validate_manifest_bad_type(self, clean_registry):
        reg = clean_registry
        errors = reg._validate_manifest(PluginManifest(name="x", entry_point="test.py", plugin_type="invalid"))
        assert any("Invalid plugin type" in e for e in errors)


# ═══════════════════════════════════════════════════════════════════════════
# Marketplace Service Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestMarketplaceService:
    def test_marketplace_singleton(self):
        m1 = MarketplaceService()
        m2 = MarketplaceService()
        assert m1 is m2

    def test_publish_package(self, clean_marketplace):
        mkt = clean_marketplace
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("# test")
            path = f.name
        pkg = mkt.publish_package("test-pkg", "1.0.0", "author", "A test", path)
        assert pkg.name == "test-pkg"
        assert pkg.package_type == "plugin"
        os.unlink(path)

    def test_get_package(self, clean_marketplace):
        mkt = clean_marketplace
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("# test")
            path = f.name
        pkg = mkt.publish_package("p1", "1.0", "a", "d", path)
        found = mkt.get_package(pkg.id)
        assert found is not None
        assert found.name == "p1"
        os.unlink(path)

    def test_get_package_by_name(self, clean_marketplace):
        mkt = clean_marketplace
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("# test")
            path = f.name
        mkt.publish_package("unique-name", "1.0", "a", "d", path)
        found = mkt.get_package_by_name("unique-name")
        assert found is not None
        os.unlink(path)

    def test_search_packages(self, clean_marketplace):
        mkt = clean_marketplace
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("# test")
            path = f.name
        mkt.publish_package("alpha", "1.0", "author1", "Alpha description", path)
        mkt.publish_package("beta", "1.0", "author2", "Beta description", path)
        results = mkt.search_packages(query="alpha")
        assert len(results) == 1
        assert results[0].name == "alpha"
        results = mkt.search_packages(query="description")
        assert len(results) == 2
        os.unlink(path)

    def test_search_packages_by_type(self, clean_marketplace):
        mkt = clean_marketplace
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("# test")
            path = f.name
        mkt.publish_package("p1", "1.0", "a", "d", path, package_type="plugin")
        mkt.publish_package("p2", "1.0", "a", "d", path, package_type="benchmark")
        results = mkt.search_packages(package_type="benchmark")
        assert len(results) == 1
        os.unlink(path)

    def test_rating(self, clean_marketplace):
        mkt = clean_marketplace
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("# test")
            path = f.name
        pkg = mkt.publish_package("rate-me", "1.0", "a", "d", path)
        mkt.rate_package(pkg.id, 4.5)
        mkt.rate_package(pkg.id, 3.5)
        pkg = mkt.get_package(pkg.id)
        assert pkg.rating == 4.0
        assert pkg.rating_count == 2
        os.unlink(path)

    def test_download_count(self, clean_marketplace):
        mkt = clean_marketplace
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("# test")
            path = f.name
        pkg = mkt.publish_package("dl-test", "1.0", "a", "d", path)
        mkt.record_download(pkg.id)
        mkt.record_download(pkg.id)
        pkg = mkt.get_package(pkg.id)
        assert pkg.downloads == 2
        os.unlink(path)

    def test_update_package(self, clean_marketplace):
        mkt = clean_marketplace
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("# test")
            path = f.name
        pkg = mkt.publish_package("update-me", "1.0", "a", "d", path)
        mkt.update_package(pkg.id, description="Updated", version="2.0")
        pkg = mkt.get_package(pkg.id)
        assert pkg.description == "Updated"
        assert pkg.version == "2.0"
        os.unlink(path)

    def test_delete_package(self, clean_marketplace):
        mkt = clean_marketplace
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("# test")
            path = f.name
        pkg = mkt.publish_package("delete-me", "1.0", "a", "d", path)
        pid = pkg.id
        assert mkt.delete_package(pid)
        assert mkt.get_package(pid) is None
        os.unlink(path)

    def test_install_package(self, clean_marketplace):
        mkt = clean_marketplace
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("# test content")
            path = f.name
        pkg = mkt.publish_package("install-me", "1.0", "a", "d", path)
        target = tempfile.mkdtemp()
        result = mkt.install_package(pkg.id, target_dir=target)
        assert result is not None
        assert Path(result).exists()
        os.unlink(path)

    def test_list_packages(self, clean_marketplace):
        mkt = clean_marketplace
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("# test")
            path = f.name
        mkt.publish_package("l1", "1.0", "a", "d", path)
        mkt.publish_package("l2", "1.0", "a", "d", path)
        pkgs = mkt.list_packages()
        assert len(pkgs) == 2
        os.unlink(path)

    def test_verified_only(self, clean_marketplace):
        mkt = clean_marketplace
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("# test")
            path = f.name
        pkg = mkt.publish_package("v1", "1.0", "a", "d", path)
        mkt.update_package(pkg.id, verified=True)
        pkgs = mkt.list_packages(verified_only=True)
        assert len(pkgs) == 1
        os.unlink(path)


# ═══════════════════════════════════════════════════════════════════════════
# Database CRUD Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestDatabaseCRUD:
    def test_save_and_get_plugin(self):
        pid = str(uuid.uuid4())
        mem_save_plugin({
            "id": pid, "name": "db-plugin", "version": "1.0", "author": "test",
            "plugin_type": "tool", "source": "/tmp/p.py", "enabled": True,
            "installed_at": "now", "updated_at": "now",
        })
        p = mem_get_plugin(pid)
        assert p is not None
        assert p["name"] == "db-plugin"
        assert p["enabled"] == 1

    def test_list_plugins(self):
        for i in range(3):
            mem_save_plugin({
                "id": str(uuid.uuid4()), "name": f"p{i}", "version": "1.0",
                "plugin_type": "tool", "source": "/tmp/p.py",
            })
        plugins = mem_list_plugins()
        assert len(plugins) >= 3

    def test_list_plugins_by_type(self):
        vid = str(uuid.uuid4())
        mem_save_plugin({
            "id": vid, "name": "v1", "version": "1.0",
            "plugin_type": "validator", "source": "/tmp/v.py",
        })
        mem_list_plugins(plugin_type="tool")
        validators = mem_list_plugins(plugin_type="validator")
        assert any(p["name"] == "v1" for p in validators)

    def test_delete_plugin(self):
        pid = str(uuid.uuid4())
        mem_save_plugin({"id": pid, "name": "del-p", "version": "1.0", "plugin_type": "tool", "source": ""})
        assert mem_delete_plugin(pid)
        assert mem_get_plugin(pid) is None

    def test_save_and_get_marketplace_package(self):
        pid = str(uuid.uuid4())
        mem_save_marketplace_package({
            "id": pid, "name": "mkt-pkg", "version": "1.0", "author": "a",
            "description": "d", "package_type": "plugin", "downloads": 10, "rating": 4.5, "rating_count": 2,
        })
        p = mem_get_marketplace_package(pid)
        assert p is not None
        assert p["name"] == "mkt-pkg"
        assert p["downloads"] == 10

    def test_search_marketplace(self):
        for i in range(3):
            mem_save_marketplace_package({
                "id": str(uuid.uuid4()), "name": f"search-pkg-{i}", "version": "1.0",
                "author": "author", "description": f"Description {i}", "package_type": "plugin",
            })
        results = mem_search_marketplace_packages(query="search-pkg-1")
        assert len(results) >= 1

    def test_search_by_type(self):
        mem_save_marketplace_package({
            "id": str(uuid.uuid4()), "name": "bench-pkg", "version": "1.0",
            "author": "a", "description": "d", "package_type": "benchmark",
        })
        results = mem_search_marketplace_packages(package_type="benchmark")
        assert len(results) >= 1

    def test_delete_marketplace_package(self):
        pid = str(uuid.uuid4())
        mem_save_marketplace_package({"id": pid, "name": "del-mkt", "version": "1.0", "author": "a", "description": "d", "package_type": "plugin"})
        assert mem_delete_marketplace_package(pid)
        assert mem_get_marketplace_package(pid) is None

    def test_save_and_list_custom_agents(self):
        aid = str(uuid.uuid4())
        mem_save_custom_agent({"id": aid, "name": "agent-1", "version": "1.0", "description": "test", "source": "/tmp/a.py"})
        agents = mem_list_custom_agents()
        assert any(a["name"] == "agent-1" for a in agents)

    def test_delete_custom_agent(self):
        aid = str(uuid.uuid4())
        mem_save_custom_agent({"id": aid, "name": "del-agent", "version": "1.0", "description": "test", "source": ""})
        assert mem_delete_custom_agent(aid)
        assert len([a for a in mem_list_custom_agents() if a["id"] == aid]) == 0

    def test_save_and_list_custom_workflows(self):
        wid = str(uuid.uuid4())
        mem_save_custom_workflow({"id": wid, "name": "wf-1", "version": "1.0", "description": "test", "source": ""})
        wfs = mem_list_custom_workflows()
        assert any(w["name"] == "wf-1" for w in wfs)

    def test_delete_custom_workflow(self):
        wid = str(uuid.uuid4())
        mem_save_custom_workflow({"id": wid, "name": "del-wf", "version": "1.0", "description": "test", "source": ""})
        assert mem_delete_custom_workflow(wid)
        assert len([w for w in mem_list_custom_workflows() if w["id"] == wid]) == 0


# ═══════════════════════════════════════════════════════════════════════════
# HTTP API Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestPluginAPI:
    def test_plugins_list_empty(self, client):
        r = client.get("/plugins")
        assert r.status_code == 200
        data = r.json()
        assert "plugins" in data
        assert isinstance(data["plugins"], list)

    def test_plugin_install_and_uninstall(self, client):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write('''"""API Test Plugin"""
# name: api-plugin
# version: 1.0.0
from sdk.plugin_sdk.base_plugin import BasePlugin
class ApiPlugin(BasePlugin):
    def install(self) -> bool: return True
    def uninstall(self) -> bool: return True
    def configure(self, config) -> bool: return True
    def validate(self) -> bool: return True
''')
            path = f.name
        r = client.post("/plugins/install", json={"source": path})
        assert r.status_code == 200
        data = r.json()
        assert data["manifest"]["name"] == "api-plugin"
        pid = data["id"]
        r2 = client.post("/plugins/uninstall", json={"plugin_id": pid})
        assert r2.status_code == 200
        assert r2.json()["uninstalled"]
        os.unlink(path)

    def test_plugin_enable_disable(self, client):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write('''"""ED Test Plugin"""
from sdk.plugin_sdk.base_plugin import BasePlugin
class EdPlugin(BasePlugin):
    def install(self) -> bool: return True
    def uninstall(self) -> bool: return True
    def configure(self, config) -> bool: return True
    def validate(self) -> bool: return True
''')
            path = f.name
        r = client.post("/plugins/install", json={"source": path})
        pid = r.json()["id"]
        r2 = client.post("/plugins/disable", json={"plugin_id": pid})
        assert r2.json()["disabled"]
        r3 = client.post("/plugins/enable", json={"plugin_id": pid})
        assert r3.json()["enabled"]
        client.post("/plugins/uninstall", json={"plugin_id": pid})
        os.unlink(path)

    def test_plugin_details(self, client):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write('''"""Detail Test Plugin"""
from sdk.plugin_sdk.base_plugin import BasePlugin
class DetailPlugin(BasePlugin):
    def install(self) -> bool: return True
    def uninstall(self) -> bool: return True
    def configure(self, config) -> bool: return True
    def validate(self) -> bool: return True
''')
            path = f.name
        r = client.post("/plugins/install", json={"source": path})
        pid = r.json()["id"]
        r2 = client.get(f"/plugins/details?plugin_id={pid}")
        assert r2.status_code == 200
        assert r2.json()["id"] == pid
        client.post("/plugins/uninstall", json={"plugin_id": pid})
        os.unlink(path)

    def test_plugin_install_error(self, client):
        r = client.post("/plugins/install", json={"source": "/nonexistent/plugin.py"})
        # Should still return 200 as the registry creates an entry even if detection fails
        assert r.status_code in (200, 400)

    def test_ecosystem_health(self, client):
        r = client.get("/ecosystem/health")
        assert r.status_code == 200
        data = r.json()
        assert data["version"] == "13.0.0"
        assert "plugins_installed" in data
        assert "marketplace_packages" in data


class TestMarketplaceAPI:
    def test_marketplace_list_empty(self, client):
        r = client.get("/plugins/marketplace/list")
        assert r.status_code == 200
        data = r.json()
        assert "packages" in data

    def test_marketplace_publish_and_search(self, client):
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8") as f:
            f.write("# test package content")
            path = f.name
        r = client.post("/plugins/marketplace/publish", json={
            "name": "api-test-pkg", "version": "1.0.0",
            "author": "tester", "description": "API test",
            "source_path": path, "package_type": "plugin",
        })
        assert r.status_code == 200
        r2 = client.get("/plugins/marketplace", params={"query": "api-test-pkg"})
        assert r2.status_code == 200
        assert len(r2.json()["packages"]) >= 1
        os.unlink(path)

    def test_marketplace_rate(self, client):
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8") as f:
            f.write("# rate test")
            path = f.name
        r = client.post("/plugins/marketplace/publish", json={
            "name": "rate-test", "version": "1.0", "author": "a",
            "description": "d", "source_path": path,
        })
        pkg_id = r.json()["id"]
        r2 = client.post("/plugins/marketplace/rate", json={"package_id": pkg_id, "rating": 4.0})
        assert r2.status_code == 200
        assert r2.json()["rating"] == 4.0
        os.unlink(path)


class TestAgentAPI:
    def test_agent_register_and_list(self, client):
        r = client.post("/agents/register", json={
            "name": "api-agent", "version": "1.0.0", "source": "/tmp/agent.py",
            "description": "Test agent",
            "capabilities": [{"name": "cap1", "description": "test"}],
        })
        assert r.status_code == 200
        assert r.json()["name"] == "api-agent"
        r2 = client.get("/agents/custom")
        assert r2.status_code == 200
        agents = r2.json()["agents"]
        assert any(a["name"] == "api-agent" for a in agents)

    def test_agent_delete(self, client):
        r = client.post("/agents/register", json={
            "name": "del-agent", "version": "1.0", "source": "/tmp/a.py", "description": "d",
        })
        aid = r.json()["id"]
        r2 = client.post("/agents/delete", json={"agent_id": aid})
        assert r2.status_code == 200
        assert r2.json()["deleted"]


class TestWorkflowAPI:
    def test_workflow_register_and_list(self, client):
        r = client.post("/workflows/register", json={
            "name": "api-workflow", "version": "1.0.0", "source": "/tmp/wf.py",
            "description": "Test workflow",
            "steps": [{"name": "step1", "deps": []}],
        })
        assert r.status_code == 200
        assert r.json()["name"] == "api-workflow"
        r2 = client.get("/workflows")
        assert r2.status_code == 200
        wfs = r2.json()["workflows"]
        assert any(w["name"] == "api-workflow" for w in wfs)

    def test_workflow_delete(self, client):
        r = client.post("/workflows/register", json={
            "name": "del-wf", "version": "1.0", "source": "/tmp/w.py", "description": "d",
        })
        wid = r.json()["id"]
        r2 = client.post("/workflows/delete", json={"workflow_id": wid})
        assert r2.status_code == 200
        assert r2.json()["deleted"]


# ═══════════════════════════════════════════════════════════════════════════
# Security & Sandbox Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestSecurityModel:
    def test_permission_system(self):
        manifest = PluginManifest(name="secure", permissions=["read:files", "write:logs"])
        assert "read:files" in manifest.permissions
        assert "write:logs" in manifest.permissions

    def test_permission_granted_on_install(self, clean_registry, temp_plugin_file):
        reg = clean_registry
        manifest = PluginManifest(name="secure-plugin", permissions=["read:files"], entry_point=temp_plugin_file)
        entry = reg.install_plugin(temp_plugin_file, manifest=manifest, permissions=["read:files"])
        assert "read:files" in entry.permissions_granted

    def test_resource_limits_defaults(self):
        entry = PluginEntry()
        assert entry.resource_limits["cpu"] == 1
        assert entry.resource_limits["memory_mb"] == 256

    def test_manifest_compatibility_validation(self, clean_registry):
        reg = clean_registry
        assert reg._validate_manifest(PluginManifest(name="x", entry_point="test.py", plugin_type="tool")) == []
        errors = reg._validate_manifest(PluginManifest(name="", entry_point="", plugin_type="tool"))
        assert len(errors) > 0

    def test_checksum_computation(self, clean_registry):
        reg = clean_registry
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("# test")
            path = f.name
        cs = reg._compute_checksum(path)
        assert len(cs) == 64  # sha256 hex
        cs2 = reg._compute_checksum("/nonexistent")
        assert cs2 == ""
        os.unlink(path)
