"""Tests for multi-workspace support, invitations, RBAC, and workspace switching."""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ["MEMORY_STORE_DIR"] = tempfile.mkdtemp()
os.environ["RATE_LIMIT_ENABLED"] = "false"

from database.database import Base, SessionLocal, engine, get_db
from database.models import User

TEST_DB_URL = "sqlite:///./test_multi_workspace.db"
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
    for f in ["test_multi_workspace.db", "test_multi_workspace.db-wal", "test_multi_workspace.db-shm"]:
        try:
            if os.path.exists(f):
                os.remove(f)
        except PermissionError:
            pass


from backend.main import app

client = TestClient(app)


def _register(name: str, email: str):
    resp = client.post(
        "/api/auth/register",
        json={
            "name": name,
            "email": email,
            "password": "password123",
            "confirm_password": "password123",
        },
    )
    assert resp.status_code == 200
    return resp.json()


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def setup_db():
    _cleanup()
    Base.metadata.create_all(bind=_test_engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=_test_engine)


class TestMultiWorkspace:
    """Tests for creating, listing, and switching workspaces."""

    def test_create_workspace(self):
        reg = _register("Alice", "alice@example.com")
        resp = client.post("/api/workspace", json={"name": "Alice Proj"}, headers=_auth_header(reg["access_token"]))
        assert resp.status_code == 200
        ws = resp.json()
        assert ws["name"] == "Alice Proj"
        assert ws["owner_id"] is not None

    def test_list_workspaces(self):
        reg = _register("Bob", "bob@example.com")
        # Should have the personal workspace
        resp = client.get("/api/workspace", headers=_auth_header(reg["access_token"]))
        assert resp.status_code == 200
        workspaces = resp.json()
        assert len(workspaces) >= 1
        names = [w["name"] for w in workspaces]
        assert "Bob Workspace" in names
        # Bob's role should be OWNER
        bob_ws = [w for w in workspaces if w["name"] == "Bob Workspace"][0]
        assert bob_ws["role"] == "OWNER"

    def test_create_multiple_workspaces(self):
        reg = _register("Carol", "carol@example.com")
        client.post("/api/workspace", json={"name": "Carol Work"}, headers=_auth_header(reg["access_token"]))
        client.post("/api/workspace", json={"name": "Carol Side"}, headers=_auth_header(reg["access_token"]))
        resp = client.get("/api/workspace", headers=_auth_header(reg["access_token"]))
        assert resp.status_code == 200
        workspaces = resp.json()
        names = [w["name"] for w in workspaces]
        assert "Carol Workspace" in names
        assert "Carol Work" in names
        assert "Carol Side" in names
        assert len(workspaces) == 3

    def test_switch_workspace(self):
        reg = _register("Dave", "dave@example.com")
        # Create a second workspace
        ws2 = client.post(
            "/api/workspace", json={"name": "Dave Side"}, headers=_auth_header(reg["access_token"])
        ).json()
        # Switch to it
        switch_resp = client.post(
            "/api/workspace/switch", json={"workspace_id": ws2["id"]}, headers=_auth_header(reg["access_token"])
        )
        assert switch_resp.status_code == 200
        data = switch_resp.json()
        assert "access_token" in data
        assert data["workspace"]["name"] == "Dave Side"
        # New token should point to the switched workspace
        new_token = data["access_token"]
        current_resp = client.get("/api/workspace/current", headers=_auth_header(new_token))
        assert current_resp.status_code == 200
        assert current_resp.json()["name"] == "Dave Side"

    def test_switch_to_non_member_workspace_fails(self):
        alice = _register("Alice", "alice2@example.com")
        bob = _register("Bob", "bob2@example.com")
        bob_ws = client.get("/api/workspace", headers=_auth_header(bob["access_token"])).json()
        bob_ws_id = bob_ws[0]["id"]
        # Alice tries to switch to Bob's workspace
        switch_resp = client.post(
            "/api/workspace/switch", json={"workspace_id": bob_ws_id}, headers=_auth_header(alice["access_token"])
        )
        assert switch_resp.status_code == 403


class TestInvitations:
    """Tests for inviting users and accepting invites."""

    def test_invite_and_accept(self):
        alice = _register("Alice", "alice3@example.com")
        bob = _register("Bob", "bob3@example.com")
        bob_ws = client.get("/api/workspace", headers=_auth_header(bob["access_token"])).json()
        bob_ws_id = bob_ws[0]["id"]

        # Switch Bob to his workspace first, then invite Alice
        switch_resp = client.post(
            "/api/workspace/switch", json={"workspace_id": bob_ws_id}, headers=_auth_header(bob["access_token"])
        )
        bob_new_token = switch_resp.json()["access_token"]

        invite_resp = client.post(
            "/api/workspace/current/invite",
            json={"email": "alice3@example.com", "role": "MEMBER"},
            headers=_auth_header(bob_new_token),
        )
        assert invite_resp.status_code == 200
        token = invite_resp.json()["token"]
        assert token

        # Alice accepts
        accept_resp = client.post(
            "/api/workspace/accept", json={"token": token}, headers=_auth_header(alice["access_token"])
        )
        assert accept_resp.status_code == 200
        assert accept_resp.json()["workspace_id"] == bob_ws_id

        # Alice should now see Bob's workspace in her list
        alice_ws = client.get("/api/workspace", headers=_auth_header(alice["access_token"])).json()
        ws_ids = [w["id"] for w in alice_ws]
        assert bob_ws_id in ws_ids

    def test_invite_wrong_email_fails(self):
        alice = _register("Alice", "alice4@example.com")
        bob = _register("Bob", "bob4@example.com")
        inviter_reg = _register("Inviter", "inviter@example.com")
        inviter_ws = client.get("/api/workspace", headers=_auth_header(inviter_reg["access_token"])).json()
        inviter_ws_id = inviter_ws[0]["id"]

        switch = client.post(
            "/api/workspace/switch",
            json={"workspace_id": inviter_ws_id},
            headers=_auth_header(inviter_reg["access_token"]),
        ).json()
        inviter_token = switch["access_token"]

        invite = client.post(
            "/api/workspace/current/invite",
            json={"email": "alice4@example.com", "role": "MEMBER"},
            headers=_auth_header(inviter_token),
        ).json()

        # Bob tries to accept with a different email
        accept = client.post(
            "/api/workspace/accept", json={"token": invite["token"]}, headers=_auth_header(bob["access_token"])
        )
        assert accept.status_code == 403

    def test_double_invite_fails(self):
        reg = _register("Owner", "owner@example.com")

        # Invite same person twice
        client.post(
            "/api/workspace/current/invite",
            json={"email": "existing@example.com", "role": "MEMBER"},
            headers=_auth_header(reg["access_token"]),
        )
        invite2 = client.post(
            "/api/workspace/current/invite",
            json={"email": "existing@example.com", "role": "MEMBER"},
            headers=_auth_header(reg["access_token"]),
        )
        # Should still work (invite again before accept)
        assert invite2.status_code == 200

    def test_pending_invites(self):
        reg = _register("Admin", "admin@example.com")
        client.post(
            "/api/workspace/current/invite",
            json={"email": "user1@example.com", "role": "MEMBER"},
            headers=_auth_header(reg["access_token"]),
        )
        client.post(
            "/api/workspace/current/invite",
            json={"email": "user2@example.com", "role": "ADMIN"},
            headers=_auth_header(reg["access_token"]),
        )
        invites = client.get("/api/workspace/current/invites", headers=_auth_header(reg["access_token"]))
        assert invites.status_code == 200
        data = invites.json()
        assert len(data) == 2
        emails = [i["email"] for i in data]
        assert "user1@example.com" in emails
        assert "user2@example.com" in emails


class TestMembers:
    """Tests for workspace members."""

    def test_members_list(self):
        reg = _register("Owner", "owner2@example.com")
        members = client.get("/api/workspace/current/members", headers=_auth_header(reg["access_token"])).json()
        assert len(members) == 1
        assert members[0]["name"] == "Owner"
        assert members[0]["role"] == "OWNER"

    def test_members_after_invite(self):
        owner = _register("Owner", "owner3@example.com")
        user_a = _register("UserA", "usera@example.com")
        user_b = _register("UserB", "userb@example.com")

        # Owner invites both
        invite_a = client.post(
            "/api/workspace/current/invite",
            json={"email": "usera@example.com", "role": "MEMBER"},
            headers=_auth_header(owner["access_token"]),
        ).json()
        invite_b = client.post(
            "/api/workspace/current/invite",
            json={"email": "userb@example.com", "role": "VIEWER"},
            headers=_auth_header(owner["access_token"]),
        ).json()

        # Both accept
        client.post(
            "/api/workspace/accept", json={"token": invite_a["token"]}, headers=_auth_header(user_a["access_token"])
        )
        client.post(
            "/api/workspace/accept", json={"token": invite_b["token"]}, headers=_auth_header(user_b["access_token"])
        )

        members = client.get("/api/workspace/current/members", headers=_auth_header(owner["access_token"])).json()
        assert len(members) == 3
        roles = {m["name"]: m["role"] for m in members}
        assert roles["Owner"] == "OWNER"
        assert roles["UserA"] == "MEMBER"
        assert roles["UserB"] == "VIEWER"

    def test_remove_member(self):
        owner = _register("Owner", "owner4@example.com")
        user = _register("User", "user4@example.com")

        invite = client.post(
            "/api/workspace/current/invite",
            json={"email": "user4@example.com", "role": "MEMBER"},
            headers=_auth_header(owner["access_token"]),
        ).json()
        client.post(
            "/api/workspace/accept", json={"token": invite["token"]}, headers=_auth_header(user["access_token"])
        )

        members = client.get("/api/workspace/current/members", headers=_auth_header(owner["access_token"])).json()
        member_to_remove = [m for m in members if m["name"] == "User"][0]

        remove = client.delete(
            f"/api/workspace/current/members/{member_to_remove['id']}", headers=_auth_header(owner["access_token"])
        )
        assert remove.status_code == 200

        members_after = client.get("/api/workspace/current/members", headers=_auth_header(owner["access_token"])).json()
        assert len(members_after) == 1


class TestActivity:
    """Tests for workspace activity feed."""

    def test_activity_on_create(self):
        reg = _register("User", "activity@example.com")
        resp = client.get("/api/workspace/current/activity", headers=_auth_header(reg["access_token"]))
        assert resp.status_code == 200
        activities = resp.json()
        assert len(activities) >= 1
        # First activity should be workspace creation
        assert activities[0]["action"] == "workspace.created"

    def test_activity_on_invite(self):
        owner = _register("Owner", "actowner@example.com")
        client.post(
            "/api/workspace/current/invite",
            json={"email": "someone@example.com", "role": "MEMBER"},
            headers=_auth_header(owner["access_token"]),
        )
        activities = client.get("/api/workspace/current/activity", headers=_auth_header(owner["access_token"])).json()
        actions = [a["action"] for a in activities]
        assert "member.invited" in actions


class TestWorkspaceSwitcher:
    """Tests for the workspace switcher in sidebar integration."""

    def test_list_workspaces_returns_role(self):
        reg = _register("User", "switchtest@example.com")
        resp = client.get("/api/workspace", headers=_auth_header(reg["access_token"]))
        assert resp.status_code == 200
        for ws in resp.json():
            assert "role" in ws

    def test_workspace_create_and_list(self):
        reg = _register("User", "createlist@example.com")
        client.post("/api/workspace", json={"name": "Extra WS"}, headers=_auth_header(reg["access_token"]))
        workspaces = client.get("/api/workspace", headers=_auth_header(reg["access_token"])).json()
        assert len(workspaces) == 2

    def test_workspace_switch_updates_token_ws(self):
        reg = _register("User", "tokentest@example.com")
        ws2 = client.post(
            "/api/workspace", json={"name": "Token Test WS"}, headers=_auth_header(reg["access_token"])
        ).json()
        switch = client.post(
            "/api/workspace/switch", json={"workspace_id": ws2["id"]}, headers=_auth_header(reg["access_token"])
        ).json()
        # The new token should have ws claim = ws2.id
        new_token = switch["access_token"]
        current = client.get("/api/workspace/current", headers=_auth_header(new_token)).json()
        assert current["id"] == ws2["id"]

    def test_non_member_cannot_switch(self):
        a = _register("A", "a_nm@example.com")
        b = _register("B", "b_nm@example.com")
        b_ws = client.get("/api/workspace", headers=_auth_header(b["access_token"])).json()
        switch = client.post(
            "/api/workspace/switch", json={"workspace_id": b_ws[0]["id"]}, headers=_auth_header(a["access_token"])
        )
        assert switch.status_code == 403
