"""Cross-Repository Validation — API compatibility, shared library compatibility, schema consistency."""
import json
import logging
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from services.org_graph_service import OrganizationGraph

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    org_id: str = ""
    validation_type: str = ""
    passed: bool = True
    issues: list[dict] = field(default_factory=list)
    summary: str = ""
    details: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CrossRepoValidator:
    def __init__(self, graph: OrganizationGraph):
        self.graph = graph
        self._lock = threading.Lock()
        self._results: dict[str, ValidationResult] = {}

    def validate_api_compatibility(self, org_id: str) -> ValidationResult:
        result = ValidationResult(
            org_id=org_id,
            validation_type="api_compatibility",
        )
        issues = []
        repos = self.graph.list_repositories()

        api_endpoints: dict[str, list[dict]] = {}
        for repo in repos:
            repo_path = Path(repo.path)
            if not repo_path.exists():
                continue
            endpoints = self._extract_api_endpoints(repo_path)
            api_endpoints[repo.name] = endpoints

        route_map: dict[str, list[str]] = {}
        for repo_name, endpoints in api_endpoints.items():
            for ep in endpoints:
                key = f"{ep['method']} {ep['path']}"
                if key not in route_map:
                    route_map[key] = []
                route_map[key].append(repo_name)

        for route, consumers in route_map.items():
            if len(consumers) > 1:
                issues.append({
                    "severity": "warning",
                    "type": "duplicate_route",
                    "message": f"Route {route} defined in multiple repos: {', '.join(consumers)}",
                    "repos": consumers,
                })

        for repo_name in api_endpoints:
            deps = [
                d for d in self.graph.org.dependencies.values()
                if d.source_repo == repo_name or d.target_repo == repo_name
            ]
            for dep in deps:
                target = dep.target_repo if dep.source_repo == repo_name else dep.source_repo
                if target in api_endpoints:
                    methods = {ep['method'] for ep in api_endpoints[repo_name]}
                    target_methods = {ep['method'] for ep in api_endpoints[target]}
                    if 'GET' in target_methods and 'GET' not in methods:
                        issues.append({
                            "severity": "info",
                            "type": "missing_method",
                            "message": f"{repo_name} depends on {target} but doesn't expose GET",
                            "repos": [repo_name, target],
                        })

        result.issues = issues
        result.passed = len(issues) == 0
        result.summary = f"API compatibility: {len(issues)} issue(s) found"
        result.details = json.dumps(issues)
        self._save_result(result)
        return result

    def validate_shared_libraries(self, org_id: str) -> ValidationResult:
        result = ValidationResult(
            org_id=org_id,
            validation_type="shared_libraries",
        )
        issues = []
        repos = self.graph.list_repositories()

        shared_libs = [r for r in repos if r.category == "shared-libraries"]
        consumers = [r for r in repos if r.category != "shared-libraries"]

        lib_interfaces: dict[str, set[str]] = {}
        for lib in shared_libs:
            lib_path = Path(lib.path)
            if not lib_path.exists():
                continue
            exports = self._extract_public_api(lib_path)
            lib_interfaces[lib.name] = exports

        for consumer in consumers:
            consumer_path = Path(consumer.path)
            if not consumer_path.exists():
                continue
            imports = self._extract_imports(consumer_path)
            for lib_name, exports in lib_interfaces.items():
                matching = [imp for imp in imports if lib_name.lower() in imp.lower()]
                if matching:
                    used_exports = set()
                    for imp in matching:
                        for exp in exports:
                            if exp.lower() in imp.lower():
                                used_exports.add(exp)
                    unused = exports - used_exports
                    if unused:
                        issues.append({
                            "severity": "info",
                            "type": "unused_export",
                            "message": f"{consumer.name} imports {lib_name} but doesn't use: {', '.join(list(unused)[:5])}",
                            "repos": [consumer.name, lib_name],
                        })

        result.issues = issues
        result.passed = len(issues) == 0
        result.summary = f"Shared library check: {len(issues)} issue(s) found"
        result.details = json.dumps(issues)
        self._save_result(result)
        return result

    def validate_schema_compatibility(self, org_id: str) -> ValidationResult:
        result = ValidationResult(
            org_id=org_id,
            validation_type="schema_compatibility",
        )
        issues = []
        repos = self.graph.list_repositories()

        for dep in self.graph.org.dependencies.values():
            if dep.relationship != "depends_on":
                continue
            source_repo = next(
                (r for r in repos if r.name == dep.source_repo), None
            )
            target_repo = next(
                (r for r in repos if r.name == dep.target_repo), None
            )
            if not source_repo or not target_repo:
                continue

            source_schemas = self._extract_schemas(Path(source_repo.path)) if Path(source_repo.path).exists() else {}
            target_schemas = self._extract_schemas(Path(target_repo.path)) if Path(target_repo.path).exists() else {}

            for name, fields in source_schemas.items():
                if name in target_schemas:
                    target_fields = target_schemas[name]
                    missing = [f for f in fields if f not in target_fields]
                    if missing:
                        issues.append({
                            "severity": "warning",
                            "type": "schema_mismatch",
                            "message": f"Schema '{name}' in {dep.target_repo} missing fields: {', '.join(missing)}",
                            "repos": [dep.source_repo, dep.target_repo],
                        })

        result.issues = issues
        result.passed = len(issues) == 0
        result.summary = f"Schema compatibility: {len(issues)} issue(s) found"
        result.details = json.dumps(issues)
        self._save_result(result)
        return result

    def validate_deployment_consistency(self, org_id: str) -> ValidationResult:
        result = ValidationResult(
            org_id=org_id,
            validation_type="deployment_consistency",
        )
        issues = []
        docker_repos = []

        for repo in self.graph.list_repositories():
            repo_path = Path(repo.path)
            if not repo_path.exists():
                continue
            has_docker = list(repo_path.glob("Dockerfile*")) or list(repo_path.glob("docker-compose*"))
            if has_docker:
                docker_repos.append(repo.name)

        if len(docker_repos) > 1:
            issues.append({
                "severity": "info",
                "type": "multi_docker",
                "message": f"{len(docker_repos)} repos have Docker configs: {', '.join(docker_repos)}",
                "repos": docker_repos,
            })

        for dep in self.graph.org.dependencies.values():
            if dep.source_repo in docker_repos and dep.target_repo not in docker_repos:
                issues.append({
                    "severity": "warning",
                    "type": "deployment_gap",
                    "message": f"{dep.source_repo} has Docker but its dependency {dep.target_repo} doesn't",
                    "repos": [dep.source_repo, dep.target_repo],
                })

        result.issues = issues
        result.passed = len(issues) == 0
        result.summary = f"Deployment consistency: {len(issues)} issue(s) found"
        result.details = json.dumps(issues)
        self._save_result(result)
        return result

    def validate_documentation_coverage(self, org_id: str) -> ValidationResult:
        result = ValidationResult(
            org_id=org_id,
            validation_type="documentation_coverage",
        )
        issues = []
        for repo in self.graph.list_repositories():
            repo_path = Path(repo.path)
            if not repo_path.exists():
                continue
            readme = repo_path / "README.md"
            if not readme.exists():
                issues.append({
                    "severity": "warning",
                    "type": "missing_readme",
                    "message": f"{repo.name} missing README.md",
                    "repos": [repo.name],
                })
            docs_dir = repo_path / "docs"
            if not docs_dir.exists():
                issues.append({
                    "severity": "info",
                    "type": "missing_docs_dir",
                    "message": f"{repo.name} missing docs/ directory",
                    "repos": [repo.name],
                })

        result.issues = issues
        result.passed = len(issues) == 0
        result.summary = f"Documentation coverage: {len(issues)} issue(s) found"
        result.details = json.dumps(issues)
        self._save_result(result)
        return result

    def run_all_validations(self, org_id: str) -> dict[str, ValidationResult]:
        return {
            "api_compatibility": self.validate_api_compatibility(org_id),
            "shared_libraries": self.validate_shared_libraries(org_id),
            "schema_compatibility": self.validate_schema_compatibility(org_id),
            "deployment_consistency": self.validate_deployment_consistency(org_id),
            "documentation_coverage": self.validate_documentation_coverage(org_id),
        }

    def get_result(self, result_id: str) -> ValidationResult | None:
        with self._lock:
            return self._results.get(result_id)

    def list_results(self, org_id: str) -> list[dict]:
        return [
            r.to_dict() for r in self._results.values()
            if r.org_id == org_id
        ]

    def _save_result(self, result: ValidationResult) -> None:
        with self._lock:
            self._results[result.id] = result

    def _extract_api_endpoints(self, repo_path: Path) -> list[dict]:
        endpoints = []
        patterns = [
            r'@(?:app|router)\.(get|post|put|patch|delete|options)\s*\(\s*[\'"]([^\'"]+)[\'"]',
            r'(?:GET|POST|PUT|PATCH|DELETE)\s+[\'"]([^\'"]+)[\'"]',
        ]
        for py_file in repo_path.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
                for pattern in patterns:
                    for match in re.finditer(pattern, content, re.IGNORECASE):
                        if len(match.groups()) == 2:
                            method, path = match.group(1).lower(), match.group(2)
                        else:
                            method, path = "get", match.group(1)
                        if not path.startswith("/"):
                            path = "/" + path
                        endpoints.append({"method": method.upper(), "path": path, "file": str(py_file.name)})
            except Exception:
                continue
        return endpoints

    def _extract_public_api(self, repo_path: Path) -> set[str]:
        exports = set()
        for py_file in repo_path.rglob("*.py"):
            if "__pycache__" in str(py_file) or py_file.name.startswith("_"):
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
                for match in re.finditer(r'^(?:async\s+)?def\s+(\w+)|^class\s+(\w+)', content, re.MULTILINE):
                    name = match.group(1) or match.group(2)
                    if not name.startswith("_"):
                        exports.add(name)
            except Exception:
                continue
        return exports

    def _extract_imports(self, repo_path: Path) -> set[str]:
        imports = set()
        for py_file in repo_path.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
                for match in re.finditer(r'^(?:from\s+(\S+)\s+)?import\s+(\S+)', content, re.MULTILINE):
                    if match.group(1):
                        imports.add(match.group(1))
                    imports.add(match.group(2))
            except Exception:
                continue
        return imports

    def _extract_schemas(self, repo_path: Path) -> dict[str, list[str]]:
        schemas = {}
        for py_file in repo_path.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
                for match in re.finditer(r'class\s+(\w+)\(.*BaseModel.*\)\s*:', content):
                    schema_name = match.group(1)
                    class_start = match.end()
                    class_end = content.find("\nclass ", class_start)
                    if class_end == -1:
                        class_end = len(content)
                    class_body = content[class_start:class_end]
                    fields = re.findall(r'^\s+(\w+)\s*:', class_body, re.MULTILINE)
                    schemas[schema_name] = fields
            except Exception:
                continue
        return schemas


_validators: dict[str, CrossRepoValidator] = {}
_validator_lock = threading.Lock()


def get_cross_repo_validator(graph: OrganizationGraph | None = None) -> CrossRepoValidator:
    key = id(graph) if graph else "default"
    with _validator_lock:
        if key not in _validators:
            from services.org_graph_service import get_org_graph_service
            g = graph or get_org_graph_service()
            _validators[key] = CrossRepoValidator(g)
        return _validators[key]
