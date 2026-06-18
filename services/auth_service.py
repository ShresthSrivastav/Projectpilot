"""Auth service — API key authentication + role-based access control."""
import logging
import os
import secrets
from enum import Enum

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

ADMIN_KEY = os.getenv("ADMIN_API_KEY", "")
USER_KEY = os.getenv("USER_API_KEY", "")

if not ADMIN_KEY:
    ADMIN_KEY = f"ak-admin-{secrets.token_hex(32)}"
    logger.warning("ADMIN_API_KEY not set. Generated ephemeral admin key: %s...%s",
                   ADMIN_KEY[:16], ADMIN_KEY[-8:])

if not USER_KEY:
    USER_KEY = f"ak-user-{secrets.token_hex(32)}"
    logger.warning("USER_API_KEY not set. Generated ephemeral user key: %s...%s",
                   USER_KEY[:16], USER_KEY[-8:])


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


def require_role(required: Role):
    def _check(role: Role = Depends(get_api_key_role)) -> None:
        if role.value < required.value if hasattr(role.value, '__lt__') else role != required and role != Role.ADMIN:
            raise HTTPException(status_code=403, detail=f"{required.value} access required.")
    return _check


def get_current_role(role: Role = Depends(get_api_key_role)) -> Role:
    return role
