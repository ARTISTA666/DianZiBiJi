"""Tests for auth + user management endpoints (17 test cases)."""

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import auth, users
from app.api.deps import get_current_user
from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.models import *  # noqa: F403
from app.models.user import User, UserRole, UserStatus


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

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
        "username": "new_user", "password": "Pass123", "display_name": "New", "email": "new@test.com", "role": "member",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["username"] == "new_user"
    assert body["role"] == "member"
    assert body["status"] == "active"


def test_create_user_as_member_forbidden(client):
    c, _, token = client
    token["value"] = "2"
    r = c.post("/users", json={"username": "x", "password": "x", "display_name": "X"})
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
