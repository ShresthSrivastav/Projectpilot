from services import jwt_service


def test_missing_jwt_env_uses_persistent_shared_secret(monkeypatch, tmp_path):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.setenv("MEMORY_STORE_DIR", str(tmp_path))
    monkeypatch.delenv("JWT_SECRET_FILE", raising=False)
    monkeypatch.setattr(jwt_service, "SECRET_KEY", None)

    first_secret = jwt_service._get_secret()
    secret_file = tmp_path / ".jwt-secret"

    assert secret_file.read_text(encoding="utf-8") == first_secret
    assert len(first_secret) >= 32

    monkeypatch.setattr(jwt_service, "SECRET_KEY", None)
    assert jwt_service._get_secret() == first_secret


def test_configured_jwt_secret_takes_priority(monkeypatch, tmp_path):
    configured = "configured-secret-that-is-long-enough-for-jwt"
    monkeypatch.setenv("JWT_SECRET_KEY", configured)
    monkeypatch.setenv("MEMORY_STORE_DIR", str(tmp_path))
    monkeypatch.setattr(jwt_service, "SECRET_KEY", None)

    assert jwt_service._get_secret() == configured
    assert not (tmp_path / ".jwt-secret").exists()
