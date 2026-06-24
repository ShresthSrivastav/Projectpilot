"""Workspace management service with multi-workspace support and RBAC."""

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Optional

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from database.models import User, Workspace, WorkspaceInvite, WorkspaceMember, WorkspaceRole
from services.activity_service import log_activity
from services.jwt_service import create_access_token

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────


def _get_role_rank(role: WorkspaceRole) -> int:
    return {"OWNER": 4, "ADMIN": 3, "MEMBER": 2, "VIEWER": 1}.get(role.value, 0)


def _check_at_least(db: Session, workspace_id: str, user_id: str, min_role: WorkspaceRole) -> WorkspaceMember:
    member = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
        .first()
    )
    if not member:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")
    if _get_role_rank(member.role) < _get_role_rank(min_role):
        raise HTTPException(status_code=403, detail=f"Requires {min_role.value} role or higher")
    return member


def _ws_to_dict(ws: Workspace) -> dict:
    return {
        "id": ws.id,
        "name": ws.name,
        "owner_id": ws.owner_id,
        "created_at": ws.created_at.isoformat() if ws.created_at else "",
        "updated_at": ws.updated_at.isoformat() if ws.updated_at else "",
    }


# ── CRUD ───────────────────────────────────────────────────────────────


def create_workspace(db: Session, name: str, user_id: str) -> Workspace:
    ws = Workspace(name=name, owner_id=user_id)
    db.add(ws)
    db.commit()
    db.refresh(ws)
    member = WorkspaceMember(workspace_id=ws.id, user_id=user_id, role=WorkspaceRole.OWNER)
    db.add(member)
    db.commit()
    log_activity(ws.id, user_id, "workspace.created", f"Workspace '{ws.name}' created")
    logger.info("Created workspace '%s' (owner=%s)", ws.name, user_id)
    return ws


def create_workspace_for_user(db: Session, user: User) -> Workspace:
    return create_workspace(db, f"{user.name} Workspace", user.id)


def get_workspace_by_id(db: Session, workspace_id: str) -> Optional[Workspace]:
    return db.query(Workspace).filter(Workspace.id == workspace_id).first()


def get_user_workspaces(db: Session, user_id: str) -> list[dict]:
    memberships = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.user_id == user_id,
        )
        .all()
    )
    ws_ids = [m.workspace_id for m in memberships]
    workspaces = db.query(Workspace).filter(Workspace.id.in_(ws_ids)).all()
    results = []
    for ws in workspaces:
        d = _ws_to_dict(ws)
        mem = next(m for m in memberships if m.workspace_id == ws.id)
        d["role"] = mem.role.value
        results.append(d)
    return results


def get_workspace_role(db: Session, workspace_id: str, user_id: str) -> Optional[WorkspaceRole]:
    member = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
        .first()
    )
    return member.role if member else None


def get_workspace_members(db: Session, workspace_id: str) -> list[dict]:
    members = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
        )
        .all()
    )
    user_ids = [m.user_id for m in members]
    users = {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()}
    results = []
    for m in members:
        u = users.get(m.user_id)
        results.append(
            {
                "id": m.id,
                "user_id": m.user_id,
                "name": u.name if u else "",
                "email": u.email if u else "",
                "role": m.role.value,
                "joined_at": m.joined_at.isoformat() if m.joined_at else "",
            }
        )
    return results


def remove_member(db: Session, workspace_id: str, member_id: str, requester_id: str) -> None:
    requester_role = get_workspace_role(db, workspace_id, requester_id)
    member = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.id == member_id,
            WorkspaceMember.workspace_id == workspace_id,
        )
        .first()
    )
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    if member.user_id == requester_id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself. Transfer ownership first.")
    target_rank = _get_role_rank(member.role)
    requester_rank = _get_role_rank(requester_role) if requester_role else 0
    if requester_rank <= target_rank:
        raise HTTPException(status_code=403, detail="Cannot remove a member with equal or higher role")
    db.delete(member)
    db.commit()
    log_activity(workspace_id, requester_id, "member.removed", f"Member {member.user_id} removed from workspace")
    logger.info("Removed member %s from workspace %s", member_id, workspace_id)


# ── Invites ────────────────────────────────────────────────────────────


def invite_to_workspace(db: Session, workspace_id: str, email: str, role: WorkspaceRole, invited_by: str) -> dict:
    _check_at_least(db, workspace_id, invited_by, WorkspaceRole.ADMIN)
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        existing_member = (
            db.query(WorkspaceMember)
            .filter(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == existing_user.id,
            )
            .first()
        )
        if existing_member:
            raise HTTPException(status_code=409, detail="User is already a member of this workspace")
    token = secrets.token_urlsafe(48)
    invite = WorkspaceInvite(
        workspace_id=workspace_id,
        email=email,
        role=role,
        token=token,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    log_activity(workspace_id, invited_by, "member.invited", f"Invited {email} as {role.value}")
    logger.info("Invited %s to workspace %s (role=%s, token=%s...)", email, workspace_id, role.value, token[:12])
    return {
        "id": invite.id,
        "email": invite.email,
        "role": invite.role.value,
        "token": token,
        "expires_at": invite.expires_at.isoformat(),
    }


def accept_invite(db: Session, token: str, user_id: str) -> dict:
    invite = (
        db.query(WorkspaceInvite)
        .filter(
            WorkspaceInvite.token == token,
            WorkspaceInvite.accepted == False,
            WorkspaceInvite.expires_at > datetime.now(UTC),
        )
        .first()
    )
    if not invite:
        raise HTTPException(status_code=404, detail="Invalid or expired invite token")
    user = db.query(User).filter(User.id == user_id).first()
    if user.email != invite.email:
        raise HTTPException(status_code=403, detail="This invite was sent to a different email address")
    existing = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == invite.workspace_id,
            WorkspaceMember.user_id == user_id,
        )
        .first()
    )
    if existing:
        invite.accepted = True
        db.commit()
        return {"workspace_id": invite.workspace_id, "message": "Already a member"}
    member = WorkspaceMember(
        workspace_id=invite.workspace_id,
        user_id=user_id,
        role=invite.role,
    )
    db.add(member)
    invite.accepted = True
    db.commit()
    ws = db.query(Workspace).filter(Workspace.id == invite.workspace_id).first()
    log_activity(invite.workspace_id, user_id, "member.joined", f"User {user.email} joined workspace")
    logger.info("User %s accepted invite to workspace %s", user_id, invite.workspace_id)
    return {"workspace_id": invite.workspace_id, "name": ws.name if ws else "", "role": invite.role.value}


def get_pending_invites(db: Session, workspace_id: str, requester_id: str) -> list[dict]:
    _check_at_least(db, workspace_id, requester_id, WorkspaceRole.ADMIN)
    invites = (
        db.query(WorkspaceInvite)
        .filter(
            WorkspaceInvite.workspace_id == workspace_id,
            WorkspaceInvite.accepted == False,
        )
        .all()
    )
    return [
        {
            "id": i.id,
            "email": i.email,
            "role": i.role.value,
            "created_at": i.created_at.isoformat() if i.created_at else "",
        }
        for i in invites
    ]


# ── Workspace switching support ────────────────────────────────────────


def switch_workspace(db: Session, workspace_id: str, user_id: str) -> dict:
    member = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
        .first()
    )
    if not member:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    new_token = create_access_token(user_id, workspace_id)
    return {"access_token": new_token, "workspace": _ws_to_dict(ws)}


# ── Legacy helpers (backward compat, now use member list) ─────────────


def get_current_workspace(db: Session, user_id: str) -> Workspace:
    workspaces = get_user_workspaces(db, user_id)
    if not workspaces:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            ws = create_workspace_for_user(db, user)
            return ws
        raise HTTPException(status_code=404, detail="User not found")
    ws = db.query(Workspace).filter(Workspace.id == workspaces[0]["id"]).first()
    return ws


def get_workspace_by_owner(db: Session, user_id: str) -> Optional[Workspace]:
    return db.query(Workspace).filter(Workspace.owner_id == user_id).first()


def get_current_workspace_id(request: Request) -> str:
    """Enforce workspace isolation — always derive from JWT via request.state."""
    ws_id = getattr(request.state, "workspace_id", None)
    if not ws_id:
        raise HTTPException(status_code=403, detail="Workspace context required")
    return ws_id
