"""Repository Analyzer Service — deep analysis and automated PR generation.

Workflow:
  1. Clone or open repository
  2. Detect language/framework
  3. Build architecture model + dependency graph
  4. Run static analysis (code smells, security, quality)
  5. Generate missing tests
  6. Generate fixes for detected issues
  7. Run validation (syntax + tests)
  8. Commit changes to a new branch
  9. Create pull request via GitHub API
"""
import logging
import os
import re
import subprocess
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from services.llm_service import call_model

logger = logging.getLogger(__name__)

REPO_WORK_DIR = Path(os.getenv("REPO_WORK_DIR", "./repo_analysis"))
MAX_FILE_SIZE = int(os.getenv("REPO_MAX_FILE_SIZE", "50000"))
SUPPORTED_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".json", ".yaml", ".yml"}

_FRAMEWORK_PATTERNS: dict[str, list[str]] = {
    "FastAPI": ["from fastapi import", "from fastapi.", "FastAPI()"],
    "Flask": ["from flask import", "from flask.", "Flask("],
    "Django": ["from django.", "django.urls", "django.conf"],
    "React": ["from react", "import React", "react-dom"],
    "Next.js": ["next/link", "next/image", "next/router"],
    "Vue": ["from vue", "import Vue", "createApp("],
    "Express": ["express()", "from express", "require('express')"],
    "Spring": ["@SpringBootApplication", "@RestController", "import org.springframework"],
}

_CLANG_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx"}


def analyze_repository(repo_path: str, job_id: str | None = None, model: str = "local") -> dict[str, Any]:
    path = Path(repo_path)
    if not path.exists():
        raise FileNotFoundError(f"Repository path not found: {repo_path}")

    results = {}
    results["repo_path"] = str(path.resolve())
    results["job_id"] = job_id or str(uuid.uuid4())

    files = _scan_files(path)
    results["file_count"] = len(files)
    results["languages"] = _detect_languages(files)

    framework = _detect_framework(files)
    results["framework"] = framework

    dep_graph = _build_dependency_graph(files, path)
    results["dependency_graph"] = dep_graph

    architecture = _analyze_architecture(files, framework, dep_graph)
    results["architecture"] = architecture

    code_smells = _detect_code_smells(files, path)
    results["code_smells"] = code_smells

    security = _detect_security_issues(files, path)
    results["security_issues"] = security

    quality = _assess_quality(files, path)
    results["quality"] = quality

    coverage = _assess_test_coverage(files)
    results["test_coverage"] = coverage

    results["summary"] = _generate_summary(architecture, code_smells, security, quality, coverage)

    _write_report(path, "architecture_report.md", _format_architecture_report(results))
    _write_report(path, "security_report.md", _format_security_report(security))
    _write_report(path, "quality_report.md", _format_quality_report(quality, code_smells))
    _write_report(path, "test_coverage_report.md", _format_coverage_report(coverage))

    logger.info("Repository analysis complete for %s: %d files, %d issues", repo_path, len(files), len(code_smells) + len(security))
    return results


def improve_repository(
    repo_path: str,
    model: str = "local",
    job_id: str | None = None,
    auto_fix: bool = True,
    generate_tests: bool = True,
) -> dict[str, Any]:
    analysis = analyze_repository(repo_path, job_id=job_id, model=model)
    path = Path(repo_path)
    changes = {"fixed_files": [], "new_tests": [], "errors": []}

    if auto_fix:
        for issue in analysis.get("code_smells", []):
            try:
                fixed = _apply_llm_fix(path, issue, model)
                if fixed:
                    changes["fixed_files"].append(fixed)
            except Exception as exc:
                changes["errors"].append({"file": issue.get("file", ""), "error": str(exc)[:200]})

    files = _scan_files(path)
    if generate_tests:
        missing = _find_missing_tests(files)
        for src_file in missing:
            try:
                new_test = _generate_test_file(path, src_file, model)
                if new_test:
                    changes["new_tests"].append(new_test)
            except Exception as exc:
                changes["errors"].append({"file": src_file, "error": str(exc)[:200]})

    validation = _run_validation(path)
    changes["validation"] = validation
    changes["analysis"] = analysis
    return changes


def create_pr(
    repo_path: str,
    github_token: str,
    repo_full_name: str,
    branch_name: str = "auto-improve",
    base_branch: str = "main",
    title: str = "Automated code quality improvements",
    body: str = "AI-driven improvements including fixes, tests, and documentation.",
    model: str = "local",
) -> dict[str, Any]:
    from services.github_service import create_branch, create_pull_request

    path = Path(repo_path)
    if not path.exists():
        raise FileNotFoundError(f"Repository not found locally: {repo_path}")

    analysis = analyze_repository(path, model=model)
    changes = improve_repository(path, model=model)

    try:
        create_branch(github_token, repo_full_name, branch_name, base_branch)
    except Exception as exc:
        logger.warning("Branch may already exist: %s", exc)
        pass

    _git_commit_and_push(path, branch_name, title)

    try:
        pr = create_pull_request(github_token, repo_full_name, title, branch_name, base_branch, body)
    except Exception as exc:
        pr = {"error": str(exc)[:300], "html_url": ""}

    return {
        "branch": branch_name,
        "pull_request": pr,
        "changes": changes,
        "analysis": analysis,
    }


def _scan_files(path: Path) -> dict[str, str]:
    files = {}
    for fp in sorted(path.rglob("*")):
        if not fp.is_file():
            continue
        if any(p.startswith(".") for p in fp.parts):
            continue
        if "__pycache__" in str(fp) or "node_modules" in str(fp) or ".git" in str(fp):
            continue
        if fp.suffix not in SUPPORTED_EXTENSIONS:
            continue
        if fp.stat().st_size > MAX_FILE_SIZE:
            continue
        try:
            rel = str(fp.relative_to(path))
            files[rel] = fp.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass
    return files


def _detect_languages(files: dict[str, str]) -> dict[str, int]:
    ext_count: dict[str, int] = defaultdict(int)
    for name in files:
        ext = Path(name).suffix
        if ext:
            ext_count[ext] += 1
    lang_map = {".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
                ".jsx": "React JSX", ".tsx": "React TSX", ".html": "HTML",
                ".css": "CSS", ".json": "JSON", ".yaml": "YAML", ".yml": "YAML"}
    return {lang_map.get(k, k): v for k, v in sorted(ext_count.items(), key=lambda x: -x[1])}


def _detect_framework(files: dict[str, str]) -> str | None:
    for name, content in files.items():
        for framework, patterns in _FRAMEWORK_PATTERNS.items():
            for pattern in patterns:
                if pattern in content:
                    return framework
    return None


def _build_dependency_graph(files: dict[str, str], base_path: Path) -> dict[str, list[str]]:
    graph: dict[str, list[str]] = {}
    for name, content in files.items():
        deps = []
        ext = Path(name).suffix
        if ext == ".py":
            for m in re.finditer(r'(?:import|from)\s+(\S+)', content):
                mod = m.group(1).split(".")[0]
                if mod and mod not in ("os", "sys", "re", "json", "typing", "datetime", "pathlib"):
                    deps.append(mod)
        elif ext in (".js", ".ts", ".jsx", ".tsx"):
            for m in re.finditer(r'(?:import|require)\s*\(?\s*[\'"](\S+)[\'"]', content):
                dep = m.group(1).split("/")[0]
                if dep and not dep.startswith("."):
                    deps.append(dep)
        graph[name] = list(set(deps))
    return graph


def _analyze_architecture(files: dict[str, str], framework: str | None, dep_graph: dict[str, list[str]]) -> dict:
    folders = defaultdict(list)
    for name in files:
        parts = name.split("/")
        parent = parts[0] if len(parts) > 1 else "root"
        folders[parent].append(name)

    has_tests = any("test" in f.lower() or f.startswith("tests/") for f in files)
    has_docs = any(f.endswith(".md") for f in files)
    has_config = any(f in ("requirements.txt", "package.json", "pyproject.toml", "tsconfig.json") for f in files)

    return {
        "framework": framework,
        "folders": {k: len(v) for k, v in sorted(folders.items())},
        "has_tests": has_tests,
        "has_docs": has_docs,
        "has_config": has_config,
        "total_files": len(files),
        "entry_points": _find_entry_points(files, framework),
    }


def _find_entry_points(files: dict[str, str], framework: str | None) -> list[str]:
    candidates = []
    for name in files:
        if "main" in name or "app" in name:
            candidates.append(name)
    return candidates[:5]


def _detect_code_smells(files: dict[str, str], base_path: Path) -> list[dict]:
    smells = []
    for name, content in files.items():
        ext = Path(name).suffix
        if ext not in _CLANG_EXTENSIONS:
            continue
        lines = content.split("\n")
        if len(lines) > 300:
            smells.append({"file": name, "line": 1, "type": "large_file", "severity": "medium",
                           "message": f"File has {len(lines)} lines. Consider splitting into smaller modules."})
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if len(stripped) > 150:
                smells.append({"file": name, "line": i, "type": "long_line", "severity": "low",
                               "message": f"Line has {len(stripped)} characters. Max recommended: 120."})
            if stripped.startswith("def ") or stripped.startswith("class "):
                if i > 1 and lines[i - 2].strip() and not lines[i - 2].strip().startswith("#"):
                    pass
            if ext == ".py":
                if "TODO" in stripped or "FIXME" in stripped or "HACK" in stripped:
                    smells.append({"file": name, "line": i, "type": "todo_comment", "severity": "low",
                                   "message": stripped.strip()})
                if "print(" in stripped and not stripped.startswith("#"):
                    smells.append({"file": name, "line": i, "type": "debug_print", "severity": "low",
                                   "message": "Debug print statement in production code."})
                if "try:" in stripped:
                    # Check for bare except
                    pass
        # Check for bare except
        for m in re.finditer(r'except\s*:', content):
            line_num = content[:m.start()].count("\n") + 1
            smells.append({"file": name, "line": line_num, "type": "bare_except", "severity": "high",
                           "message": "Bare except clause catches all exceptions. Specify exception types."})
    return smells


def _detect_security_issues(files: dict[str, str], base_path: Path) -> list[dict]:
    issues = []
    patterns = [
        ("hardcoded_secret", r"(?:api_key|secret|password|token)\s*=\s*['\"][A-Za-z0-9_\-]{16,}['\"]", "high"),
        ("sql_injection", r"execute\([^)]*['\"].*\{.*['\"]", "high"),
        ("eval_usage", r"\beval\s*\(", "high"),
        ("exec_usage", r"\bexec\s*\(", "high"),
        ("pickle_load", r"pickle\.loads?\(", "high"),
        ("debug_enabled", r"debug\s*=\s*True", "medium"),
        ("dangerous_default", r"def \w+\(.*=\s*\[\s*\]", "medium"),
        ("dangerous_default_dict", r"def \w+\(.*=\s*\{\s*\}", "medium"),
    ]
    for name, content in files.items():
        for issue_type, pattern, severity in patterns:
            for m in re.finditer(pattern, content):
                line_num = content[:m.start()].count("\n") + 1
                issues.append({
                    "file": name, "line": line_num, "type": issue_type,
                    "severity": severity, "message": f"Potential {issue_type.replace('_', ' ')} detected.",
                })
    return issues


def _assess_quality(files: dict[str, str], base_path: Path) -> dict:
    docstring_count = 0
    function_count = 0
    class_count = 0
    for name, content in files.items():
        ext = Path(name).suffix
        if ext == ".py":
            function_count += len(re.findall(r'^\s*def ', content, re.MULTILINE))
            class_count += len(re.findall(r'^\s*class ', content, re.MULTILINE))
            docstring_count += len(re.findall(r'"""', content)) // 2
    return {
        "total_functions": function_count,
        "total_classes": class_count,
        "docstring_blocks": docstring_count,
        "documentation_ratio": round(docstring_count / max(function_count, 1), 2),
    }


def _assess_test_coverage(files: dict[str, str]) -> dict:
    source_files = [f for f in files if not f.startswith("tests/") and not f.startswith("test_")]
    test_files = [f for f in files if f.startswith("tests/") or f.startswith("test_")]
    return {
        "source_files": len(source_files),
        "test_files": len(test_files),
        "test_ratio": round(len(test_files) / max(len(source_files), 1), 2),
        "needs_improvement": len(test_files) < max(len(source_files) // 3, 1),
    }


def _find_missing_tests(files: dict[str, str]) -> list[str]:
    source_files = [f for f in files if not f.startswith("tests/") and not f.startswith("test_")]
    test_files = {f.replace("tests/", "").replace("test_", "") for f in files if f.startswith("tests/") or f.startswith("test_")}
    missing = []
    for sf in source_files:
        stem = Path(sf).stem
        if stem not in test_files and f"test_{stem}" not in test_files:
            if Path(sf).suffix in _CLANG_EXTENSIONS:
                missing.append(sf)
    return missing


def _generate_test_file(base_path: Path, src_file: str, model: str) -> str | None:
    src_path = base_path / src_file
    if not src_path.exists():
        return None
    content = src_path.read_text(encoding="utf-8")[:8000]
    ext = Path(src_file).suffix
    test_ext = ext

    test_file = f"test_{Path(src_file).stem}{test_ext}"
    test_dir = base_path / "tests"
    test_dir.mkdir(exist_ok=True)
    test_path = test_dir / test_file

    prompt = (
        f"Generate a comprehensive test file for the following {ext} source code.\n\n"
        f"Source file: {src_file}\n\n"
        f"```{ext}\n{content}\n```\n\n"
        f"Return ONLY the complete test file content with no markdown fences. "
        f"Include imports, test fixtures, and edge cases."
    )
    system = f"You are an expert test engineer. Generate thorough unit tests for {ext} files using the appropriate testing framework."

    try:
        test_code = call_model(prompt, system_prompt=system, model=model, agent="RepoAnalyzer")
        test_code = re.sub(r"^```[\w]*\n?", "", test_code).strip()
        test_code = re.sub(r"\n```$", "", test_code).strip()
        if len(test_code) > 50:
            test_path.write_text(test_code, encoding="utf-8")
            return str(test_path.relative_to(base_path))
    except Exception as exc:
        logger.warning("Test generation failed for %s: %s", src_file, exc)
    return None


def _apply_llm_fix(base_path: Path, issue: dict, model: str) -> str | None:
    file_path = base_path / issue.get("file", "")
    if not file_path.exists():
        return None
    content = file_path.read_text(encoding="utf-8")
    prompt = (
        f"Fix the following code issue in {issue['file']}.\n\nIssue: {issue['message']}\n"
        f"Severity: {issue['severity']}\nLine: {issue['line']}\n\n"
        f"Current code:\n```\n{content}\n```\n\n"
        f"Return the COMPLETE fixed file with no markdown fences."
    )
    system = "You are an expert code reviewer and fixer. Fix the issue while preserving all existing functionality."
    try:
        fixed = call_model(prompt, system_prompt=system, model=model, agent="RepoAnalyzer")
        fixed = re.sub(r"^```[\w]*\n?", "", fixed).strip()
        fixed = re.sub(r"\n```$", "", fixed).strip()
        if len(fixed) > 50 and fixed != content:
            file_path.write_text(fixed, encoding="utf-8")
            return issue["file"]
    except Exception as exc:
        logger.warning("Fix failed for %s: %s", issue.get("file"), exc)
    return None


def _run_validation(base_path: Path) -> dict:
    result = {"syntax_ok": True, "tests_passed": None, "errors": []}
    # Syntax check Python files
    for fp in base_path.rglob("*.py"):
        if "__pycache__" in str(fp):
            continue
        try:
            compile(fp.read_text(encoding="utf-8"), str(fp), "exec")
        except SyntaxError as exc:
            result["syntax_ok"] = False
            result["errors"].append({"file": str(fp.relative_to(base_path)), "error": str(exc)})
    # Run pytest if exists
    test_dir = base_path / "tests" if (base_path / "tests").exists() else base_path
    test_files = list(test_dir.rglob("test_*.py"))
    if test_files:
        try:
            r = subprocess.run(["python", "-m", "pytest", str(test_dir), "-x", "--tb=short", "-q"],
                               capture_output=True, text=True, timeout=120, cwd=str(base_path))
            result["tests_passed"] = r.returncode == 0
            result["test_output"] = r.stdout[-1000:] + r.stderr[-1000:]
        except Exception as exc:
            result["tests_passed"] = False
            result["errors"].append({"error": str(exc)[:200]})
    return result


def _git_commit_and_push(path: Path, branch: str, message: str):
    try:
        subprocess.run(["git", "add", "-A"], cwd=str(path), capture_output=True, text=True, timeout=30)
        subprocess.run(["git", "commit", "-m", message], cwd=str(path), capture_output=True, text=True, timeout=30)
        subprocess.run(["git", "push", "origin", branch], cwd=str(path), capture_output=True, text=True, timeout=120)
    except Exception as exc:
        logger.warning("Git commit/push failed: %s", exc)


def _generate_summary(architecture: dict, code_smells: list, security: list, quality: dict, coverage: dict) -> str:
    parts = [
        "# Repository Analysis Summary",
        "",
        f"**Framework:** {architecture.get('framework', 'Unknown')}",
        f"**Total files:** {architecture.get('total_files', 0)}",
        f"**Test coverage:** {coverage.get('test_ratio', 0):.0%}",
        f"**Documentation ratio:** {quality.get('documentation_ratio', 0):.0%}",
        "",
        "## Issues Found",
        f"- Code smells: {len(code_smells)}",
        f"- Security issues: {len(security)}",
        f"- Functions: {quality.get('total_functions', 0)}",
        f"- Classes: {quality.get('total_classes', 0)}",
        f"- Docstrings: {quality.get('docstring_blocks', 0)}",
        "",
        "## Recommendations",
    ]
    if coverage.get("needs_improvement"):
        parts.append("- Add more tests to improve coverage")
    if code_smells:
        parts.append(f"- Address {len(code_smells)} code smell(s)")
    if security:
        parts.append(f"- Fix {len(security)} security issue(s)")
    return "\n".join(parts)


def _format_architecture_report(results: dict) -> str:
    arch = results.get("architecture", {})
    deps = results.get("dependency_graph", {})
    lines = [
        "# Architecture Report",
        f"**Generated:** {datetime.utcnow().isoformat()}",
        f"**Files analyzed:** {results.get('file_count', 0)}",
        f"**Framework:** {arch.get('framework', 'Unknown')}",
        "",
        "## Project Structure",
        "",
        "| Directory | Files |",
        "|-----------|-------|",
    ]
    for folder, count in arch.get("folders", {}).items():
        lines.append(f"| {folder} | {count} |")
    lines.extend([
        "",
        "## Entry Points",
    ])
    for ep in arch.get("entry_points", []):
        lines.append(f"- `{ep}`")
    lines.extend(["", "## Dependency Graph (top 20)", ""])
    top_deps = sorted(deps.items(), key=lambda x: -len(x[1]))[:20]
    for file, deps_list in top_deps:
        if deps_list:
            lines.append(f"- **{file}**: {', '.join(deps_list[:5])}")
    return "\n".join(lines)


def _format_security_report(issues: list[dict]) -> str:
    lines = [
        "# Security Report",
        f"**Generated:** {datetime.utcnow().isoformat()}",
        f"**Issues found:** {len(issues)}",
        "",
        "## Findings",
        "",
        "| Severity | File | Line | Type | Description |",
        "|----------|------|------|------|-------------|",
    ]
    for issue in sorted(issues, key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.get("severity", "low"), 3)):
        lines.append(f"| {issue.get('severity', 'low').upper()} | {issue.get('file', '')} | {issue.get('line', 0)} | {issue.get('type', '')} | {issue.get('message', '')} |")
    return "\n".join(lines)


def _format_quality_report(quality: dict, smells: list) -> str:
    lines = [
        "# Quality Report",
        f"**Generated:** {datetime.utcnow().isoformat()}",
        "",
        "## Metrics",
        f"- Functions: {quality.get('total_functions', 0)}",
        f"- Classes: {quality.get('total_classes', 0)}",
        f"- Docstring blocks: {quality.get('docstring_blocks', 0)}",
        f"- Documentation ratio: {quality.get('documentation_ratio', 0):.0%}",
        "",
        "## Code Smells",
        "",
        "| Severity | File | Line | Type | Message |",
        "|----------|------|------|------|---------|",
    ]
    for s in sorted(smells, key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.get("severity", "low"), 3)):
        lines.append(f"| {s.get('severity', 'low').upper()} | {s.get('file', '')} | {s.get('line', '')} | {s.get('type', '')} | {s.get('message', '')} |")
    return "\n".join(lines)


def _format_coverage_report(coverage: dict) -> str:
    lines = [
        "# Test Coverage Report",
        f"**Generated:** {datetime.utcnow().isoformat()}",
        "",
        "## Metrics",
        f"- Source files: {coverage.get('source_files', 0)}",
        f"- Test files: {coverage.get('test_files', 0)}",
        f"- Test ratio: {coverage.get('test_ratio', 0):.0%}",
        "",
    ]
    if coverage.get("needs_improvement"):
        lines.append("**Warning:** Test coverage needs improvement.")
    return "\n".join(lines)


def _write_report(path: Path, filename: str, content: str):
    reports_dir = path / "reports"
    reports_dir.mkdir(exist_ok=True)
    (reports_dir / filename).write_text(content, encoding="utf-8")
    logger.info("Report written: %s", reports_dir / filename)


def get_supported_frameworks() -> list[str]:
    return list(_FRAMEWORK_PATTERNS.keys())
