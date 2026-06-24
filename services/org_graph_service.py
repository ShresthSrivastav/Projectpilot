"""Organization Graph Service — multi-repository knowledge graph, dependency mapping, impact analysis."""

import json
import logging
import os
import re
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ORG_DATA_DIR = Path(os.getenv("ORG_DATA_DIR", "./org_data"))
ORG_DATA_DIR.mkdir(parents=True, exist_ok=True)


class RelationshipType(Enum):
    IMPORTS = "imports"
    DEPENDS_ON = "depends_on"
    CALLS = "calls"
    DOCUMENTS = "documents"
    DEPLOYS = "deploys"
    TESTS = "tests"
    EXTENDS = "extends"
    IMPLEMENTS = "implements"
    CONFIGURES = "configures"
    REFERENCES = "references"


class RepoCategory(Enum):
    FRONTEND = "frontend"
    BACKEND = "backend"
    MOBILE = "mobile"
    INFRASTRUCTURE = "infrastructure"
    DOCUMENTATION = "documentation"
    SHARED_LIBRARIES = "shared-libraries"
    DATA_SERVICES = "data-services"
    OTHER = "other"


@dataclass
class RepositoryNode:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    path: str = ""
    category: str = "other"
    language: str = ""
    description: str = ""
    url: str = ""
    default_branch: str = "main"
    file_count: int = 0
    total_lines: int = 0
    indexed_at: float | None = None
    last_commit: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CrossRepoDependency:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_repo: str = ""
    source_file: str = ""
    source_symbol: str = ""
    target_repo: str = ""
    target_file: str = ""
    target_symbol: str = ""
    relationship: str = "depends_on"
    weight: float = 1.0
    verified: bool = False
    detected_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OrgEntity:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    repo: str = ""
    file_path: str = ""
    entity_type: str = "class"
    name: str = ""
    full_name: str = ""
    line_start: int = 0
    line_end: int = 0
    docstring: str = ""
    imports: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    extends: list[str] = field(default_factory=list)
    implements: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Organization:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    repositories: dict[str, RepositoryNode] = field(default_factory=dict)
    dependencies: dict[str, CrossRepoDependency] = field(default_factory=dict)
    entities: dict[str, OrgEntity] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "repositories": [r.to_dict() for r in self.repositories.values()],
            "dependencies": [d.to_dict() for d in self.dependencies.values()],
            "entity_count": len(self.entities),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }


@dataclass
class ImpactReport:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    organization_id: str = ""
    query: str = ""
    affected_repos: list[str] = field(default_factory=list)
    affected_files: list[dict[str, Any]] = field(default_factory=list)
    affected_entities: list[dict[str, Any]] = field(default_factory=list)
    dependencies_traversed: list[dict[str, Any]] = field(default_factory=list)
    impact_score: float = 0.0
    risk_level: str = "low"
    recommendations: list[str] = field(default_factory=list)
    report_markdown: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


SUPPORTED_LANGUAGES = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".swift": "swift",
    ".kt": "kotlin",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".md": "markdown",
    ".sql": "sql",
    ".tf": "terraform",
    ".dockerfile": "docker",
}


REPO_CATEGORY_PATTERNS = {
    RepoCategory.FRONTEND: ["frontend", "web", "ui", "client"],
    RepoCategory.BACKEND: ["backend", "api", "server", "service"],
    RepoCategory.MOBILE: ["mobile", "ios", "android", "react-native", "flutter"],
    RepoCategory.INFRASTRUCTURE: ["infra", "terraform", "k8s", "kubernetes", "docker", "deploy"],
    RepoCategory.DOCUMENTATION: ["docs", "documentation", "wiki"],
    RepoCategory.SHARED_LIBRARIES: ["shared", "common", "lib", "library", "packages"],
    RepoCategory.DATA_SERVICES: ["data", "database", "etl", "analytics", "pipeline"],
}


class OrganizationGraph:
    def __init__(self, org_id: str = ""):
        self.org = Organization(id=org_id or str(uuid.uuid4()))
        self._lock = threading.Lock()
        self._loaded = False

    # ── Repository Management ───────────────────────────────────────────────────

    def add_repository(
        self, name: str, path: str, category: str = "", language: str = "", url: str = "", description: str = ""
    ) -> RepositoryNode:
        if not category:
            category = self._detect_category(name, path)
        repo = RepositoryNode(
            name=name,
            path=str(Path(path).resolve()) if path else "",
            category=category,
            language=language or self._detect_language(path),
            url=url,
            description=description,
        )
        with self._lock:
            self.org.repositories[repo.id] = repo
            self.org.updated_at = time.time()
        logger.info("Added repository: %s (%s)", name, category)
        self._save()
        return repo

    def remove_repository(self, repo_id: str) -> bool:
        with self._lock:
            if repo_id not in self.org.repositories:
                return False
            del self.org.repositories[repo_id]
            self.org.dependencies = {
                k: v for k, v in self.org.dependencies.items() if v.source_repo != repo_id and v.target_repo != repo_id
            }
            self.org.entities = {k: v for k, v in self.org.entities.items() if v.repo != repo_id}
            self.org.updated_at = time.time()
        self._save()
        return True

    def get_repository(self, repo_id: str) -> RepositoryNode | None:
        with self._lock:
            return self.org.repositories.get(repo_id)

    def list_repositories(self) -> list[RepositoryNode]:
        with self._lock:
            return list(self.org.repositories.values())

    def _detect_category(self, name: str, path: str) -> str:
        combined = f"{name} {path}".lower()
        for cat, patterns in REPO_CATEGORY_PATTERNS.items():
            if any(p in combined for p in patterns):
                return cat.value
        return "other"

    def _detect_language(self, path: str) -> str:
        repo_path = Path(path)
        if not repo_path.exists():
            return ""
        extensions = defaultdict(int)
        for f in repo_path.rglob("*"):
            if f.is_file() and f.suffix in SUPPORTED_LANGUAGES:
                extensions[SUPPORTED_LANGUAGES[f.suffix]] += 1
        if not extensions:
            return ""
        return max(extensions, key=extensions.get)

    # ── Repository Indexing ─────────────────────────────────────────────────────

    def index_repository(self, repo_id: str) -> dict[str, Any]:
        repo = self.get_repository(repo_id)
        if not repo:
            return {"error": f"Repository {repo_id} not found"}

        repo_path = Path(repo.path)
        if not repo_path.exists():
            return {"error": f"Path {repo.path} does not exist"}

        stats = {"files_scanned": 0, "entities_found": 0, "errors": []}

        for f in repo_path.rglob("*"):
            if not f.is_file():
                continue
            if f.suffix not in SUPPORTED_LANGUAGES:
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
                rel_path = str(f.relative_to(repo_path))
                entities = self._parse_entities(content, repo.name, rel_path, f.suffix)
                with self._lock:
                    for entity in entities:
                        self.org.entities[entity.id] = entity
                stats["entities_found"] += len(entities)
                stats["files_scanned"] += 1
            except Exception as exc:
                stats["errors"].append(f"Error parsing {f}: {exc}")

        with self._lock:
            repo.file_count = stats["files_scanned"]
            repo.indexed_at = time.time()
            self.org.updated_at = time.time()

        self._detect_dependencies()
        self._save()
        logger.info(
            "Indexed repo %s: %d files, %d entities", repo.name, stats["files_scanned"], stats["entities_found"]
        )
        return stats

    def _parse_entities(self, content: str, repo_name: str, rel_path: str, suffix: str) -> list[OrgEntity]:
        entities = []
        # Parse imports
        imports = []
        if suffix == ".py":
            for match in re.finditer(r"^(?:from\s+(\S+)\s+)?import\s+(\S+)", content, re.MULTILINE):
                if match.group(1):
                    imports.append(f"{match.group(1)}.{match.group(2)}")
                else:
                    imports.append(match.group(2))
        elif suffix in (".js", ".ts", ".tsx", ".jsx"):
            for match in re.finditer(
                r'(?:import\s+\S+\s+from\s+[\'"]([^\'"]+)[\'"]|require\([\'"]([^\'"]+)[\'"]\))', content
            ):
                imports.append(match.group(1) or match.group(2))

        # Parse classes
        class_patterns = {
            ".py": r"^class\s+(\w+)(?:\(([^)]*)\))?\s*:",
            ".java": r"^(?:public\s+)?(?:abstract\s+)?class\s+(\w+)",
            ".ts": r"^(?:export\s+)?(?:abstract\s+)?class\s+(\w+)",
            ".js": r"^class\s+(\w+)",
        }
        pattern = class_patterns.get(suffix, r"^class\s+(\w+)")
        for match in re.finditer(pattern, content, re.MULTILINE):
            line_no = content[: match.start()].count("\n") + 1
            class_name = match.group(1)
            extends = []
            if match.lastindex >= 2 and match.group(2):
                extends = [e.strip() for e in match.group(2).split(",") if e.strip() and not e.strip().startswith("_")]

            # Find docstring
            docstring = ""
            doc_match = re.search(r'"""(.*?)"""', content[match.end() :], re.DOTALL)
            if doc_match:
                docstring = doc_match.group(1).strip()

            entity = OrgEntity(
                repo=repo_name,
                file_path=rel_path,
                entity_type="class",
                name=class_name,
                full_name=f"{repo_name}/{rel_path}::{class_name}",
                line_start=line_no,
                imports=list(imports),
                extends=extends,
                docstring=docstring[:200],
            )
            entities.append(entity)

        # Parse functions
        func_patterns = {
            ".py": r"^(?:async\s+)?def\s+(\w+)\s*\(",
            ".js": r"^(?:async\s+)?(?:export\s+)?(?:function\s+(\w+)|const\s+(\w+)\s*=\s*(?:async\s+)?\(|const\s+(\w+)\s*=\s*function)",
            ".ts": r"^(?:async\s+)?(?:export\s+)?(?:function\s+(\w+)|const\s+(\w+)\s*=\s*(?:async\s+)?\()",
            ".java": r"^(?:public|private|protected)\s+\S+\s+(\w+)\s*\(",
        }
        func_pattern = func_patterns.get(suffix, r"^(?:async\s+)?def\s+(\w+)\s*\(")
        for match in re.finditer(func_pattern, content, re.MULTILINE):
            line_no = content[: match.start()].count("\n") + 1
            func_name = next(g for g in match.groups() if g)

            # Skip if inside a class (handled above)
            class_line = max(
                [0] + [content[: match.start()].rfind("\nclass "), content[: match.start()].rfind("\nclass\t")]
            )
            if class_line > 0:
                after_class = content[class_line : match.start()]
                if after_class.count("\n") < 50:
                    continue

            entity = OrgEntity(
                repo=repo_name,
                file_path=rel_path,
                entity_type="function",
                name=func_name,
                full_name=f"{repo_name}/{rel_path}::{func_name}",
                line_start=line_no,
                imports=list(imports),
            )
            entities.append(entity)

        return entities

    # ── Dependency Detection ────────────────────────────────────────────────────

    def _detect_dependencies(self) -> None:
        with self._lock:
            entities = list(self.org.entities.values())
            repos = {r.name: r.id for r in self.org.repositories.values()}

        new_deps: dict[str, CrossRepoDependency] = {}

        for entity in entities:
            if entity.entity_type != "class":
                continue
            for ext in entity.extends:
                dep = self._find_cross_repo_dependency(
                    entity.repo, entity.file_path, entity.name, ext, repos, entities, "extends"
                )
                if dep:
                    new_deps[dep.id] = dep
            for imp in entity.imports:
                dep = self._find_cross_repo_dependency(
                    entity.repo, entity.file_path, entity.name, imp, repos, entities, "imports"
                )
                if dep:
                    new_deps[dep.id] = dep

        with self._lock:
            self.org.dependencies.update(new_deps)
            self.org.updated_at = time.time()

    def _find_cross_repo_dependency(
        self,
        source_repo: str,
        source_file: str,
        source_symbol: str,
        target_text: str,
        repos: dict[str, str],
        entities: list[OrgEntity],
        rel_type: str,
    ) -> CrossRepoDependency | None:
        target_repo = ""
        target_file = ""
        target_symbol = ""

        # Check if target contains a repo name
        for rname in repos:
            if rname.lower() in target_text.lower():
                target_repo = rname
                break

        if not target_repo:
            return None

        # Don't create self-dependencies
        if target_repo == source_repo:
            return None

        # Try to find matching entity in target repo
        for ent in entities:
            if ent.repo == target_repo and (
                ent.name.lower() in target_text.lower() or target_text.lower() in ent.name.lower()
            ):
                target_file = ent.file_path
                target_symbol = ent.name
                break

        dep = CrossRepoDependency(
            source_repo=source_repo,
            source_file=source_file,
            source_symbol=source_symbol,
            target_repo=target_repo,
            target_file=target_file or target_text,
            target_symbol=target_symbol or target_text.split(".")[-1],
            relationship=rel_type,
        )
        return dep

    def add_manual_dependency(
        self,
        source_repo: str,
        target_repo: str,
        relationship: str = "depends_on",
        weight: float = 1.0,
    ) -> CrossRepoDependency:
        dep = CrossRepoDependency(
            source_repo=source_repo,
            target_repo=target_repo,
            relationship=relationship,
            weight=weight,
            verified=True,
        )
        with self._lock:
            self.org.dependencies[dep.id] = dep
            self.org.updated_at = time.time()
        self._save()
        return dep

    # ── Impact Analysis ─────────────────────────────────────────────────────────

    def analyze_impact(self, query: str) -> ImpactReport:
        report = ImpactReport(
            organization_id=self.org.id,
            query=query,
        )

        keywords = self._extract_keywords(query)

        with self._lock:
            repos = list(self.org.repositories.values())
            entities = list(self.org.entities.values())
            deps = list(self.org.dependencies.values())

        affected_repos: set[str] = set()
        affected_files: list[dict] = []
        affected_entities: list[dict] = []
        deps_traversed: list[dict] = []

        # Phase 1: Find direct matches
        for entity in entities:
            match_score = self._match_keywords(entity, keywords)
            if match_score > 0:
                affected_repos.add(entity.repo)
                affected_entities.append(entity.to_dict())
                affected_files.append(
                    {
                        "repo": entity.repo,
                        "file": entity.file_path,
                        "entity": entity.name,
                        "type": entity.entity_type,
                        "match_score": match_score,
                    }
                )

        # Phase 2: Find dependencies of matched entities
        matched_symbols = {e["entity"] for e in affected_entities}
        matched_repos = set(affected_repos)

        for dep in deps:
            if dep.source_repo in matched_repos or dep.target_repo in matched_repos:
                deps_traversed.append(dep.to_dict())
                affected_repos.add(dep.source_repo)
                affected_repos.add(dep.target_repo)
                if dep.source_symbol in matched_symbols or dep.target_symbol in matched_symbols:
                    weight = dep.weight * 0.8
                    affected_files.append(
                        {
                            "repo": dep.target_repo,
                            "file": dep.target_file,
                            "entity": dep.target_symbol,
                            "type": "dependency",
                            "match_score": weight,
                        }
                    )

        # Phase 3: Find tests and docs for affected repos
        for entity in entities:
            if entity.repo in affected_repos:
                if "test" in entity.file_path.lower():
                    affected_files.append(
                        {
                            "repo": entity.repo,
                            "file": entity.file_path,
                            "entity": entity.name,
                            "type": "test",
                            "match_score": 0.5,
                        }
                    )
                if "doc" in entity.file_path.lower() or entity.file_path.endswith(".md"):
                    affected_files.append(
                        {
                            "repo": entity.repo,
                            "file": entity.file_path,
                            "entity": entity.name,
                            "type": "documentation",
                            "match_score": 0.3,
                        }
                    )

        # Phase 4: Find infrastructure files
        for repo in repos:
            if repo.name in affected_repos:
                if repo.category in ("infrastructure", "deploy"):
                    affected_files.append(
                        {
                            "repo": repo.name,
                            "file": "deployment/",
                            "entity": repo.name,
                            "type": "infrastructure",
                            "match_score": 0.4,
                        }
                    )

        report.affected_repos = list(affected_repos)
        report.affected_files = affected_files
        report.affected_entities = affected_entities
        report.dependencies_traversed = deps_traversed

        # Calculate impact score
        report.impact_score = min(100.0, len(affected_repos) * 10.0 + len(affected_files) * 2.0)

        # Determine risk level
        if report.impact_score >= 70 or len(affected_repos) >= 4:
            report.risk_level = "high"
        elif report.impact_score >= 40 or len(affected_repos) >= 2:
            report.risk_level = "medium"
        else:
            report.risk_level = "low"

        # Generate recommendations
        report.recommendations = self._generate_recommendations(affected_repos, deps_traversed, report.risk_level)

        # Generate markdown report
        report.report_markdown = self._generate_impact_markdown(report)

        self._save_impact_report(report)
        logger.info(
            "Impact analysis: query='%s' Score=%.1f Risk=%s Repos=%d",
            query,
            report.impact_score,
            report.risk_level,
            len(affected_repos),
        )
        return report

    def _extract_keywords(self, query: str) -> list[str]:
        keywords = re.findall(r"\b[a-zA-Z_]\w+\b", query.lower())
        stopwords = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "has",
            "have",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "can",
            "shall",
            "to",
            "of",
            "in",
            "for",
            "on",
            "with",
            "at",
            "by",
            "from",
            "as",
            "into",
            "through",
            "during",
            "before",
            "after",
            "above",
            "below",
            "between",
            "out",
            "off",
            "over",
            "under",
            "again",
            "further",
            "then",
            "once",
            "here",
            "there",
            "when",
            "where",
            "why",
            "how",
            "all",
            "each",
            "every",
            "both",
            "few",
            "more",
            "most",
            "other",
            "some",
            "such",
            "no",
            "nor",
            "not",
            "only",
            "own",
            "same",
            "so",
            "than",
            "too",
            "very",
            "just",
            "because",
            "but",
            "and",
            "or",
            "if",
            "while",
            "about",
            "up",
            "it",
            "its",
            "this",
            "that",
            "these",
            "those",
            "i",
            "me",
            "my",
            "we",
            "our",
            "you",
            "your",
            "he",
            "him",
            "his",
            "she",
            "her",
            "they",
            "them",
            "their",
            "what",
            "which",
            "who",
            "whom",
            "change",
            "modify",
            "update",
            "add",
            "remove",
            "delete",
            "fix",
            "implement",
            "need",
            "want",
            "please",
            "make",
            "create",
            "new",
        }
        return [k for k in keywords if k not in stopwords and len(k) > 2][:20]

    def _match_keywords(self, entity: OrgEntity, keywords: list[str]) -> float:
        text = f"{entity.name} {entity.file_path} {entity.docstring} {' '.join(entity.imports)} {' '.join(entity.extends)}".lower()
        score = 0.0
        for kw in keywords:
            if kw in text:
                score += 1.0
            if kw in entity.name.lower():
                score += 2.0
        return score / max(len(keywords), 1)

    def _generate_recommendations(self, affected_repos: set[str], deps: list[dict], risk: str) -> list[str]:
        recommendations = []
        if len(affected_repos) == 1:
            recommendations.append(f"Change is contained to 1 repository: {list(affected_repos)[0]}")
        else:
            recommendations.append(f"Change affects {len(affected_repos)} repositories. Coordinate across teams.")

        recommendations.append("Run cross-repo validation after applying changes")
        recommendations.append("Update shared library versions if modifying common interfaces")
        recommendations.append("Verify API contracts between frontend and backend")

        if risk == "high":
            recommendations.append("HIGH RISK: Consider phased rollout with feature flags")
            recommendations.append("Schedule change during low-traffic period")
            recommendations.append("Prepare rollback plan before deployment")

        if any("test" in str(d) for d in deps):
            recommendations.append("Run full integration test suite before merge")

        return recommendations

    def _generate_impact_markdown(self, report: ImpactReport) -> str:
        lines = [
            "# Impact Analysis Report",
            "",
            f"**Query:** {report.query}",
            f"**Impact Score:** {report.impact_score:.1f}/100",
            f"**Risk Level:** {report.risk_level.upper()}",
            f"**Affected Repositories:** {len(report.affected_repos)}",
            f"**Affected Files:** {len(report.affected_files)}",
            f"**Generated:** {datetime.now(UTC).isoformat()}",
            "",
            "## Affected Repositories",
            "",
        ]
        for repo in sorted(report.affected_repos):
            lines.append(f"- {repo}")

        lines.extend(["", "## Affected Files", ""])
        for f in report.affected_files[:30]:
            lines.append(f"- `{f['repo']}/{f['file']}` ({f['type']}, score: {f['match_score']:.1f})")

        if report.affected_entities:
            lines.extend(["", "## Affected Entities", ""])
            for e in report.affected_entities[:20]:
                lines.append(f"- `{e['full_name']}` ({e['entity_type']})")

        if report.dependencies_traversed:
            lines.extend(["", "## Cross-Repo Dependencies Traversed", ""])
            for d in report.dependencies_traversed[:15]:
                lines.append(f"- {d['source_repo']} -> {d['target_repo']} ({d['relationship']})")

        lines.extend(["", "## Recommendations", ""])
        for r in report.recommendations:
            lines.append(f"- {r}")

        return "\n".join(lines)

    # ── Persistence ─────────────────────────────────────────────────────────────

    def _save(self) -> None:
        try:
            org_file = ORG_DATA_DIR / f"org_{self.org.id[:8]}.json"
            data = self.org.to_dict()
            data["entities"] = [e.to_dict() for e in self.org.entities.values()]
            org_file.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        except Exception as exc:
            logger.warning("Save org failed: %s", exc)

    def _save_impact_report(self, report: ImpactReport) -> None:
        try:
            report_dir = ORG_DATA_DIR / "impact_reports"
            report_dir.mkdir(parents=True, exist_ok=True)
            report_file = report_dir / f"impact_{report.id[:8]}.json"
            report_file.write_text(json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8")
        except Exception as exc:
            logger.warning("Save impact report failed: %s", exc)

    def get_impact_report(self, report_id: str) -> ImpactReport | None:
        report_dir = ORG_DATA_DIR / "impact_reports"
        for f in report_dir.glob("*.json"):
            if report_id in f.stem:
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    return ImpactReport(**data)
                except Exception as exc:
                    logger.warning("Load impact report failed: %s", exc)
        return None

    def list_impact_reports(self, limit: int = 20) -> list[dict]:
        report_dir = ORG_DATA_DIR / "impact_reports"
        if not report_dir.exists():
            return []
        reports = []
        for f in sorted(report_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                reports.append(
                    {
                        "id": data.get("id", ""),
                        "query": data.get("query", ""),
                        "impact_score": data.get("impact_score", 0),
                        "risk_level": data.get("risk_level", ""),
                        "affected_repos": data.get("affected_repos", []),
                        "created_at": data.get("created_at", 0),
                    }
                )
            except Exception:
                continue
        return reports

    def get_graph_data(self) -> dict[str, Any]:
        """Return graph visualization data."""
        with self._lock:
            repos = list(self.org.repositories.values())
            deps = list(self.org.dependencies.values())

        nodes = [
            {
                "id": r.id[:8],
                "label": r.name,
                "category": r.category,
                "file_count": r.file_count,
                "size": max(10, min(50, r.file_count // 10 + 5)),
            }
            for r in repos
        ]

        edges = [
            {
                "source": d.source_repo,
                "target": d.target_repo,
                "label": d.relationship,
                "weight": d.weight,
            }
            for d in deps
        ]

        return {"nodes": nodes, "edges": edges}

    def get_health(self) -> dict[str, Any]:
        with self._lock:
            repo_count = len(self.org.repositories)
            dep_count = len(self.org.dependencies)
            entity_count = len(self.org.entities)

        indexed_count = sum(1 for r in self.org.repositories.values() if r.indexed_at)
        return {
            "organization_id": self.org.id,
            "organization_name": self.org.name,
            "repository_count": repo_count,
            "indexed_count": indexed_count,
            "dependency_count": dep_count,
            "entity_count": entity_count,
            "health_score": min(
                100.0, (indexed_count / max(repo_count, 1)) * 50.0 + (dep_count / max(repo_count, 1)) * 25.0 + 25.0
            ),
        }


class OrgGraphAnalyzer:
    def __init__(self, graph: OrganizationGraph):
        self.graph = graph

    def find_shared_dependencies(self) -> list[dict[str, Any]]:
        """Find libraries/shared components that multiple repos depend on."""
        dep_map = defaultdict(list)
        for dep in self.graph.org.dependencies.values():
            dep_map[dep.target_repo].append(dep.source_repo)

        shared = []
        for target, sources in dep_map.items():
            if len(sources) >= 2:
                shared.append(
                    {
                        "target": target,
                        "sources": sources,
                        "count": len(sources),
                    }
                )
        return sorted(shared, key=lambda x: x["count"], reverse=True)

    def find_orphan_repos(self) -> list[str]:
        """Find repos with no dependencies to or from other repos."""
        all_repos = {r.name for r in self.graph.org.repositories.values()}
        connected = set()
        for dep in self.graph.org.dependencies.values():
            connected.add(dep.source_repo)
            connected.add(dep.target_repo)
        return list(all_repos - connected)

    def find_critical_path(self) -> list[str]:
        """Find the most depended-upon repos (single points of failure)."""
        dep_count = defaultdict(int)
        for dep in self.graph.org.dependencies.values():
            dep_count[dep.target_repo] += 1
        return sorted(dep_count, key=dep_count.get, reverse=True)


# ── Singleton ──────────────────────────────────────────────────────────────────

_org_graphs: dict[str, OrganizationGraph] = {}
_org_lock = threading.Lock()


def create_organization(name: str, description: str = "") -> OrganizationGraph:
    graph = OrganizationGraph()
    graph.org.name = name
    graph.org.description = description
    with _org_lock:
        _org_graphs[graph.org.id] = graph
    graph._save()
    logger.info("Created organization: %s (%s)", name, graph.org.id[:8])
    return graph


def get_organization(org_id: str) -> OrganizationGraph | None:
    with _org_lock:
        if org_id in _org_graphs:
            return _org_graphs[org_id]
    # Try loading from disk
    org_file = ORG_DATA_DIR / f"org_{org_id[:8]}.json"
    if org_file.exists():
        try:
            graph = OrganizationGraph(org_id=org_id)
            data = json.loads(org_file.read_text(encoding="utf-8"))
            graph.org.name = data.get("name", "")
            graph.org.description = data.get("description", "")
            for rdata in data.get("repositories", []):
                repo = RepositoryNode(**rdata)
                graph.org.repositories[repo.id] = repo
            for ddata in data.get("dependencies", []):
                dep = CrossRepoDependency(**ddata)
                graph.org.dependencies[dep.id] = dep
            for edata in data.get("entities", []):
                entity = OrgEntity(**edata)
                graph.org.entities[entity.id] = entity
            graph.org.created_at = data.get("created_at", time.time())
            graph.org.updated_at = data.get("updated_at", time.time())
            with _org_lock:
                _org_graphs[graph.org.id] = graph
            logger.info("Loaded organization: %s (%s)", graph.org.name, graph.org.id[:8])
            return graph
        except Exception as exc:
            logger.warning("Failed to load org %s: %s", org_id, exc)
    return None


def list_organizations() -> list[dict[str, Any]]:
    orgs = []
    for f in ORG_DATA_DIR.glob("org_*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            orgs.append(
                {
                    "id": data.get("id", ""),
                    "name": data.get("name", ""),
                    "description": data.get("description", ""),
                    "repo_count": len(data.get("repositories", [])),
                    "entity_count": data.get("entity_count", 0),
                    "created_at": data.get("created_at", 0),
                }
            )
        except Exception:
            continue
    return sorted(orgs, key=lambda x: x.get("created_at", 0), reverse=True)


def get_org_graph_service() -> OrganizationGraph:
    """Get or create a default organization graph for backward compatibility."""
    orgs = list_organizations()
    if orgs:
        graph = get_organization(orgs[0]["id"])
        if graph:
            return graph
    return create_organization("default-org", "Auto-created default organization")
