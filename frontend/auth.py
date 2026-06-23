import os
import time

import requests

BACKEND = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")


def backend_url(path: str) -> str:
    return f"{BACKEND}{path}"


def _headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def register(name: str, email: str, password: str, confirm_password: str) -> dict:
    resp = requests.post(
        backend_url("/api/auth/register"),
        json={
            "name": name,
            "email": email,
            "password": password,
            "confirm_password": confirm_password,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def login(email: str, password: str) -> dict:
    resp = requests.post(
        backend_url("/api/auth/login"),
        json={"email": email, "password": password},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def refresh_access_token(refresh_token: str) -> dict:
    resp = requests.post(
        backend_url("/api/auth/refresh"),
        json={"refresh_token": refresh_token},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def get_me(access_token: str) -> dict:
    resp = requests.get(
        backend_url("/api/auth/me"),
        headers=_headers(access_token),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def get_current_workspace(access_token: str) -> dict:
    resp = requests.get(
        backend_url("/api/workspace/current"),
        headers=_headers(access_token),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def logout(refresh_token: str) -> None:
    try:
        requests.post(
            backend_url("/api/auth/logout"),
            json={"refresh_token": refresh_token},
            timeout=15,
        )
    except requests.RequestException:
        pass


# ── Workspace management ─────────────────────────────────────────────


def list_workspaces(access_token: str) -> list[dict]:
    resp = requests.get(
        backend_url("/api/workspace"),
        headers=_headers(access_token),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def create_workspace(access_token: str, name: str) -> dict:
    resp = requests.post(
        backend_url("/api/workspace"),
        headers=_headers(access_token),
        json={"name": name},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def switch_workspace(access_token: str, workspace_id: str) -> dict:
    resp = requests.post(
        backend_url("/api/workspace/switch"),
        headers=_headers(access_token),
        json={"workspace_id": workspace_id},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def get_workspace_members(access_token: str) -> list[dict]:
    resp = requests.get(
        backend_url("/api/workspace/current/members"),
        headers=_headers(access_token),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def invite_member(access_token: str, email: str, role: str = "MEMBER") -> dict:
    resp = requests.post(
        backend_url("/api/workspace/current/invite"),
        headers=_headers(access_token),
        json={"email": email, "role": role},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def remove_member(access_token: str, member_id: str) -> dict:
    resp = requests.delete(
        backend_url(f"/api/workspace/current/members/{member_id}"),
        headers=_headers(access_token),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def get_pending_invites(access_token: str) -> list[dict]:
    resp = requests.get(
        backend_url("/api/workspace/current/invites"),
        headers=_headers(access_token),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def accept_invite(access_token: str, token: str) -> dict:
    resp = requests.post(
        backend_url("/api/workspace/accept"),
        headers=_headers(access_token),
        json={"token": token},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


# ── Activity & Notifications ─────────────────────────────────────────


def get_activities(access_token: str, limit: int = 50) -> list[dict]:
    resp = requests.get(
        backend_url(f"/api/workspace/current/activity?limit={limit}"),
        headers=_headers(access_token),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def get_notifications(access_token: str, unread_only: bool = False, limit: int = 20) -> list[dict]:
    resp = requests.get(
        backend_url(f"/api/workspace/notifications?unread_only={str(unread_only).lower()}&limit={limit}"),
        headers=_headers(access_token),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def mark_notification_read(access_token: str, notification_id: str) -> dict:
    resp = requests.post(
        backend_url("/api/workspace/notifications/mark-read"),
        headers=_headers(access_token),
        json={"notification_id": notification_id},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def mark_all_notifications_read(access_token: str) -> dict:
    resp = requests.post(
        backend_url("/api/workspace/notifications/mark-all-read"),
        headers=_headers(access_token),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()
