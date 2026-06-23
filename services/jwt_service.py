import uuid
from datetime import UTC, datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

SECRET_KEY = None
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _get_secret() -> str:
    global SECRET_KEY
    if SECRET_KEY is None:
        import os
        SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
        if not SECRET_KEY:
            import secrets
            SECRET_KEY = secrets.token_hex(32)
    return SECRET_KEY


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: str, workspace_id: Optional[str] = None) -> str:
    now = datetime.now(UTC)
    payload = {
        "jti": str(uuid.uuid4()),
        "sub": user_id,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    if workspace_id:
        payload["ws"] = workspace_id
    return jwt.encode(payload, _get_secret(), algorithm=ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    now = datetime.now(UTC)
    token_id = str(uuid.uuid4())
    payload = {
        "jti": token_id,
        "sub": user_id,
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, _get_secret(), algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, _get_secret(), algorithms=[ALGORITHM])
    except JWTError:
        return None


def decode_access_token(token: str) -> Optional[dict]:
    payload = decode_token(token)
    if payload and payload.get("type") == "access":
        return payload
    return None


def decode_refresh_token(token: str) -> Optional[dict]:
    payload = decode_token(token)
    if payload and payload.get("type") == "refresh":
        return payload
    return None
