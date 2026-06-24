"""Token encryption/decryption for GitHub tokens at rest.

Uses Fernet (symmetric AES-128-CBC) with a key derived from a
secret configured in the environment (TOKEN_ENCRYPTION_KEY).

If no key is configured, tokens are stored in plaintext with a warning.
"""

import base64
import logging
import os

logger = logging.getLogger(__name__)

_ENCRYPTION_KEY: bytes | None = None

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:
    Fernet = None  # type: ignore
    InvalidToken = None  # type: ignore


def _get_key() -> bytes | None:
    global _ENCRYPTION_KEY
    if _ENCRYPTION_KEY is not None:
        return _ENCRYPTION_KEY

    raw = os.getenv("TOKEN_ENCRYPTION_KEY", "")
    if not raw:
        logger.warning("TOKEN_ENCRYPTION_KEY not set. Tokens will be stored in plaintext.")
        _ENCRYPTION_KEY = b""
        return None

    try:
        if len(raw) == 64:
            raw_bytes = bytes.fromhex(raw)
            _ENCRYPTION_KEY = base64.urlsafe_b64encode(raw_bytes)
        else:
            _ENCRYPTION_KEY = raw.encode() if isinstance(raw, str) else raw
            try:
                Fernet(_ENCRYPTION_KEY)
            except (ValueError, TypeError):
                padded = base64.urlsafe_b64encode(raw.encode().ljust(32, b"\0")[:32])
                _ENCRYPTION_KEY = padded
        return _ENCRYPTION_KEY
    except Exception as exc:
        logger.warning("Failed to initialise encryption key: %s. Tokens stored in plaintext.", exc)
        return None


def encrypt_token(plaintext: str) -> str:
    if not plaintext:
        return ""
    key = _get_key()
    if key is None or Fernet is None:
        return plaintext
    try:
        f = Fernet(key)
        return f.encrypt(plaintext.encode()).decode()
    except Exception as exc:
        logger.error("Token encryption failed: %s", exc)
        return plaintext


def decrypt_token(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    key = _get_key()
    if key is None or Fernet is None:
        return ciphertext
    try:
        f = Fernet(key)
        return f.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        logger.error("Token decryption failed (invalid token or key changed).")
        return ""
    except Exception as exc:
        logger.error("Token decryption failed: %s", exc)
        return ciphertext


def mask_token(token: str, visible: int = 6) -> str:
    if not token or len(token) <= visible + 4:
        return token[:visible] + "..." if len(token) > visible else token
    return token[:visible] + "*" * (len(token) - visible - 4) + token[-4:]
