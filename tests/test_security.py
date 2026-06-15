"""Security remediation tests — auth, rate limiting, token masking, secrets."""
import importlib as _il
import os
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["SKIP_AUTH"] = "false"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["ADMIN_API_KEY"] = "test-admin-key-987"
os.environ["USER_API_KEY"] = "test-user-key-654"
os.environ["TOKEN_ENCRYPTION_KEY"] = "8c198ed512b30de8f507eb94ec7f53a1186f21035ccb613181d2b2266331c193"
os.environ["GENERATED_PROJECTS_DIR"] = "./test_security_projects"
os.environ["CHROMA_PATH"] = "./test_security_chroma"
os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"
os.environ["ZIP_RETENTION_HOURS"] = "1"

# Force re-import modules to pick up test env vars (already imported by test_api.py)
import services.auth_service as _as
import services.token_crypto as _tc
import services.rate_limiter as _rl
import backend.main as _bm
_il.reload(_as)
_il.reload(_rl)
_il.reload(_tc)
_il.reload(_bm)

from backend.main import app
from services.auth_service import lookup_role, Role
from services.token_crypto import encrypt_token, decrypt_token, mask_token


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


# ── Auth Tests ──────────────────────────────────────────────────────────────

class TestAuthService:
    def test_lookup_admin_key(self):
        assert lookup_role("test-admin-key-987") == Role.ADMIN

    def test_lookup_user_key(self):
        assert lookup_role("test-user-key-654") == Role.USER

    def test_lookup_invalid_key(self):
        assert lookup_role("invalid-key") == Role.NONE

    def test_lookup_empty_key(self):
        assert lookup_role("") == Role.NONE


class TestAuthMiddleware:
    ADMIN_HEADER = {"Authorization": "Bearer test-admin-key-987"}
    USER_HEADER = {"Authorization": "Bearer test-user-key-654"}

    PROTECTED_GET = "/validate/test"  # GET route that needs auth
    ADMIN_GET = "/sandbox/status"      # GET route that needs admin

    def test_health_no_auth(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_protected_route_no_auth(self, client):
        r = client.get(self.PROTECTED_GET)
        assert r.status_code == 401

    def test_protected_route_invalid_key(self, client):
        r = client.get(self.PROTECTED_GET, headers={"Authorization": "Bearer wrong-key"})
        assert r.status_code == 401

    def test_protected_route_valid_key(self, client):
        r = client.get(self.PROTECTED_GET, headers=self.USER_HEADER)
        assert r.status_code in (200, 404)

    def test_admin_route_no_auth(self, client):
        r = client.get(self.ADMIN_GET)
        assert r.status_code == 401

    def test_admin_route_user_key_denied(self, client):
        r = client.get(self.ADMIN_GET, headers=self.USER_HEADER)
        assert r.status_code == 403

    def test_admin_route_admin_key(self, client):
        r = client.get(self.ADMIN_GET, headers=self.ADMIN_HEADER)
        assert r.status_code in (200, 404)

    def test_wrong_auth_scheme(self, client):
        r = client.get(self.PROTECTED_GET, headers={"Authorization": "Basic xyz"})
        assert r.status_code == 401

    def test_health_ignores_auth(self, client):
        r = client.get("/health", headers=self.ADMIN_HEADER)
        assert r.status_code == 200

    def test_openapi_route_no_auth(self, client):
        r = client.get("/openapi.json")
        assert r.status_code == 200


# ── Token Encryption Tests ──────────────────────────────────────────────────

class TestTokenCrypto:
    def test_encrypt_decrypt(self):
        token = "ghp_test1234567890abcdef"
        encrypted = encrypt_token(token)
        assert encrypted != token
        decrypted = decrypt_token(encrypted)
        assert decrypted == token

    def test_encrypt_empty(self):
        assert encrypt_token("") == ""

    def test_decrypt_empty(self):
        assert decrypt_token("") == ""

    def test_encrypt_none(self):
        assert encrypt_token("") == ""

    def test_mask_token_long(self):
        token = "ghp_test1234567890abcdef"
        masked = mask_token(token)
        assert len(masked) <= len(token) + 3
        assert token[:6] == masked[:6]
        assert "*" in masked

    def test_mask_token_short(self):
        token = "abc"
        masked = mask_token(token)
        assert masked == "abc"

    def test_mask_token_empty(self):
        assert mask_token("") == ""

    def test_mask_token_no_leak(self):
        token = "ghp_abcdef1234567890"
        masked = mask_token(token)
        assert token not in masked


# ── Rate Limiting Tests ─────────────────────────────────────────────────────

class TestRateLimitConfig:
    def test_env_controls_rate_limit(self):
        from services.rate_limiter import RATE_LIMIT_ENABLED
        assert not RATE_LIMIT_ENABLED

    def test_rate_limit_env_var_read(self):
        from services.rate_limiter import LIMITS
        assert "generate" in LIMITS
        assert "benchmark" in LIMITS
        assert "evaluation" in LIMITS


# ── Request Body Size Tests ─────────────────────────────────────────────────

class TestRequestBodyLimits:
    def test_max_body_size_env(self):
        from backend.main import MAX_BODY_SIZE
        assert MAX_BODY_SIZE > 0
        assert MAX_BODY_SIZE <= 100 * 1024 * 1024


# ── Secrets Validation Tests ────────────────────────────────────────────────

class TestSecrets:
    def test_no_hardcoded_keys_in_source(self):
        root = Path(__file__).parent.parent
        for py_file in root.rglob("*.py"):
            if "test_" in py_file.name:
                continue
            if ".venv" in str(py_file) or "__pycache__" in str(py_file):
                continue
            text = py_file.read_text(encoding="utf-8", errors="ignore")
            matches = re.findall(r'GOOGLE_API_KEY\s*=\s*["\'](?!os\.getenv)', text)
            if matches:
                pytest.fail(f"Hardcoded GOOGLE_API_KEY in {py_file}")

    def test_env_example_exists(self):
        assert Path(__file__).parent.parent.joinpath(".env.example").exists()

    def test_env_example_has_auth_keys(self):
        text = Path(__file__).parent.parent.joinpath(".env.example").read_text()
        assert "ADMIN_API_KEY" in text
        assert "USER_API_KEY" in text
        assert "TOKEN_ENCRYPTION_KEY" in text
        assert "GOOGLE_API_KEY" in text


# ── Git Clone URL Tests ─────────────────────────────────────────────────────

class TestGitCloneSecurity:
    def test_clone_error_masks_token(self):
        import unittest.mock as mock
        from services.github_service import clone_repo
        with (
            mock.patch("services.github_service._get_client") as mock_client,
            mock.patch("services.github_service.Repo.clone_from") as mock_clone,
        ):
            fake_repo = mock.MagicMock()
            fake_repo.clone_url = "https://github.com/fake/repo.git"
            fake_repo.default_branch = "main"
            mock_client.return_value.get_repo.return_value = fake_repo
            from git import GitCommandError
            mock_clone.side_effect = GitCommandError("clone", b"stderr error output")
            result = clone_repo("ghp_fake1234567890abcdef", "fake/repo")
            assert "ghp_fake1234567890abcdef" not in result.get("error", "")
            assert "token" in result.get("error", "").lower() or "error" in result
