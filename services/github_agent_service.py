"""GitHub Agent Service — AI-powered repo analysis, PR review, bug fixing, improvements."""
import json
import logging
from typing import Any, Dict, List, Optional

from services.github_service import (
    list_files as gh_list_files,
    get_file_content, list_issues, list_pull_requests,
    get_pr_files, create_issue, add_issue_comment,
    get_repo_info, list_branches, list_commits,
    local_read_file, local_write_file, local_commit_and_push,
    clone_repo, get_local_repo_status,
)
from services.llm_service import call_model, clean_code_response

logger = logging.getLogger(__name__)


def _repo_context(token: str, full_name: str, limit_files: int = 15) -> str:
    info = get_repo_info(token, full_name)
    parts = [f"Repository: {full_name}"]
    if info:
        parts.append(f"Description: {info.get('description', '')}")
        parts.append(f"Language: {info.get('language', '')}")
        parts.append(f"Default Branch: {info.get('default_branch', '')}")
        parts.append(f"Topics: {', '.join(info.get('topics', []))}")
    branches = list_branches(token, full_name)
    parts.append(f"Branches: {', '.join(b['name'] for b in branches[:5])}")
    commits = list_commits(token, full_name)[:3]
    parts.append("Recent commits:")
    for c in commits:
        parts.append(f"  - {c['sha'][:8]}: {c['message'][:80]}")
    files = gh_list_files(token, full_name)[:limit_files]
    parts.append(f"\nTop-level files ({len(files)} shown):")
    for f in files:
        parts.append(f"  {f['type']}: {f['path']}")
    return "\n".join(parts)


def _read_key_files(token: str, full_name: str, max_chars: int = 8000) -> str:
    paths = ["README.md", "package.json", "requirements.txt", "pyproject.toml",
             "setup.py", "Makefile", "Dockerfile", "docker-compose.yml",
             ".env.example", "main.py", "app.py", "index.js", "src/main.py"]
    contents = []
    total = 0
    for p in paths:
        content = get_file_content(token, full_name, p)
        if content and content.get("content"):
            text = content["content"][:2000]
            if total + len(text) > max_chars:
                break
            contents.append(f"### {p}\n{text}")
            total += len(text)
    return "\n\n".join(contents)


def analyze_repository(token: str, full_name: str, model: str = "local") -> Dict[str, Any]:
    try:
        context = _repo_context(token, full_name)
        files_content = _read_key_files(token, full_name)
        prompt = (
            f"Analyze the following GitHub repository and provide a structured report:\n\n"
            f"{context}\n\n"
            f"Key file contents:\n{files_content}\n\n"
            "Provide analysis in JSON format with keys: "
            "overview (2-3 sentence summary), tech_stack (list of technologies), "
            "architecture (description of project structure), "
            "code_quality (suggestions for improvement), "
            "security (potential issues), "
            "documentation (quality assessment), "
            "recommendations (list of 3-5 actionable suggestions)."
        )
        system = "You are a senior software engineer analyzing a GitHub repository. Return ONLY valid JSON."
        result = call_model(prompt, system_prompt=system, model=model,
                            job_id="gh_analyze", agent="GitHubAgent")
        import re
        json_match = re.search(r"\{.*\}", result, re.DOTALL)
        parsed = json.loads(json_match.group(0)) if json_match else json.loads(result)
        return {"status": "ok", "full_name": full_name, "analysis": parsed}
    except Exception as exc:
        logger.error("analyze_repository failed: %s", exc)
        return {"status": "error", "full_name": full_name, "error": str(exc)}


def review_pull_request(token: str, full_name: str, pr_number: int, model: str = "local") -> Dict[str, Any]:
    try:
        prs = list_pull_requests(token, full_name)
        pr = next((p for p in prs if p["number"] == pr_number), None)
        if not pr:
            return {"status": "error", "error": "PR not found"}
        files = get_pr_files(token, full_name, pr_number)
        context = (
            f"Pull Request #{pr_number}: {pr['title']}\n"
            f"Base: {pr['base_branch']} <- Head: {pr['head_branch']}\n"
            f"Description: {pr['body'][:500]}\n"
            f"Changed files ({pr['changed_files']}):\n"
        )
        for f in files[:10]:
            context += f"\n--- {f['filename']} ({f['status']}, +{f['additions']}/-{f['deletions']})\n"
            if f.get("patch"):
                context += f"{f['patch'][:1000]}\n"

        prompt = (
            f"Review this Pull Request:\n\n{context}\n\n"
            "Provide review in JSON: summary, issues (list of {file, line, severity, message}), "
            "approve (bool), suggestions (list of strings)."
        )
        system = "You are a senior code reviewer. Return ONLY valid JSON."
        result = call_model(prompt, system_prompt=system, model=model,
                            job_id=f"gh_pr_{pr_number}", agent="GitHubAgent")
        import re
        json_match = re.search(r"\{.*\}", result, re.DOTALL)
        parsed = json.loads(json_match.group(0)) if json_match else json.loads(result)
        add_issue_comment(token, full_name, pr_number,
                          f"## AI Code Review\n\n{parsed.get('summary', '')}\n\n"
                          f"**Approve:** {'Yes' if parsed.get('approve') else 'No'}\n\n"
                          f"### Suggestions:\n" + "\n".join(f"- {s}" for s in parsed.get("suggestions", [])))
        return {"status": "ok", "pr_number": pr_number, "review": parsed}
    except Exception as exc:
        logger.error("review_pull_request failed: %s", exc)
        return {"status": "error", "error": str(exc)}


def fix_issue(token: str, full_name: str, issue_number: int, model: str = "local") -> Dict[str, Any]:
    try:
        issues = list_issues(token, full_name)
        issue = next((i for i in issues if i["number"] == issue_number), None)
        if not issue:
            return {"status": "error", "error": "Issue not found"}
        context = _repo_context(token, full_name, limit_files=10)
        prompt = (
            f"GitHub Issue #{issue_number}: {issue['title']}\n"
            f"Description: {issue['body'][:1000]}\n\n"
            f"Repository context:\n{context}\n\n"
            "Analyze this issue and provide a fix plan in JSON: "
            "root_cause (string), fix_plan (list of steps with file and description), "
            "effort (low/medium/high), related_files (list of paths)."
        )
        system = "You are a senior developer fixing a GitHub issue. Return ONLY valid JSON."
        result = call_model(prompt, system_prompt=system, model=model,
                            job_id=f"gh_issue_{issue_number}", agent="GitHubAgent")
        import re
        json_match = re.search(r"\{.*\}", result, re.DOTALL)
        parsed = json.loads(json_match.group(0)) if json_match else json.loads(result)
        add_issue_comment(token, full_name, issue_number,
                          f"## AI Analysis\n\n**Root Cause:** {parsed.get('root_cause', '')}\n\n"
                          f"**Effort:** {parsed.get('effort', 'unknown')}\n\n"
                          f"### Fix Plan\n"
                          + "\n".join(f"{i+1}. `{s.get('file', '?')}` — {s.get('description', '')}"
                                      for i, s in enumerate(parsed.get("fix_plan", []))))
        return {"status": "ok", "issue_number": issue_number, "analysis": parsed}
    except Exception as exc:
        logger.error("fix_issue failed: %s", exc)
        return {"status": "error", "error": str(exc)}


def suggest_improvements(token: str, full_name: str, model: str = "local") -> Dict[str, Any]:
    try:
        context = _repo_context(token, full_name)
        files_content = _read_key_files(token, full_name)
        prompt = (
            f"Suggest improvements for this GitHub repository:\n\n{context}\n\n"
            f"Key files:\n{files_content}\n\n"
            "Provide suggestions in JSON: "
            "summary (2-3 sentences), performance (list), security (list), "
            "maintainability (list), testing (list), new_features (list of {title, description})."
        )
        system = "You are a senior software architect. Return ONLY valid JSON."
        result = call_model(prompt, system_prompt=system, model=model,
                            job_id="gh_improve", agent="GitHubAgent")
        import re
        json_match = re.search(r"\{.*\}", result, re.DOTALL)
        parsed = json.loads(json_match.group(0)) if json_match else json.loads(result)
        create_issue(token, full_name,
                     title=f"[AI] Improvement Suggestions for {full_name.split('/')[-1]}",
                     body=json.dumps(parsed, indent=2),
                     labels=["enhancement", "ai-generated"])
        return {"status": "ok", "full_name": full_name, "suggestions": parsed}
    except Exception as exc:
        logger.error("suggest_improvements failed: %s", exc)
        return {"status": "error", "error": str(exc)}
