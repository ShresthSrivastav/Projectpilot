"""GitHub integration routes — extracted from main.py."""

import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request, Response
from pydantic import BaseModel

from database.memory_store import (
    save_github_repo,
    save_repository_relationship,
)
from services.github_service import (
    add_issue_comment,
    clone_repo,
    connect_github,
    create_branch,
    create_file,
    create_issue,
    create_pull_request,
    create_webhook,
    delete_branch,
    delete_file,
    delete_webhook,
    disconnect_github,
    get_commit_diff,
    get_connection,
    get_file_content,
    get_local_repo_status,
    get_pr_files,
    get_repo_info,
    list_branches,
    list_commits,
    list_connections,
    list_issue_comments,
    list_issues,
    list_pull_requests,
    list_repos,
    list_webhooks,
    local_commit_and_push,
    local_file_list,
    local_read_file,
    local_write_file,
    merge_pull_request,
    pull_repo,
    search_repos,
    update_file,
    update_issue,
)
from services.github_service import list_files as _gh_list_files

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/github", tags=["GitHub"])


# ── Models ────────────────────────────────────────────────────────────────


class GithubConnectRequest(BaseModel):
    token: str
    username: str = ""


class DisconnectRequest(BaseModel):
    username: str


class BranchRequest(BaseModel):
    username: str
    branch: str
    source_branch: str = ""


class FileWriteRequest(BaseModel):
    username: str
    path: str
    content: str
    message: str
    branch: str = ""
    sha: str = ""


class PRCreateRequest(BaseModel):
    username: str
    title: str
    head: str
    base: str
    body: str = ""
    draft: bool = False


class PRMergeRequest(BaseModel):
    username: str
    commit_message: str = ""
    merge_method: str = "merge"


class IssueCreateRequest(BaseModel):
    username: str
    title: str
    body: str = ""
    labels: list[str] = []
    assignees: list[str] = []


class IssueUpdateRequest(BaseModel):
    username: str
    title: str = ""
    body: str = ""
    state: str = ""


class IssueCommentRequest(BaseModel):
    username: str
    body: str


class WebhookCreateRequest(BaseModel):
    username: str
    url: str
    events: list[str] = []


# ── Connection ───────────────────────────────────────────────────────────


@router.post("/connect")
async def github_connect(req: GithubConnectRequest):
    try:
        data = connect_github(req.token, req.username)
        return {"status": "connected", "data": data}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/disconnect")
async def github_disconnect(req: DisconnectRequest):
    disconnect_github(req.username)
    return {"status": "disconnected"}


@router.get("/connections")
async def github_list_connections():
    return {"connections": list_connections()}


# ── Repos ────────────────────────────────────────────────────────────────


@router.get("/{username}/repos")
async def github_list_repos(username: str):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    repos = list_repos(conn["token"], conn["username"])
    for r in repos:
        save_github_repo(username, r["full_name"], r)
    return {"repos": repos}


@router.get("/repo/{full_name:path}")
async def github_repo_info(full_name: str, username: str = ""):
    if not username:
        raise HTTPException(status_code=400, detail="username required")
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    info = get_repo_info(conn["token"], full_name)
    if not info:
        raise HTTPException(status_code=404, detail="Repo not found")
    return info


@router.get("/search")
async def github_search(q: str, username: str = ""):
    if not username:
        raise HTTPException(status_code=400, detail="username required")
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return {"results": search_repos(conn["token"], q)}


# ── Branches ─────────────────────────────────────────────────────────────


@router.get("/{full_name:path}/branches")
async def github_list_branches(full_name: str, username: str = ""):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return {"branches": list_branches(conn["token"], full_name)}


@router.post("/{full_name:path}/branches")
async def github_create_branch(full_name: str, req: BranchRequest):
    conn = get_connection(req.username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return create_branch(conn["token"], full_name, req.branch, req.source_branch)


@router.delete("/{full_name:path}/branches/{branch}")
async def github_delete_branch(full_name: str, branch: str, username: str = ""):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return delete_branch(conn["token"], full_name, branch)


# ── Files ────────────────────────────────────────────────────────────────


@router.get("/{full_name:path}/files")
async def github_list_files(full_name: str, path: str = "", ref: str = "", username: str = ""):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return {"files": _gh_list_files(conn["token"], full_name, path, ref)}


@router.get("/{full_name:path}/file")
async def github_get_file(full_name: str, path: str, ref: str = "", username: str = ""):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    content = get_file_content(conn["token"], full_name, path, ref)
    if not content:
        raise HTTPException(status_code=404, detail="File not found")
    return content


@router.post("/{full_name:path}/file")
async def github_create_or_update_file(full_name: str, req: FileWriteRequest):
    conn = get_connection(req.username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    if req.sha:
        return update_file(conn["token"], full_name, req.path, req.content, req.message, req.sha, req.branch)
    return create_file(conn["token"], full_name, req.path, req.content, req.message, req.branch)


@router.delete("/{full_name:path}/file")
async def github_delete_file_ep(full_name: str, path: str, message: str, sha: str, username: str = ""):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return delete_file(conn["token"], full_name, path, message, sha)


# ── Commits ──────────────────────────────────────────────────────────────


@router.get("/{full_name:path}/commits")
async def github_list_commits(full_name: str, branch: str = "", since: str = "", until: str = "", username: str = ""):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return {"commits": list_commits(conn["token"], full_name, branch, since, until)}


@router.get("/{full_name:path}/commits/{sha}")
async def github_commit_detail(full_name: str, sha: str, username: str = ""):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return {"diff": get_commit_diff(conn["token"], full_name, sha)}


# ── Pull Requests ────────────────────────────────────────────────────────


@router.get("/{full_name:path}/pulls")
async def github_list_pulls(full_name: str, state: str = "open", username: str = ""):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return {"pull_requests": list_pull_requests(conn["token"], full_name, state)}


@router.post("/{full_name:path}/pulls")
async def github_create_pr(full_name: str, req: PRCreateRequest):
    conn = get_connection(req.username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return create_pull_request(conn["token"], full_name, req.title, req.head, req.base, req.body, req.draft)


@router.post("/{full_name:path}/pulls/{pr_number}/merge")
async def github_merge_pr(full_name: str, pr_number: int, req: PRMergeRequest):
    conn = get_connection(req.username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return merge_pull_request(conn["token"], full_name, pr_number, req.commit_message, req.merge_method)


@router.get("/{full_name:path}/pulls/{pr_number}/files")
async def github_pr_files(full_name: str, pr_number: int, username: str = ""):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return {"files": get_pr_files(conn["token"], full_name, pr_number)}


# ── Issues ───────────────────────────────────────────────────────────────


@router.get("/{full_name:path}/issues")
async def github_list_issues(full_name: str, state: str = "open", labels: str = "", username: str = ""):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return {"issues": list_issues(conn["token"], full_name, state, labels)}


@router.post("/{full_name:path}/issues")
async def github_create_issue(full_name: str, req: IssueCreateRequest):
    conn = get_connection(req.username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return create_issue(conn["token"], full_name, req.title, req.body, req.labels, req.assignees)


@router.patch("/{full_name:path}/issues/{issue_number}")
async def github_update_issue(full_name: str, issue_number: int, req: IssueUpdateRequest):
    conn = get_connection(req.username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return update_issue(conn["token"], full_name, issue_number, req.title, req.body, req.state)


@router.post("/{full_name:path}/issues/{issue_number}/comments")
async def github_add_comment(full_name: str, issue_number: int, req: IssueCommentRequest):
    conn = get_connection(req.username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return add_issue_comment(conn["token"], full_name, issue_number, req.body)


@router.get("/{full_name:path}/issues/{issue_number}/comments")
async def github_list_comments(full_name: str, issue_number: int, username: str = ""):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return {"comments": list_issue_comments(conn["token"], full_name, issue_number)}


# ── Local Clone / Sync ───────────────────────────────────────────────────


@router.post("/{full_name:path}/clone")
async def github_clone(full_name: str, username: str = "", branch: str = ""):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return clone_repo(conn["token"], full_name, branch)


@router.post("/{full_name:path}/pull")
async def github_pull(full_name: str, username: str = "", branch: str = ""):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return pull_repo(conn["token"], full_name, branch)


@router.get("/{full_name:path}/local-status")
async def github_local_status(full_name: str):
    status = get_local_repo_status(full_name)
    if not status:
        raise HTTPException(status_code=404, detail="Not cloned locally")
    return status


@router.get("/{full_name:path}/local-files")
async def github_local_files(full_name: str, path: str = ""):
    return {"files": local_file_list(full_name, path)}


@router.get("/{full_name:path}/local-file")
async def github_local_read(full_name: str, path: str):
    content = local_read_file(full_name, path)
    if content is None:
        raise HTTPException(status_code=404, detail="File not found")
    return Response(content, media_type="text/plain")


@router.post("/{full_name:path}/local-file")
async def github_local_write(
    full_name: str, path: str, content: str = Body(..., embed=True), message: str = "", username: str = ""
):
    return local_write_file(full_name, path, content, message)


@router.post("/{full_name:path}/commit-push")
async def github_commit_push(
    full_name: str, message: str = Body(..., embed=True), branch: str = "", username: str = ""
):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return local_commit_and_push(full_name, message, branch)


# ── Webhooks ─────────────────────────────────────────────────────────────


@router.get("/{full_name:path}/webhooks")
async def github_list_webhooks(full_name: str, username: str = ""):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return {"webhooks": list_webhooks(conn["token"], full_name)}


@router.post("/{full_name:path}/webhooks")
async def github_create_webhook(full_name: str, req: WebhookCreateRequest):
    conn = get_connection(req.username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return create_webhook(conn["token"], full_name, req.url, req.events or None)


@router.delete("/{full_name:path}/webhooks/{hook_id}")
async def github_delete_webhook(full_name: str, hook_id: int, username: str = ""):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    return delete_webhook(conn["token"], full_name, hook_id)


# ── AI Agent: GitHub Analysis ────────────────────────────────────────────


@router.post("/agent/analyze-repo")
async def github_agent_analyze(full_name: str = Body(...), username: str = Body(...), model: str = "local"):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    from services.github_agent_service import analyze_repository

    return analyze_repository(conn["token"], full_name, model=model)


@router.post("/agent/review-pr")
async def github_agent_review_pr(
    full_name: str = Body(...), pr_number: int = Body(...), username: str = Body(...), model: str = "local"
):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    from services.github_agent_service import review_pull_request

    return review_pull_request(conn["token"], full_name, pr_number, model=model)


@router.post("/agent/fix-issue")
async def github_agent_fix_issue(
    full_name: str = Body(...), issue_number: int = Body(...), username: str = Body(...), model: str = "local"
):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    from services.github_agent_service import fix_issue

    return fix_issue(conn["token"], full_name, issue_number, model=model)


@router.post("/agent/suggest-improvements")
async def github_agent_suggest(full_name: str = Body(...), username: str = Body(...), model: str = "local"):
    conn = get_connection(username)
    if not conn:
        raise HTTPException(status_code=404, detail="No connection found")
    from services.github_agent_service import suggest_improvements

    return suggest_improvements(conn["token"], full_name, model=model)


# ── Webhook Receiver ─────────────────────────────────────────────────────


@router.post("/webhook-receiver/{full_name:path}")
async def github_webhook_receiver(full_name: str, request: Request):
    """
    Receiver endpoint for GitHub webhooks.
    - Push events → auto-pull local clone
    - pull_request events → auto-AI-review
    """
    event = request.headers.get("X-GitHub-Event", "push")
    payload = await request.json()
    if event == "push":
        ref = payload.get("ref", "")
        branch = ref.replace("refs/heads/", "") if ref else ""
        try:
            from services.github_service import pull_repo

            result = pull_repo("", full_name, branch=branch)
            return {"event": event, "branch": branch, "result": result}
        except Exception as exc:
            return {"event": event, "error": str(exc)}
    if event == "pull_request" and payload.get("action") in ("opened", "synchronize"):
        pr_number = payload.get("number", 0)
        try:
            from services.github_agent_service import review_pull_request

            result = review_pull_request("", full_name, pr_number, model="local")
            return {"event": event, "pr": pr_number, "result": result}
        except Exception as exc:
            return {"event": event, "error": str(exc)}
    return {"event": event, "action": payload.get("action", "unknown"), "handled": False}