"""GitHub Service — OAuth, repo management, branches, commits, PRs, issues, sync."""
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from git import GitCommandError, Repo
from github import Github
from github.Auth import Token as GhToken

from database.memory_store import (
    delete_github_connection,
    get_github_connection,
    save_github_connection,
)
from services.token_crypto import decrypt_token, encrypt_token, mask_token

logger = logging.getLogger(__name__)

CLONE_BASE = os.getenv("GITHUB_CLONE_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "github_repos"))


def _get_client(token: str) -> Github:
    return Github(auth=GhToken(token))


# ── Connection Management ────────────────────────────────────────────────

def connect_github(token: str, username: str = "") -> dict[str, Any]:
    g = _get_client(token)
    user = g.get_user()
    login = username or user.login
    encrypted = encrypt_token(token)
    data = {
        "username": login,
        "token": encrypted,
        "avatar_url": user.avatar_url,
        "name": user.name or login,
        "email": user.email or "",
        "public_repos": user.public_repos,
        "connected_at": datetime.now(UTC).isoformat(),
    }
    save_github_connection(login, data)
    # Return masked token in response, never plaintext
    display = data.copy()
    display["token"] = mask_token(token)
    logger.info("GitHub connected: %s (token: %s)", login, mask_token(token))
    return display


def disconnect_github(username: str) -> None:
    delete_github_connection(username)


def get_connection(username: str) -> dict | None:
    raw = get_github_connection(username)
    if raw:
        raw["token"] = decrypt_token(raw.get("token", ""))
    return raw


def list_connections() -> list[dict]:
    raw_list = get_github_connection() or []
    for conn in raw_list:
        conn["token"] = decrypt_token(conn.get("token", ""))
    return raw_list


def _mask_gh_token_in_args(func_name: str, args: tuple, kwargs: dict) -> tuple:
    masked_args = []
    for arg in args:
        if isinstance(arg, str) and len(arg) > 20 and any(c in arg for c in ("ghp_", "gho_", "ghu_", "ghs_", "ghr_")):
            masked_args.append(mask_token(arg))
        else:
            masked_args.append(arg)
    masked_kwargs = {}
    for k, v in kwargs.items():
        if k == "token" and isinstance(v, str):
            masked_kwargs[k] = mask_token(v)
        else:
            masked_kwargs[k] = v
    return func_name, tuple(masked_args), masked_kwargs


# ── Repository Operations ────────────────────────────────────────────────

def list_repos(token: str, username: str = "") -> list[dict]:
    g = _get_client(token)
    user = g.get_user(username) if username else g.get_user()
    repos = []
    for r in user.get_repos(type="all", sort="updated", direction="desc"):
        repos.append({
            "id": r.id,
            "name": r.name,
            "full_name": r.full_name,
            "description": r.description or "",
            "url": r.html_url,
            "clone_url": r.clone_url,
            "ssh_url": r.ssh_url,
            "language": r.language or "",
            "default_branch": r.default_branch,
            "stars": r.stargazers_count,
            "forks": r.forks_count,
            "open_issues": r.open_issues_count,
            "private": r.private,
            "updated_at": r.updated_at.isoformat() if r.updated_at else "",
        })
    return repos


def get_repo_info(token: str, full_name: str) -> dict | None:
    try:
        g = _get_client(token)
        r = g.get_repo(full_name)
        return {
            "id": r.id,
            "name": r.name,
            "full_name": r.full_name,
            "description": r.description or "",
            "url": r.html_url,
            "clone_url": r.clone_url,
            "ssh_url": r.ssh_url,
            "language": r.language or "",
            "default_branch": r.default_branch,
            "stars": r.stargazers_count,
            "forks": r.forks_count,
            "open_issues": r.open_issues_count,
            "private": r.private,
            "topics": r.get_topics(),
            "license": r.license.spdx_id if r.license else "",
            "size_kb": r.size,
            "created_at": r.created_at.isoformat() if r.created_at else "",
            "updated_at": r.updated_at.isoformat() if r.updated_at else "",
        }
    except Exception as exc:
        logger.warning("get_repo_info(%s) failed: %s", full_name, exc)
        return None


def search_repos(token: str, query: str) -> list[dict]:
    g = _get_client(token)
    results = []
    for r in g.search_repositories(query, sort="updated", order="desc")[:20]:
        results.append({
            "id": r.id,
            "full_name": r.full_name,
            "description": r.description or "",
            "url": r.html_url,
            "language": r.language or "",
            "stars": r.stargazers_count,
        })
    return results


# ── Branch Operations ────────────────────────────────────────────────────

def list_branches(token: str, full_name: str) -> list[dict]:
    g = _get_client(token)
    r = g.get_repo(full_name)
    branches = []
    for b in r.get_branches():
        branches.append({
            "name": b.name,
            "sha": b.commit.sha,
            "protected": b.protected,
        })
    return branches


def create_branch(token: str, full_name: str, branch: str, source_branch: str = "") -> dict:
    g = _get_client(token)
    r = g.get_repo(full_name)
    source = source_branch or r.default_branch
    src_sha = r.get_branch(source).commit.sha
    r.create_git_ref(f"refs/heads/{branch}", src_sha)
    return {"name": branch, "source": source, "sha": src_sha}


def delete_branch(token: str, full_name: str, branch: str) -> dict:
    g = _get_client(token)
    r = g.get_repo(full_name)
    ref = r.get_git_ref(f"heads/{branch}")
    ref.delete()
    return {"deleted": branch}


# ── File Operations ──────────────────────────────────────────────────────

def get_file_content(token: str, full_name: str, path: str, ref: str = "") -> dict | None:
    try:
        g = _get_client(token)
        r = g.get_repo(full_name)
        kwargs = {"ref": ref} if ref else {}
        content = r.get_contents(path, **kwargs)
        return {
            "path": content.path,
            "name": content.name,
            "sha": content.sha,
            "size": content.size,
            "encoding": content.encoding,
            "content": content.decoded_content.decode("utf-8") if content.encoding == "base64" else content.decoded_content,
            "type": content.type,
            "html_url": content.html_url,
            "download_url": content.download_url,
        }
    except Exception as exc:
        logger.warning("get_file(%s) failed: %s", path, exc)
        return None


def create_file(token: str, full_name: str, path: str, content: str, message: str, branch: str = "") -> dict:
    g = _get_client(token)
    r = g.get_repo(full_name)
    branch = branch or r.default_branch
    result = r.create_file(path, message, content, branch=branch)
    return {
        "path": path,
        "sha": result["content"].sha,
        "commit": result["commit"].sha,
        "url": result["commit"].html_url,
    }


def update_file(token: str, full_name: str, path: str, content: str, message: str, sha: str, branch: str = "") -> dict:
    g = _get_client(token)
    r = g.get_repo(full_name)
    branch = branch or r.default_branch
    result = r.update_file(path, message, content, sha, branch=branch)
    return {
        "path": path,
        "sha": result["content"].sha,
        "commit": result["commit"].sha,
        "url": result["commit"].html_url,
    }


def delete_file(token: str, full_name: str, path: str, message: str, sha: str, branch: str = "") -> dict:
    g = _get_client(token)
    r = g.get_repo(full_name)
    branch = branch or r.default_branch
    result = r.delete_file(path, message, sha, branch=branch)
    return {"commit": result["commit"].sha}


def list_files(token: str, full_name: str, path: str = "", ref: str = "") -> list[dict]:
    try:
        g = _get_client(token)
        r = g.get_repo(full_name)
        kwargs = {"ref": ref} if ref else {}
        contents = r.get_contents(path or "", **kwargs)
        if not isinstance(contents, list):
            contents = [contents]
        files = []
        for c in contents:
            files.append({
                "path": c.path,
                "name": c.name,
                "type": c.type,
                "size": c.size,
                "sha": c.sha,
                "download_url": c.download_url,
            })
        return files
    except Exception as exc:
        logger.warning("list_files(%s) failed: %s", path, exc)
        return []


# ── Commit Operations ────────────────────────────────────────────────────

def list_commits(token: str, full_name: str, branch: str = "", since: str = "", until: str = "") -> list[dict]:
    g = _get_client(token)
    r = g.get_repo(full_name)
    kwargs: dict = {}
    if branch:
        kwargs["sha"] = branch
    if since:
        kwargs["since"] = datetime.fromisoformat(since)
    if until:
        kwargs["until"] = datetime.fromisoformat(until)
    commits = []
    for c in r.get_commits(**kwargs)[:30]:
        commits.append({
            "sha": c.sha,
            "message": c.commit.message,
            "author": c.commit.author.name,
            "author_email": c.commit.author.email,
            "date": c.commit.author.date.isoformat() if c.commit.author.date else "",
            "url": c.html_url,
            "files_changed": len(c.files) if c.files else 0,
            "additions": c.stats.additions if c.stats else 0,
            "deletions": c.stats.deletions if c.stats else 0,
        })
    return commits


def get_commit_diff(token: str, full_name: str, sha: str) -> str:
    g = _get_client(token)
    r = g.get_repo(full_name)
    commit = r.get_commit(sha)
    diff_parts = []
    for f in commit.files or []:
        diff_parts.append(f"--- a/{f.filename}\n+++ b/{f.filename}\n{f.patch or ''}")
    return "\n".join(diff_parts)


# ── Pull Request Operations ──────────────────────────────────────────────

def list_pull_requests(token: str, full_name: str, state: str = "open") -> list[dict]:
    g = _get_client(token)
    r = g.get_repo(full_name)
    prs = []
    for pr in r.get_pulls(state=state, sort="updated", direction="desc"):
        prs.append({
            "number": pr.number,
            "title": pr.title,
            "body": pr.body or "",
            "state": pr.state,
            "author": pr.user.login if pr.user else "",
            "head_branch": pr.head.ref,
            "base_branch": pr.base.ref,
            "created_at": pr.created_at.isoformat() if pr.created_at else "",
            "updated_at": pr.updated_at.isoformat() if pr.updated_at else "",
            "url": pr.html_url,
            "draft": pr.draft if hasattr(pr, "draft") else False,
            "mergeable": pr.mergeable,
            "merged": pr.merged,
            "additions": pr.additions or 0,
            "deletions": pr.deletions or 0,
            "changed_files": pr.changed_files or 0,
        })
    return prs


def create_pull_request(token: str, full_name: str, title: str, head: str, base: str, body: str = "", draft: bool = False) -> dict:
    g = _get_client(token)
    r = g.get_repo(full_name)
    pr = r.create_pull(title=title, body=body, head=head, base=base, draft=draft)
    return {
        "number": pr.number,
        "title": pr.title,
        "url": pr.html_url,
        "state": pr.state,
        "created_at": pr.created_at.isoformat() if pr.created_at else "",
    }


def merge_pull_request(token: str, full_name: str, pr_number: int, commit_message: str = "", merge_method: str = "merge") -> dict:
    g = _get_client(token)
    r = g.get_repo(full_name)
    pr = r.get_pull(pr_number)
    result = pr.merge(commit_message=commit_message or pr.title, merge_method=merge_method)
    return {"merged": result.merged, "message": result.message, "sha": result.sha}


def get_pr_diff(token: str, full_name: str, pr_number: int) -> str:
    g = _get_client(token)
    r = g.get_repo(full_name)
    pr = r.get_pull(pr_number)
    return pr.get_files()


def get_pr_files(token: str, full_name: str, pr_number: int) -> list[dict]:
    g = _get_client(token)
    r = g.get_repo(full_name)
    pr = r.get_pull(pr_number)
    files = []
    for f in pr.get_files():
        files.append({
            "filename": f.filename,
            "status": f.status,
            "additions": f.additions,
            "deletions": f.deletions,
            "changes": f.changes,
            "patch": f.patch or "",
            "contents_url": f.contents_url,
        })
    return files


# ── Issue Operations ─────────────────────────────────────────────────────

def list_issues(token: str, full_name: str, state: str = "open", labels: str = "") -> list[dict]:
    g = _get_client(token)
    r = g.get_repo(full_name)
    kwargs: dict = {"state": state, "sort": "updated", "direction": "desc"}
    if labels:
        kwargs["labels"] = labels.split(",")
    issues = []
    for i in r.get_issues(**kwargs)[:30]:
        issues.append({
            "number": i.number,
            "title": i.title,
            "body": i.body or "",
            "state": i.state,
            "author": i.user.login if i.user else "",
            "labels": [l.name for l in i.labels],
            "assignees": [a.login for a in i.assignees],
            "comments_count": i.comments,
            "created_at": i.created_at.isoformat() if i.created_at else "",
            "updated_at": i.updated_at.isoformat() if i.updated_at else "",
            "url": i.html_url,
        })
    return issues


def create_issue(token: str, full_name: str, title: str, body: str = "", labels: list[str] = None, assignees: list[str] = None) -> dict:
    g = _get_client(token)
    r = g.get_repo(full_name)
    issue = r.create_issue(title=title, body=body, labels=labels or [], assignees=assignees or [])
    return {
        "number": issue.number,
        "title": issue.title,
        "url": issue.html_url,
        "state": issue.state,
        "created_at": issue.created_at.isoformat() if issue.created_at else "",
    }


def update_issue(token: str, full_name: str, issue_number: int, title: str = "", body: str = "", state: str = "") -> dict:
    g = _get_client(token)
    r = g.get_repo(full_name)
    issue = r.get_issue(issue_number)
    kwargs: dict = {}
    if title:
        kwargs["title"] = title
    if body:
        kwargs["body"] = body
    if state:
        kwargs["state"] = state
    issue.edit(**kwargs)
    return {
        "number": issue.number,
        "title": issue.title,
        "state": issue.state,
        "updated_at": issue.updated_at.isoformat() if issue.updated_at else "",
    }


def add_issue_comment(token: str, full_name: str, issue_number: int, body: str) -> dict:
    g = _get_client(token)
    r = g.get_repo(full_name)
    comment = r.get_issue(issue_number).create_comment(body)
    return {"id": comment.id, "body": body, "created_at": comment.created_at.isoformat() if comment.created_at else ""}


def list_issue_comments(token: str, full_name: str, issue_number: int) -> list[dict]:
    g = _get_client(token)
    r = g.get_repo(full_name)
    comments = []
    for c in r.get_issue(issue_number).get_comments():
        comments.append({
            "id": c.id,
            "body": c.body,
            "author": c.user.login if c.user else "",
            "created_at": c.created_at.isoformat() if c.created_at else "",
        })
    return comments


# ── Local Clone / Sync Operations ────────────────────────────────────────

def _clone_dir(full_name: str) -> Path:
    return Path(CLONE_BASE) / full_name.replace("/", "_")


def clone_repo(token: str, full_name: str, branch: str = "") -> dict:
    dest = _clone_dir(full_name)
    if dest.exists():
        return {"status": "already_cloned", "path": str(dest)}
    dest.parent.mkdir(parents=True, exist_ok=True)
    g = _get_client(token)
    r = g.get_repo(full_name)
    auth_url = r.clone_url.replace("https://", f"https://oauth2:{token}@")
    try:
        repo = Repo.clone_from(auth_url, str(dest), branch=branch or r.default_branch)
        # Remove token from remote URL after clone
        with repo.config_writer() as cw:
            cw.set_value("remote.origin", "url", r.clone_url)
        logger.info("Cloned %s (branch: %s, token: %s)", full_name, repo.active_branch.name, mask_token(token))
        return {"status": "cloned", "path": str(dest), "branch": repo.active_branch.name}
    except GitCommandError as exc:
        logger.error("Clone failed for %s (token: %s): %s", full_name, mask_token(token), str(exc))
        return {"status": "error", "error": "Clone failed. Check token permissions."}


def pull_repo(token: str, full_name: str, branch: str = "") -> dict:
    dest = _clone_dir(full_name)
    if not dest.exists():
        return clone_repo(token, full_name, branch)
    try:
        repo = Repo(str(dest))
        origin = repo.remotes.origin
        pull_branch = branch or repo.active_branch.name
        info = origin.pull(pull_branch)
        return {"status": "pulled", "branch": pull_branch, "commits": len(info)}
    except GitCommandError as exc:
        logger.error("Pull failed: %s", exc)
        return {"status": "error", "error": str(exc)}


def get_local_repo_status(full_name: str) -> dict | None:
    dest = _clone_dir(full_name)
    if not dest.exists():
        return None
    try:
        repo = Repo(str(dest))
        return {
            "path": str(dest),
            "branch": repo.active_branch.name,
            "dirty": repo.is_dirty(),
            "untracked": len(repo.untracked_files),
            "ahead": sum(1 for _ in repo.iter_commits(f"origin/{repo.active_branch.name}..{repo.active_branch.name}")),
            "behind": sum(1 for _ in repo.iter_commits(f"{repo.active_branch.name}..origin/{repo.active_branch.name}")),
            "last_commit": repo.head.commit.message if repo.head else "",
            "last_commit_date": str(repo.head.commit.committed_datetime) if repo.head else "",
        }
    except Exception as exc:
        return {"error": str(exc)}


def local_file_list(full_name: str, path: str = "") -> list[dict]:
    dest = _clone_dir(full_name)
    base = dest / path if path else dest
    if not base.exists():
        return []
    files = []
    for item in sorted(base.iterdir()):
        files.append({
            "name": item.name,
            "type": "dir" if item.is_dir() else "file",
            "path": str(item.relative_to(dest)),
            "size": item.stat().st_size if item.is_file() else 0,
        })
    return files


def local_read_file(full_name: str, path: str) -> str | None:
    dest = _clone_dir(full_name) / path
    if not dest.exists() or not dest.is_file():
        return None
    try:
        return dest.read_text(encoding="utf-8")
    except Exception:
        return None


def local_write_file(full_name: str, path: str, content: str, message: str = "") -> dict:
    dest = _clone_dir(full_name) / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    if message:
        repo = Repo(str(_clone_dir(full_name)))
        repo.index.add([str(dest)])
        repo.index.commit(message)
    return {"path": path, "size": len(content), "committed": bool(message)}


def local_commit_and_push(full_name: str, message: str, branch: str = "") -> dict:
    dest = _clone_dir(full_name)
    if not dest.exists():
        return {"status": "error", "error": "Repo not cloned locally"}
    try:
        repo = Repo(str(dest))
        if repo.is_dirty() or repo.untracked_files:
            repo.index.add("*")
        repo.index.commit(message)
        branch = branch or repo.active_branch.name
        origin = repo.remotes.origin
        origin.push(branch)
        return {"status": "pushed", "branch": branch, "commit": repo.head.commit.hexsha}
    except GitCommandError as exc:
        logger.error("Push failed: %s", exc)
        return {"status": "error", "error": str(exc)}


# ── Webhook Management ───────────────────────────────────────────────────

def list_webhooks(token: str, full_name: str) -> list[dict]:
    g = _get_client(token)
    r = g.get_repo(full_name)
    hooks = []
    for h in r.get_hooks():
        hooks.append({
            "id": h.id,
            "name": h.name,
            "url": h.config.get("url", ""),
            "events": h.events,
            "active": h.active,
            "created_at": h.created_at.isoformat() if h.created_at else "",
        })
    return hooks


def create_webhook(token: str, full_name: str, webhook_url: str, events: list[str] = None) -> dict:
    g = _get_client(token)
    r = g.get_repo(full_name)
    hook = r.create_hook(
        name="web",
        config={"url": webhook_url, "content_type": "json"},
        events=events or ["push", "pull_request", "issues"],
        active=True,
    )
    return {"id": hook.id, "url": webhook_url, "events": hook.events}


def delete_webhook(token: str, full_name: str, hook_id: int) -> dict:
    g = _get_client(token)
    r = g.get_repo(full_name)
    hook = r.get_hook(hook_id)
    hook.delete()
    return {"deleted": hook_id}
