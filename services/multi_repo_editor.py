"""Multi-Repository Editor — coordinated branch/commit/PR management across repositories."""
import logging
import subprocess
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from services.org_graph_service import OrganizationGraph

logger = logging.getLogger(__name__)


class ChangeStatus:
    PENDING = "pending"
    BRANCH_CREATED = "branch_created"
    FILES_MODIFIED = "files_modified"
    COMMITTED = "committed"
    PR_CREATED = "pr_created"
    MERGED = "merged"
    FAILED = "failed"


@dataclass
class RepoChange:
    repo_name: str = ""
    repo_path: str = ""
    branch: str = ""
    files: dict[str, str] = field(default_factory=dict)
    commit_message: str = ""
    status: str = ChangeStatus.PENDING
    pr_url: str = ""
    error: str = ""


@dataclass
class CoordinatedChange:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    org_id: str = ""
    description: str = ""
    branch_name: str = ""
    changes: dict[str, RepoChange] = field(default_factory=dict)
    status: str = ChangeStatus.PENDING
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "org_id": self.org_id,
            "description": self.description,
            "branch_name": self.branch_name,
            "changes": {k: asdict(v) for k, v in self.changes.items()},
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


class MultiRepoEditor:
    def __init__(self, graph: OrganizationGraph):
        self.graph = graph
        self._lock = threading.Lock()
        self._coordinated_changes: dict[str, CoordinatedChange] = {}

    def plan_change(
        self, org_id: str, description: str,
        repos: dict[str, dict[str, str]],
    ) -> CoordinatedChange:
        branch_name = f"auto-change-{uuid.uuid4().hex[:8]}"
        cc = CoordinatedChange(
            org_id=org_id,
            description=description,
            branch_name=branch_name,
        )
        for repo_name, file_changes in repos.items():
            repo_node = None
            for r in self.graph.list_repositories():
                if r.name == repo_name:
                    repo_node = r
                    break
            rc = RepoChange(
                repo_name=repo_name,
                repo_path=repo_node.path if repo_node else "",
                branch=branch_name,
                files=file_changes,
                commit_message=f"[{branch_name}] {description[:80]}",
            )
            cc.changes[repo_name] = rc
        with self._lock:
            self._coordinated_changes[cc.id] = cc
        logger.info("Planned coordinated change: %s (%d repos)", cc.id[:8], len(repos))
        return cc

    def apply_changes(self, change_id: str) -> CoordinatedChange:
        cc = self._get_change(change_id)
        if not cc:
            raise ValueError(f"Coordinated change {change_id} not found")

        for repo_name, rc in cc.changes.items():
            try:
                repo_path = Path(rc.repo_path)
                if not repo_path.exists():
                    rc.status = ChangeStatus.FAILED
                    rc.error = f"Repo path {rc.repo_path} does not exist"
                    continue

                git_dir = repo_path / ".git"
                if not git_dir.exists():
                    rc.status = ChangeStatus.FAILED
                    rc.error = "No .git directory found"
                    continue

                self._git_checkout_branch(repo_path, rc.branch)
                rc.status = ChangeStatus.BRANCH_CREATED

                for file_path, content in rc.files.items():
                    full_path = repo_path / file_path
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_text(content, encoding="utf-8")
                rc.status = ChangeStatus.FILES_MODIFIED

                self._git_commit(repo_path, rc.commit_message, rc.branch)
                rc.status = ChangeStatus.COMMITTED

            except Exception as exc:
                rc.status = ChangeStatus.FAILED
                rc.error = str(exc)
                logger.warning("Failed to apply changes to %s: %s", repo_name, exc)

        all_committed = all(
            rc.status == ChangeStatus.COMMITTED for rc in cc.changes.values()
        )
        cc.status = ChangeStatus.COMMITTED if all_committed else ChangeStatus.FAILED
        cc.completed_at = time.time()
        return cc

    def create_prs(
        self, change_id: str, github_token: str = "",
        repo_full_names: dict[str, str] | None = None,
    ) -> CoordinatedChange:
        cc = self._get_change(change_id)
        if not cc:
            raise ValueError(f"Coordinated change {change_id} not found")

        repo_full_names = repo_full_names or {}

        for repo_name, rc in cc.changes.items():
            if rc.status not in (ChangeStatus.COMMITTED, ChangeStatus.PR_CREATED):
                rc.status = ChangeStatus.FAILED
                rc.error = "Cannot create PR: changes not committed"
                continue

            full_name = repo_full_names.get(repo_name, "")
            if not full_name or not github_token:
                rc.pr_url = f"https://github.com/org/{repo_name}/pull/new/{rc.branch}"
                rc.status = ChangeStatus.PR_CREATED
                continue

            try:
                import requests
                api_url = f"https://api.github.com/repos/{full_name}/pulls"
                resp = requests.post(
                    api_url,
                    headers={
                        "Authorization": f"token {github_token}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                    json={
                        "title": rc.commit_message,
                        "head": rc.branch,
                        "base": "main",
                        "body": cc.description,
                    },
                    timeout=30,
                )
                if resp.ok:
                    pr_data = resp.json()
                    rc.pr_url = pr_data.get("html_url", "")
                    rc.status = ChangeStatus.PR_CREATED
                else:
                    rc.error = f"GitHub API error: {resp.status_code} {resp.text[:200]}"
            except Exception as exc:
                rc.error = str(exc)
                logger.warning("PR creation failed for %s: %s", repo_name, exc)

        has_prs = any(rc.pr_url for rc in cc.changes.values())
        cc.status = ChangeStatus.PR_CREATED if has_prs else cc.status
        return cc

    def get_status(self, change_id: str) -> CoordinatedChange | None:
        return self._get_change(change_id)

    def list_changes(self, org_id: str) -> list[dict]:
        return [
            cc.to_dict() for cc in self._coordinated_changes.values()
            if cc.org_id == org_id
        ]

    def _get_change(self, change_id: str) -> CoordinatedChange | None:
        with self._lock:
            return self._coordinated_changes.get(change_id)

    def _git_checkout_branch(self, repo_path: Path, branch: str) -> None:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=str(repo_path), timeout=30,
        )
        current_branch = result.stdout.strip()
        if current_branch != branch:
            check_result = subprocess.run(
                ["git", "rev-parse", "--verify", branch],
                capture_output=True, text=True, cwd=str(repo_path), timeout=30,
            )
            if check_result.returncode == 0:
                subprocess.run(
                    ["git", "checkout", branch],
                    capture_output=True, cwd=str(repo_path), timeout=30, check=True,
                )
            else:
                subprocess.run(
                    ["git", "checkout", "-b", branch],
                    capture_output=True, cwd=str(repo_path), timeout=30, check=True,
                )

    def _git_commit(self, repo_path: Path, message: str, branch: str) -> None:
        subprocess.run(
            ["git", "add", "-A"],
            capture_output=True, cwd=str(repo_path), timeout=30, check=True,
        )
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            capture_output=True, cwd=str(repo_path), timeout=30,
        )
        if result.returncode != 0:
            subprocess.run(
                ["git", "commit", "-m", message],
                capture_output=True, cwd=str(repo_path), timeout=30, check=True,
            )


_multi_repo_editors: dict[str, MultiRepoEditor] = {}
_editor_lock = threading.Lock()


def get_multi_repo_editor(graph: OrganizationGraph | None = None) -> MultiRepoEditor:
    key = id(graph) if graph else "default"
    with _editor_lock:
        if key not in _multi_repo_editors:
            from services.org_graph_service import get_org_graph_service
            g = graph or get_org_graph_service()
            _multi_repo_editors[key] = MultiRepoEditor(g)
        return _multi_repo_editors[key]
