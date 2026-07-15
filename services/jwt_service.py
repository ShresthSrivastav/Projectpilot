import logging
import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

logger = logging.getLogger(__name__)

SECRET_KEY = None
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _get_secret() -> str:
    global SECRET_KEY
    if SECRET_KEY is None:
        configured_secret = os.getenv("JWT_SECRET_KEY", "").strip()
        if configured_secret and not configured_secret.startswith("your-"):
            SECRET_KEY = configured_secret
        else:
            memory_dir = Path(
                os.getenv(
                    "MEMORY_STORE_DIR",
                    Path(__file__).resolve().parents[1] / "memory_store",
                )
            )
            secret_path = Path(os.getenv("JWT_SECRET_FILE", memory_dir / ".jwt-secret"))
            secret_path.parent.mkdir(parents=True, exist_ok=True)

            if secret_path.exists():
                SECRET_KEY = secret_path.read_text(encoding="utf-8").strip()
            else:
                candidate = secrets.token_hex(32)
                try:
                    fd = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(fd, "w", encoding="utf-8") as secret_file:
                        secret_file.write(candidate)
                    SECRET_KEY = candidate
                except FileExistsError:
                    # Another worker created the shared secret first.
                    SECRET_KEY = secret_path.read_text(encoding="utf-8").strip()

            if not SECRET_KEY or len(SECRET_KEY) < 32:
                raise RuntimeError(f"JWT secret at {secret_path} must contain at least 32 characters")
            logger.warning(
                "JWT_SECRET_KEY is not configured; using persistent secret file %s",
                secret_path,
            )
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
