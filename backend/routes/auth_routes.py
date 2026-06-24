from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import User, WorkspaceRole
from services.auth_service import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    SwitchWorkspaceResponse,
    UserResponse,
    WorkspaceResponse,
    get_current_user,
    get_me,
    login_user,
    logout_user,
    refresh_access_token,
    register_user,
    require_auth,
)
from services.workspace_service import (
    accept_invite,
    create_workspace,
    get_current_workspace,
    get_current_workspace_id,
    get_pending_invites,
    get_user_workspaces,
    get_workspace_by_id,
    get_workspace_members,
    get_workspace_role,
    invite_to_workspace,
    remove_member,
    switch_workspace,
)
from services.activity_service import get_activities
from services.notification_service import (
    get_notifications,
    mark_all_notifications_read,
    mark_notification_read,
)

router = APIRouter(prefix="/api/auth", tags=["Auth"])


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


@router.post("/register", response_model=AuthResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    return register_user(db, req)


@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    return login_user(db, req)


@router.post("/logout")
def logout(req: LogoutRequest, db: Session = Depends(get_db)):
    logout_user(db, req.refresh_token)
    return {"message": "Logged out successfully"}


@router.post("/refresh", response_model=AuthResponse)
def refresh(req: RefreshRequest, db: Session = Depends(get_db)):
    return refresh_access_token(db, req.refresh_token)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(require_auth), db: Session = Depends(get_db)):
    return get_me(db, current_user.id)


# ── Workspace management ──────────────────────────────────────────────

router_workspace = APIRouter(prefix="/api/workspace", tags=["Workspace"])


class CreateWorkspaceRequest(BaseModel):
    name: str


class SwitchWorkspaceRequest(BaseModel):
    workspace_id: str


class InviteRequest(BaseModel):
    email: str
    role: WorkspaceRole = WorkspaceRole.MEMBER


class AcceptInviteRequest(BaseModel):
    token: str


class MemberResponse(BaseModel):
    id: str
    user_id: str
    name: str
    email: str
    role: str
    joined_at: str


class WorkspaceListResponse(BaseModel):
    id: str
    name: str
    owner_id: str
    role: str
    created_at: str
    updated_at: str


@router_workspace.get("/current", response_model=WorkspaceResponse)
def current_workspace(request: Request, current_user: User = Depends(require_auth), db: Session = Depends(get_db)):
    ws_id_from_token = getattr(request.state, "workspace_id", None)
    if ws_id_from_token:
        ws = get_workspace_by_id(db, ws_id_from_token)
        if ws:
            return WorkspaceResponse(
                id=ws.id,
                name=ws.name,
                owner_id=ws.owner_id,
                created_at=ws.created_at.isoformat() if ws.created_at else "",
                updated_at=ws.updated_at.isoformat() if ws.updated_at else "",
            )
    ws = get_current_workspace(db, current_user.id)
    return WorkspaceResponse(
        id=ws.id,
        name=ws.name,
        owner_id=ws.owner_id,
        created_at=ws.created_at.isoformat() if ws.created_at else "",
        updated_at=ws.updated_at.isoformat() if ws.updated_at else "",
    )


@router_workspace.get("", response_model=list[WorkspaceListResponse])
def list_workspaces(current_user: User = Depends(require_auth), db: Session = Depends(get_db)):
    return get_user_workspaces(db, current_user.id)


@router_workspace.post("", response_model=WorkspaceResponse)
def create_new_workspace(
    req: CreateWorkspaceRequest, current_user: User = Depends(require_auth), db: Session = Depends(get_db)
):
    ws = create_workspace(db, req.name, current_user.id)
    return WorkspaceResponse(
        id=ws.id,
        name=ws.name,
        owner_id=ws.owner_id,
        created_at=ws.created_at.isoformat() if ws.created_at else "",
        updated_at=ws.updated_at.isoformat() if ws.updated_at else "",
    )


@router_workspace.post("/switch", response_model=SwitchWorkspaceResponse)
def switch_workspace_endpoint(
    req: SwitchWorkspaceRequest, current_user: User = Depends(require_auth), db: Session = Depends(get_db)
):
    result = switch_workspace(db, req.workspace_id, current_user.id)
    return SwitchWorkspaceResponse(
        access_token=result["access_token"],
        workspace=WorkspaceResponse(**result["workspace"]),
    )


@router_workspace.get("/members", response_model=list[MemberResponse])
def workspace_members(current_user: User = Depends(require_auth), db: Session = Depends(get_db)):
    workspaces = get_user_workspaces(db, current_user.id)
    if not workspaces:
        raise HTTPException(status_code=404, detail="No workspaces found")
    ws_id = workspaces[0]["id"]
    return get_workspace_members(db, ws_id)


@router_workspace.get("/members/{workspace_id}", response_model=list[MemberResponse])
def workspace_members_by_id(
    workspace_id: str, current_user: User = Depends(require_auth), db: Session = Depends(get_db)
):
    role = get_workspace_role(db, workspace_id, current_user.id)
    if role is None:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")
    return get_workspace_members(db, workspace_id)


@router_workspace.get("/current/members", response_model=list[MemberResponse])
def current_workspace_members(
    request: Request, current_user: User = Depends(require_auth), db: Session = Depends(get_db)
):
    ws_id = get_current_workspace_id(request)
    return get_workspace_members(db, ws_id)


@router_workspace.delete("/current/members/{member_id}")
def remove_current_workspace_member(
    member_id: str, request: Request, current_user: User = Depends(require_auth), db: Session = Depends(get_db)
):
    ws_id = get_current_workspace_id(request)
    remove_member(db, ws_id, member_id, current_user.id)
    return {"message": "Member removed"}


@router_workspace.post("/current/invite")
def invite_current_workspace_member(
    req: InviteRequest, request: Request, current_user: User = Depends(require_auth), db: Session = Depends(get_db)
):
    ws_id = get_current_workspace_id(request)
    return invite_to_workspace(db, ws_id, req.email, req.role, current_user.id)


@router_workspace.post("/accept")
def accept_workspace_invite(
    req: AcceptInviteRequest, current_user: User = Depends(require_auth), db: Session = Depends(get_db)
):
    return accept_invite(db, req.token, current_user.id)


@router_workspace.get("/current/invites", response_model=list[dict])
def current_workspace_pending_invites(
    request: Request, current_user: User = Depends(require_auth), db: Session = Depends(get_db)
):
    ws_id = get_current_workspace_id(request)
    return get_pending_invites(db, ws_id, current_user.id)


# ── Activity Feed ────────────────────────────────────────────────────


class ActivityResponse(BaseModel):
    id: str
    workspace_id: str
    user_id: str
    action: str
    description: str
    resource_type: str
    resource_id: str
    timestamp: str


@router_workspace.get("/current/activity", response_model=list[ActivityResponse])
def workspace_activity(request: Request, current_user: User = Depends(require_auth), limit: int = 50):
    ws_id = get_current_workspace_id(request)
    return get_activities(ws_id, limit)


# ── Notifications ────────────────────────────────────────────────────


class NotificationResponse(BaseModel):
    id: str
    user_id: str
    workspace_id: str
    type: str
    title: str
    message: str
    data: dict
    is_read: bool
    created_at: str


class MarkReadRequest(BaseModel):
    notification_id: str


@router_workspace.get("/notifications", response_model=list[NotificationResponse])
def list_notifications(
    request: Request, current_user: User = Depends(require_auth), unread_only: bool = False, limit: int = 20
):
    ws_id = get_current_workspace_id(request)
    return get_notifications(current_user.id, ws_id, limit, unread_only)


@router_workspace.post("/notifications/mark-read")
def mark_read(req: MarkReadRequest, current_user: User = Depends(require_auth)):
    ok = mark_notification_read(req.notification_id, current_user.id)
    return {"ok": ok}


@router_workspace.post("/notifications/mark-all-read")
def mark_all_read(request: Request, current_user: User = Depends(require_auth)):
    ws_id = get_current_workspace_id(request)
    mark_all_notifications_read(current_user.id, ws_id)
    return {"ok": True}
