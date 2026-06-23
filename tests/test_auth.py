import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Set test DB path BEFORE importing app
os.environ["MEMORY_STORE_DIR"] = tempfile.mkdtemp()
os.environ["RATE_LIMIT_ENABLED"] = "false"

from database.database import Base, SessionLocal, engine, get_db
from database.models import User
from services.auth_service import hash_password

TEST_DB_URL = "sqlite:///./test_projectpilot_auth.db"
_test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
_test_session_local = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)


def override_get_db():
    db = _test_session_local()
    try:
        yield db
    finally:
        db.close()


def _cleanup():
    import gc
    _test_engine.dispose()
    engine.dispose()
    gc.collect()
    for f in ["test_projectpilot_auth.db", "test_projectpilot_auth.db-wal", "test_projectpilot_auth.db-shm"]:
        try:
            if os.path.exists(f):
                os.remove(f)
        except PermissionError:
            pass


@pytest.fixture(autouse=True)
def setup_db():
    _cleanup()
    Base.metadata.create_all(bind=_test_engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=_test_engine)


from backend.main import app

client = TestClient(app)


class TestAuth:
    REGISTER_PAYLOAD = {
        "name": "Test User",
        "email": "test@example.com",
        "password": "password123",
        "confirm_password": "password123",
    }

    def test_register_user(self):
        resp = client.post("/api/auth/register", json=self.REGISTER_PAYLOAD)
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["name"] == "Test User"
        assert data["user"]["email"] == "test@example.com"

    def test_register_duplicate_email(self):
        client.post("/api/auth/register", json=self.REGISTER_PAYLOAD)
        resp = client.post("/api/auth/register", json=self.REGISTER_PAYLOAD)
        assert resp.status_code == 409
        assert "already registered" in resp.json()["detail"].lower()

    def test_register_password_mismatch(self):
        payload = {**self.REGISTER_PAYLOAD, "confirm_password": "different"}
        resp = client.post("/api/auth/register", json=payload)
        assert resp.status_code == 400
        assert "do not match" in resp.json()["detail"].lower()

    def test_register_short_password(self):
        payload = {**self.REGISTER_PAYLOAD, "password": "123", "confirm_password": "123"}
        resp = client.post("/api/auth/register", json=payload)
        assert resp.status_code == 400
        assert "8 characters" in resp.json()["detail"].lower()

    def test_login_success(self):
        client.post("/api/auth/register", json=self.REGISTER_PAYLOAD)
        resp = client.post("/api/auth/login", json={
            "email": self.REGISTER_PAYLOAD["email"],
            "password": self.REGISTER_PAYLOAD["password"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["email"] == "test@example.com"

    def test_login_invalid_credentials(self):
        resp = client.post("/api/auth/login", json={
            "email": "nonexistent@example.com",
            "password": "wrongpass",
        })
        assert resp.status_code == 401
        assert "invalid" in resp.json()["detail"].lower()

    def test_get_me_authenticated(self):
        reg = client.post("/api/auth/register", json=self.REGISTER_PAYLOAD).json()
        access_token = reg["access_token"]
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {access_token}"})
        assert resp.status_code == 200
        user = resp.json()
        assert user["email"] == "test@example.com"
        assert user["name"] == "Test User"
        assert user["is_active"] is True

    def test_get_me_unauthenticated(self):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 403

    def test_refresh_token(self):
        reg = client.post("/api/auth/register", json=self.REGISTER_PAYLOAD).json()
        refresh_token = reg["refresh_token"]
        resp = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["access_token"] != reg["access_token"]

    def test_refresh_token_revoked_after_use(self):
        reg = client.post("/api/auth/register", json=self.REGISTER_PAYLOAD).json()
        refresh_token = reg["refresh_token"]
        client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        resp2 = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        assert resp2.status_code == 401

    def test_logout(self):
        reg = client.post("/api/auth/register", json=self.REGISTER_PAYLOAD).json()
        refresh_token = reg["refresh_token"]
        resp = client.post("/api/auth/logout", json={"refresh_token": refresh_token})
        assert resp.status_code == 200
        refresh_resp = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        assert refresh_resp.status_code == 401

    def test_get_current_workspace(self):
        reg = client.post("/api/auth/register", json=self.REGISTER_PAYLOAD).json()
        access_token = reg["access_token"]
        resp = client.get("/api/workspace/current", headers={"Authorization": f"Bearer {access_token}"})
        assert resp.status_code == 200
        ws = resp.json()
        assert ws["name"] == "Test User Workspace"
        assert "id" in ws
        assert "owner_id" in ws

    def test_workspace_isolation(self):
        reg1 = client.post("/api/auth/register", json=self.REGISTER_PAYLOAD).json()
        reg2 = client.post("/api/auth/register", json={
            "name": "User Two",
            "email": "user2@example.com",
            "password": "password123",
            "confirm_password": "password123",
        }).json()
        ws1 = client.get("/api/workspace/current", headers={"Authorization": f"Bearer {reg1['access_token']}"}).json()
        ws2 = client.get("/api/workspace/current", headers={"Authorization": f"Bearer {reg2['access_token']}"}).json()
        assert ws1["id"] != ws2["id"]
        assert ws1["name"] == "Test User Workspace"
        assert ws2["name"] == "User Two Workspace"
