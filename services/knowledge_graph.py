"""Repository Knowledge Graph — file/API/dependency relationships, impact analysis, graph queries."""
import ast
import logging
import re
import threading
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FileNode:
    path: str
    file_type: str = ""
    imports: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    apis: list[dict] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    dependents: list[str] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    size_bytes: int = 0
    line_count: int = 0
    complexity: float = 0.0
    tech_stack: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Relationship:
    source: str
    target: str
    rel_type: str  # imports, extends, implements, calls, tests, api_depends, service_depends
    weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ImpactResult:
    affected_files: list[dict]
    impact_score: float
    breaking_changes: list[str]
    cascade_paths: list[list[str]]
    recommendations: list[str]


class KnowledgeGraph:
    def __init__(self, repo_path: str | None = None):
        self.repo_path = Path(repo_path) if repo_path else None
        self.files: dict[str, FileNode] = {}
        self.relationships: list[Relationship] = []
        self._lock = threading.Lock()
        self._adjacency: dict[str, set[str]] = defaultdict(set)
        self._reverse_adj: dict[str, set[str]] = defaultdict(set)

    def build_from_repo(self, repo_path: str) -> int:
        self.repo_path = Path(repo_path)
        if not self.repo_path.exists():
            raise FileNotFoundError(f"Repository path not found: {repo_path}")

        all_files = sorted(self.repo_path.rglob("*"))
        for fpath in all_files:
            if not fpath.is_file():
                continue
            if "__pycache__" in str(fpath) or ".git" in str(fpath) or "node_modules" in str(fpath):
                continue
            rel = str(fpath.relative_to(self.repo_path))
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                content = ""
            node = FileNode(
                path=rel,
                file_type=fpath.suffix.lower(),
                size_bytes=fpath.stat().st_size,
                line_count=len(content.splitlines()) if content else 0,
            )
            if fpath.suffix == ".py":
                self._parse_python_file(content, node)
            elif fpath.suffix in (".js", ".ts", ".jsx", ".tsx"):
                self._parse_js_ts_file(content, node)
            elif fpath.suffix in (".html", ".vue", ".svelte"):
                node.tech_stack.append("frontend")
            elif fpath.suffix in (".yaml", ".yml", ".json", ".toml", ".ini", ".cfg"):
                node.tech_stack.append("config")
            self.files[rel] = node

        self._build_relationships()
        logger.info("Knowledge graph built: %d files, %d relationships", len(self.files), len(self.relationships))
        return len(self.files)

    def _parse_python_file(self, content: str, node: FileNode) -> None:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            node.tech_stack.append("python_syntax_error")
            return
        node.tech_stack.append("python")
        for item in ast.walk(tree):
            if isinstance(item, ast.Import):
                for alias in item.names:
                    node.imports.append(alias.name or "")
                    if alias.asname:
                        node.exports.append(alias.asname)
            elif isinstance(item, ast.ImportFrom):
                module = item.module or ""
                for alias in item.names:
                    full = f"{module}.{alias.name}" if module else alias.name
                    node.imports.append(full)
                    if alias.asname:
                        node.exports.append(alias.asname)
            elif isinstance(item, ast.ClassDef):
                node.classes.append(item.name)
                for base in item.bases:
                    if isinstance(base, ast.Name):
                        node.exports.append(base.id)
                    elif isinstance(base, ast.Attribute):
                        node.exports.append(f"{base.value.id}.{base.attr}" if isinstance(base.value, ast.Name) else base.attr)
            elif isinstance(item, ast.FunctionDef):
                node.functions.append(item.name)
                for dec in item.decorator_list:
                    if isinstance(dec, ast.Call):
                        func = dec.func
                        method = ""
                        if isinstance(func, ast.Attribute):
                            method = func.attr
                        elif isinstance(func, ast.Name):
                            method = func.id
                        if method in ("get", "post", "put", "delete", "patch", "route"):
                            path = ""
                            for a in dec.args:
                                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                                    path = a.value
                            node.apis.append({
                                "method": method.upper(),
                                "path": path,
                                "handler": item.name,
                                "line": item.lineno,
                            })
            elif isinstance(item, ast.Call):
                if isinstance(item.func, ast.Attribute) and item.func.attr in ("add_route", "include_router", "mount"):
                    for a in item.args:
                        if isinstance(a, ast.Str):
                            node.exports.append(f"route:{a.s}")
                        elif isinstance(a, ast.Constant) and isinstance(a.value, str):
                            node.exports.append(f"route:{a.value}")

    def _parse_js_ts_file(self, content: str, node: FileNode) -> None:
        node.tech_stack.append("javascript")
        import_re = re.findall(r"""from\s+['"]([^'"]+)['"]|require\s*\(\s*['"]([^'"]+)['"]""", content)
        for m in import_re:
            node.imports.append(m[0] or m[1])
        export_re = re.findall(r'(?:export\s+(?:default\s+)?)?(?:function|const|let|var|class)\s+(\w+)', content)
        node.exports.extend(export_re)
        api_re = re.findall(r'(?:app|router|server)\s*\.\s*(get|post|put|delete|patch)\s*\(\s*[\'"]([^\'"]+)[\'"]', content)
        for method, path in api_re:
            node.apis.append({"method": method.upper(), "path": f"/{path.lstrip('/')}", "handler": ""})

    def _build_relationships(self) -> None:
        for path, node in self.files.items():
            for imp in node.imports:
                target = self._resolve_import(path, imp)
                if target:
                    rel = Relationship(source=path, target=target, rel_type="imports")
                    self.relationships.append(rel)
                    self._adjacency[path].add(target)
                    self._reverse_adj[target].add(path)
                    if target in self.files:
                        self.files[target].dependents.append(path)
                        if path not in self.files[target].dependents:
                            pass
        for path, node in self.files.items():
            for cls_name in node.classes:
                for other_path, other_node in self.files.items():
                    if other_path != path and cls_name in other_node.imports:
                        rel = Relationship(source=path, target=other_path, rel_type="implements", metadata={"class": cls_name})
                        self.relationships.append(rel)
            for api in node.apis:
                for other_path, other_node in self.files.items():
                    if other_path != path and any(
                        t.get("method") == api["method"] and t.get("path") == api["path"]
                        for t in other_node.apis
                    ):
                        rel = Relationship(source=path, target=other_path, rel_type="api_depends",
                                           metadata={"method": api["method"], "path": api["path"]})
                        self.relationships.append(rel)

    def _resolve_import(self, current_path: str, imp: str) -> str | None:
        parts = imp.split(".")
        for i in range(len(parts), 0, -1):
            prefix = ".".join(parts[:i])
            rel_path = prefix.replace(".", "/") + ".py"
            if (self.repo_path / rel_path).exists():
                return str(Path(rel_path).as_posix())
            init_path = prefix.replace(".", "/") + "/__init__.py"
            if (self.repo_path / init_path).exists():
                return str(Path(init_path).as_posix())
        rel = Path(current_path).parent
        for i in range(len(parts), 0, -1):
            prefix = "/".join(parts[:i])
            test_path = rel / f"{prefix}.py"
            if (self.repo_path / test_path).exists():
                return str(test_path.as_posix())

        for fpath in self.files:
            stem = Path(fpath).stem
            if stem == parts[0] or fpath.endswith(f"/{parts[0]}.py"):
                return fpath
        return None

    def find_test_files(self, source_path: str) -> list[str]:
        tests = []
        stem = Path(source_path).stem
        parent = Path(source_path).parent
        if self.repo_path:
            test_patterns = [
                f"tests/test_{stem}.py",
                f"tests/{stem}_test.py",
                f"tests/{parent.name}/test_{stem}.py",
                f"tests/{source_path}",
            ]
            for pattern in test_patterns:
                test_path = self.repo_path / pattern
                if test_path.exists():
                    rel = str(test_path.relative_to(self.repo_path))
                    tests.append(rel)
                    if source_path in self.files:
                        self.files[source_path].test_files.append(rel)
        for fpath in self.files:
            if "test" in fpath and stem in fpath:
                if fpath not in tests:
                    tests.append(fpath)
        return tests

    def impact_analysis(self, changed_files: list[str]) -> ImpactResult:
        visited: set[str] = set()
        cascade: list[list[str]] = []
        affected: dict[str, float] = {}
        breaking: list[str] = []

        def bfs(start: str, path: list[str]) -> None:
            queue = [(start, path)]
            while queue:
                current, cur_path = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                for neighbor in self._reverse_adj.get(current, set()):
                    new_path = cur_path + [neighbor]
                    cascade.append(new_path)
                    weight = 1.0 / len(new_path)
                    affected[neighbor] = max(affected.get(neighbor, 0), weight)
                    self._check_breaking(current, neighbor, breaking)
                    queue.append((neighbor, new_path))

        for cf in changed_files:
            if cf in self.files:
                bfs(cf, [cf])

        affected_files = [
            {"path": p, "impact_score": round(s, 3), "file_type": self.files[p].file_type if p in self.files else ""}
            for p, s in sorted(affected.items(), key=lambda x: -x[1])
        ]
        total_files = len(self.files) or 1
        impact_score = len(affected) / total_files
        return ImpactResult(
            affected_files=affected_files,
            impact_score=round(impact_score, 3),
            breaking_changes=breaking,
            cascade_paths=cascade[:20],
            recommendations=self._generate_recommendations(changed_files, affected_files, breaking),
        )

    def _check_breaking(self, changed: str, dependent: str, breaking: list[str]) -> None:
        if changed in self.files and dependent in self.files:
            changed_node = self.files[changed]
            dep_node = self.files[dependent]
            for cls in changed_node.classes:
                if any(cls in imp for imp in dep_node.imports):
                    breaking.append(f"Class '{cls}' change in {changed} affects {dependent}")

    def _generate_recommendations(self, changed: list[str], affected: list[dict], breaking: list[str]) -> list[str]:
        recs = []
        if breaking:
            recs.append(f"Address {len(breaking)} breaking changes before deployment")
        if len(affected) > 10:
            recs.append(f"Wide impact ({len(affected)} files affected) — consider phased rollout")
        for f in affected[:3]:
            recs.append(f"Verify tests for {f['path']} still pass")
        for cf in changed:
            tests = self.find_test_files(cf)
            if not tests:
                recs.append(f"No tests found for {cf} — consider adding test coverage")
        return recs

    def query_apis(self) -> list[dict]:
        apis = []
        for path, node in self.files.items():
            for api in node.apis:
                apis.append({
                    "file": path,
                    "method": api["method"],
                    "path": api["path"],
                    "handler": api.get("handler", ""),
                })
        return sorted(apis, key=lambda x: (x["path"], x["method"]))

    def query_dependency_graph(self, module: str | None = None) -> dict[str, Any]:
        if module:
            sub_graph = {k: v for k, v in self.files.items() if module in k}
        else:
            sub_graph = self.files
        nodes = [{"id": p, "file_type": n.file_type, "classes": n.classes[:3], "functions": n.functions[:3]} for p, n in sub_graph.items()]
        edges = [{"source": r.source, "target": r.target, "type": r.rel_type} for r in self.relationships
                 if r.source in sub_graph or r.target in sub_graph]
        return {"nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges)}

    def query_service_dependencies(self) -> dict[str, list[str]]:
        deps: dict[str, list[str]] = defaultdict(list)
        for path, node in self.files.items():
            for imp in node.imports:
                if any(service in imp for service in ["service", "api", "client", "db", "redis", "mq", "queue"]):
                    deps[path].append(imp)
        return dict(deps)

    def query_test_mappings(self) -> dict[str, list[str]]:
        mappings: dict[str, list[str]] = {}
        for path, node in self.files.items():
            tests = self.find_test_files(path)
            if tests:
                mappings[path] = tests
        return mappings

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_path": str(self.repo_path) if self.repo_path else "",
            "files": {p: asdict(n) for p, n in self.files.items()},
            "relationships": [asdict(r) for r in self.relationships],
            "file_count": len(self.files),
            "relationship_count": len(self.relationships),
        }

    def get_architecture_summary(self) -> dict[str, Any]:
        tech_stacks: dict[str, int] = defaultdict(int)
        api_count = 0
        test_count = 0
        for node in self.files.values():
            for ts in node.tech_stack:
                tech_stacks[ts] += 1
            api_count += len(node.apis)
            if "test" in node.path:
                test_count += 1
        return {
            "file_count": len(self.files),
            "relationship_count": len(self.relationships),
            "api_count": api_count,
            "test_file_count": test_count,
            "tech_stacks": dict(tech_stacks),
        }

    def visualize_mermaid(self) -> str:
        lines = ["graph LR;"]
        for path, node in self.files.items():
            label = Path(path).stem
            lines.append(f"    {label}[{label}]")
        for r in self.relationships[:50]:
            src = Path(r.source).stem
            tgt = Path(r.target).stem
            if src and tgt and src != tgt:
                lines.append(f"    {src} -->|{r.rel_type}| {tgt}")
        return "\n".join(lines)


def build_knowledge_graph(repo_path: str) -> KnowledgeGraph:
    kg = KnowledgeGraph()
    kg.build_from_repo(repo_path)
    return kg
