import hashlib
import logging
import os
import secrets
from datetime import UTC, datetime
from enum import Enum
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import RefreshToken, User
from services.jwt_service import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from services.workspace_service import create_workspace_for_user, get_current_workspace, get_user_workspaces

logger = logging.getLogger(__name__)

# ── Existing API key auth (kept for backward compatibility) ──────────────

ADMIN_KEY = os.getenv("ADMIN_API_KEY", "")
USER_KEY = os.getenv("USER_API_KEY", "")

if not ADMIN_KEY:
    ADMIN_KEY = f"ak-admin-{secrets.token_hex(32)}"
    logger.warning("ADMIN_API_KEY not set. Generated ephemeral admin key: %s...%s", ADMIN_KEY[:16], ADMIN_KEY[-8:])

if not USER_KEY:
    USER_KEY = f"ak-user-{secrets.token_hex(32)}"
    logger.warning("USER_API_KEY not set. Generated ephemeral user key: %s...%s", USER_KEY[:16], USER_KEY[-8:])


class Role(str, Enum):
    ADMIN = "admin"
    USER = "user"
    NONE = "none"


_API_KEYS: dict[str, Role] = {}

def _init_keys():
    _API_KEYS.clear()
    if ADMIN_KEY:
        _API_KEYS[ADMIN_KEY] = Role.ADMIN
    if USER_KEY:
        _API_KEYS[USER_KEY] = Role.USER

_init_keys()

bearer_scheme = HTTPBearer(auto_error=False)


def get_api_key_role(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> Role:
    if credentials is None:
        return Role.NONE
    return _API_KEYS.get(credentials.credentials, Role.NONE)


def lookup_role(api_key: str) -> Role:
    return _API_KEYS.get(api_key, Role.NONE)


def require_admin(role: Role = Depends(get_api_key_role)) -> None:
    if role != Role.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required.")


def require_user(role: Role = Depends(get_api_key_role)) -> None:
    if role not in (Role.ADMIN, Role.USER):
        raise HTTPException(status_code=401, detail="Authentication required.")


# ── Pydantic schemas ────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    confirm_password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    is_active: bool
    created_at: str
    last_login: Optional[str] = None


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    owner_id: str
    created_at: str
    updated_at: str


class SwitchWorkspaceResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    workspace: WorkspaceResponse


# ── JWT auth dependencies ───────────────────────────────────────────────

def get_current_user(db: Session = Depends(get_db), credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=True))) -> User:
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired access token")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


def require_auth(current_user: User = Depends(get_current_user)) -> User:
    return current_user


def get_current_user_optional(db: Session = Depends(get_db), credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)) -> Optional[User]:
    if credentials is None:
        return None
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id, User.is_active == True).first()


# ── Auth service methods ────────────────────────────────────────────────

def register_user(db: Session, req: RegisterRequest) -> AuthResponse:
    if req.password != req.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    existing = db.query(User).filter(User.email == req.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        name=req.name,
        email=req.email,
        password_hash=hash_password(req.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    workspace = create_workspace_for_user(db, user)

    access_token = create_access_token(user.id, workspace.id)
    refresh_token = create_refresh_token(user.id)
    _store_refresh_token(db, user.id, refresh_token)

    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=_user_to_dict(user),
    )


def login_user(db: Session, req: LoginRequest) -> AuthResponse:
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")

    user.last_login = datetime.now(UTC)
    db.commit()

    workspaces = get_user_workspaces(db, user.id)
    workspace_id = workspaces[0]["id"] if workspaces else None

    access_token = create_access_token(user.id, workspace_id)
    refresh_token = create_refresh_token(user.id)
    _store_refresh_token(db, user.id, refresh_token)

    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=_user_to_dict(user),
    )


def refresh_access_token(db: Session, refresh_token_str: str) -> AuthResponse:
    payload = decode_refresh_token(refresh_token_str)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    token_hash = hashlib.sha256(refresh_token_str.encode()).hexdigest()
    stored = db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash,
        RefreshToken.expires_at > datetime.now(UTC),
    ).first()

    if not stored:
        raise HTTPException(status_code=401, detail="Refresh token revoked or expired")

    user = db.query(User).filter(User.id == payload["sub"], User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    # Rotate: delete old token, issue new ones
    db.delete(stored)

    workspaces = get_user_workspaces(db, user.id)
    workspace_id = workspaces[0]["id"] if workspaces else None

    new_access = create_access_token(user.id, workspace_id)
    new_refresh = create_refresh_token(user.id)
    _store_refresh_token(db, user.id, new_refresh)
    db.commit()

    return AuthResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        user=_user_to_dict(user),
    )


def logout_user(db: Session, refresh_token_str: str) -> None:
    token_hash = hashlib.sha256(refresh_token_str.encode()).hexdigest()
    stored = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
    if stored:
        db.delete(stored)
        db.commit()


def get_me(db: Session, user_id: str) -> UserResponse:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_to_response(user)


# ── Helpers ─────────────────────────────────────────────────────────────

def _store_refresh_token(db: Session, user_id: str, token_str: str) -> None:
    import hashlib
    from datetime import UTC, datetime, timedelta
    token_hash = hashlib.sha256(token_str.encode()).hexdigest()
    rt = RefreshToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    db.add(rt)
    db.commit()


def _user_to_dict(user: User) -> dict:
    return {"id": user.id, "name": user.name, "email": user.email}


def _user_to_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        is_active=user.is_active,
        created_at=user.created_at.isoformat() if user.created_at else "",
        last_login=user.last_login.isoformat() if user.last_login else None,
    )
