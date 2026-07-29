"""Tests for auth + user management endpoints (20 test cases)."""

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api import auth, users
from app.api.auth import _reset_rate_limiter_state
from app.api.deps import get_current_user
from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.models import *  # noqa: F403
from app.models.user import User, UserRole, UserStatus


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Ensure each test starts with a clean rate-limiter state."""
    _reset_rate_limiter_state()
    yield
    _reset_rate_limiter_state()


@pytest.fixture()
def client(db_engine):
    SessionLocal = sessionmaker(bind=db_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=db_engine)

    # Create seed users
    db = SessionLocal()
    db.add_all([
        User(id=1, username="admin", password_hash=hash_password("admin123"), display_name="Admin", role=UserRole.SUPER_ADMIN),
        User(id=2, username="member", password_hash=hash_password("pass"), display_name="Member", role=UserRole.MEMBER),
        User(id=3, username="disabled", password_hash=hash_password("pass"), display_name="Disabled", role=UserRole.MEMBER, status=UserStatus.DISABLED),
    ])
    db.commit()
    db.close()

    # Build app with overrides
    app = FastAPI()
    app.include_router(auth.router)
    app.include_router(users.router)
    active_token: dict = {"value": None}

    def override_db():
        s = SessionLocal()
        try: yield s
        finally: s.close()

    def override_user():
        s = SessionLocal()
        try:
            uid = active_token["value"]
            if uid is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
            return s.get(User, int(uid))
        finally: s.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    return TestClient(app), SessionLocal, active_token


# ── Auth ───────────────────────────────────────────────────

def test_login_success(client):
    c, _, token = client
    r = c.post("/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_login_bad_password(client):
    r = client[0].post("/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_login_disabled_user(client):
    r = client[0].post("/auth/login", json={"username": "disabled", "password": "pass"})
    assert r.status_code == 401


def test_login_nonexistent_user(client):
    r = client[0].post("/auth/login", json={"username": "ghost", "password": "x"})
    assert r.status_code == 401


def test_me_authenticated(client):
    c, _, token = client
    token["value"] = "1"
    r = c.get("/auth/me")
    assert r.status_code == 200
    assert r.json()["username"] == "admin"


def test_me_unauthenticated(client):
    # No token set → override raises 401
    r = client[0].get("/auth/me")
    assert r.status_code == 401


def test_logout(client):
    c, _, token = client
    token["value"] = "1"
    r = c.post("/auth/logout")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


# ── User CRUD ──────────────────────────────────────────────

def test_list_users_as_admin(client):
    c, _, token = client
    token["value"] = "1"
    r = c.get("/users")
    assert r.status_code == 200
    assert len(r.json()) == 3


def test_list_users_as_member(client):
    c, _, token = client
    token["value"] = "2"
    r = c.get("/users")
    assert r.status_code == 200  # any authenticated user can list


def test_create_user_as_admin(client):
    c, _, token = client
    token["value"] = "1"
    r = c.post("/users", json={
        "username": "new_user", "password": "Pass1234", "display_name": "New", "email": "new@test.com", "role": "member",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["username"] == "new_user"
    assert body["role"] == "member"
    assert body["status"] == "active"


def test_create_user_rejects_duplicate_username(client):
    c, _, token = client
    token["value"] = "1"

    response = c.post("/users", json={
        "username": "member", "password": "Pass1234", "display_name": "Duplicate",
    })

    assert response.status_code == 409
    assert response.json()["detail"] == "Username already exists"


def test_create_user_as_member_forbidden(client):
    c, _, token = client
    token["value"] = "2"
    r = c.post("/users", json={"username": "user_x", "password": "Password123", "display_name": "X"})
    assert r.status_code == 403


def test_update_user_as_admin(client):
    c, _, token = client
    token["value"] = "1"
    r = c.patch("/users/2", json={"display_name": "Updated Name", "email": "updated@test.com"})
    assert r.status_code == 200
    body = r.json()
    assert body["display_name"] == "Updated Name"


def test_update_user_not_found(client):
    c, _, token = client
    token["value"] = "1"
    r = c.patch("/users/999", json={"display_name": "X"})
    assert r.status_code == 404


def test_disable_user_as_admin(client):
    c, _, token = client
    token["value"] = "1"
    r = c.post("/users/2/disable")
    assert r.status_code == 200
    assert r.json()["status"] == "disabled"


def test_cannot_disable_self(client):
    c, _, token = client
    token["value"] = "1"
    r = c.post("/users/1/disable")
    assert r.status_code == 409


def test_disable_nonexistent_user(client):
    c, _, token = client
    token["value"] = "1"
    r = c.post("/users/999/disable")
    assert r.status_code == 404


def test_password_change_revokes_old_token_and_returns_replacement(client):
    c, _, _ = client
    c.app.dependency_overrides.pop(get_current_user)
    old_token = c.post("/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]

    response = c.post(
        "/users/me/password",
        headers={"Authorization": f"Bearer {old_token}"},
        json={"current_password": "admin123", "new_password": "NewPassword123"},
    )

    assert response.status_code == 200
    new_token = response.json()["access_token"]
    # The auth cookie must be refreshed alongside the auth_version bump.
    assert "eln_access_token" in response.headers.get("set-cookie", "")
    assert c.get("/auth/me", headers={"Authorization": f"Bearer {old_token}"}).status_code == 401
    assert c.get("/auth/me", headers={"Authorization": f"Bearer {new_token}"}).status_code == 200
    assert c.post("/auth/login", json={"username": "admin", "password": "admin123"}).status_code == 401
    assert c.post("/auth/login", json={"username": "admin", "password": "NewPassword123"}).status_code == 200


def test_logout_revokes_presented_token(client):
    c, _, _ = client
    c.app.dependency_overrides.pop(get_current_user)
    token = c.post("/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert c.post("/auth/logout", headers=headers).status_code == 200
    assert c.get("/auth/me", headers=headers).status_code == 401


# ── Cookie session ─────────────────────────────────────────

def test_login_sets_httponly_cookie_that_authenticates(client):
    c, _, _ = client
    c.app.dependency_overrides.pop(get_current_user)

    r = c.post("/auth/login", json={"username": "admin", "password": "admin123"})

    assert r.status_code == 200
    set_cookie = r.headers.get("set-cookie", "")
    assert "eln_access_token=" in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()
    # No Authorization header: the HttpOnly cookie authenticates the browser.
    me = c.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "admin"


def test_logout_clears_cookie_session(client):
    c, _, _ = client
    c.app.dependency_overrides.pop(get_current_user)
    c.post("/auth/login", json={"username": "admin", "password": "admin123"})
    assert c.get("/auth/me").status_code == 200

    assert c.post("/auth/logout").status_code == 200

    assert c.get("/auth/me").status_code == 401


# ── IP rate limiting ───────────────────────────────────────


def test_login_rate_limit_blocks_after_exhausting_attempts(client, monkeypatch):
    c, _, _ = client
    c.app.dependency_overrides.pop(get_current_user)
    monkeypatch.setattr("app.api.auth.get_settings", lambda: _FakeSettings(max_attempts=3, window=60))

    for _ in range(3):
        r = c.post("/auth/login", json={"username": "admin", "password": "wrong"})
        assert r.status_code == 401

    r = c.post("/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 429
    assert "Too many" in r.json()["detail"]


def test_login_rate_limit_cleared_on_success(client, monkeypatch):
    c, _, _ = client
    c.app.dependency_overrides.pop(get_current_user)
    monkeypatch.setattr("app.api.auth.get_settings", lambda: _FakeSettings(max_attempts=3, window=60))

    # Two failures then a success should reset the counter.
    c.post("/auth/login", json={"username": "admin", "password": "wrong"})
    c.post("/auth/login", json={"username": "admin", "password": "wrong"})
    r = c.post("/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200

    # Three more failures should NOT be blocked (counter was cleared).
    for _ in range(3):
        r = c.post("/auth/login", json={"username": "admin", "password": "wrong"})
        assert r.status_code in (401, 200)  # 401 for bad password; still under limit


def test_login_rate_limit_respects_x_forwarded_for(client, monkeypatch):
    c, _, _ = client
    c.app.dependency_overrides.pop(get_current_user)
    monkeypatch.setattr("app.api.auth.get_settings", lambda: _FakeSettings(max_attempts=2, window=60))

    headers_a = {"X-Forwarded-For": "10.0.0.1"}
    headers_b = {"X-Forwarded-For": "10.0.0.2"}

    # IP-A exhausts its limit.
    c.post("/auth/login", json={"username": "admin", "password": "wrong"}, headers=headers_a)
    c.post("/auth/login", json={"username": "admin", "password": "wrong"}, headers=headers_a)
    r = c.post("/auth/login", json={"username": "admin", "password": "wrong"}, headers=headers_a)
    assert r.status_code == 429

    # IP-B is unaffected.
    r = c.post("/auth/login", json={"username": "admin", "password": "wrong"}, headers=headers_b)
    assert r.status_code == 401


class _FakeSettings:
    """Minimal stand-in for app.core.config.Settings."""

    def __init__(self, max_attempts: int, window: int):
        self.login_ip_rate_limit_max_attempts = max_attempts
        self.login_ip_rate_limit_window_seconds = window
        # Fields accessed by set_auth_cookie:
        self.access_token_expire_minutes = 480
        self.app_env = "test"
