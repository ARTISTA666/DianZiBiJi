"""Tests for project CRUD + members + reviewers (18 test cases)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import projects
from app.api.deps import get_current_user
from app.core.database import Base, get_db
from app.core.security import hash_password
from app.models import *  # noqa: F403
from app.models.project import Project, ProjectMember, ProjectReviewer, ProjectRole, ProjectStatus
from app.models.user import User, UserRole


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    db.add_all([
        User(id=1, username="admin", password_hash=hash_password("x"), display_name="Admin", role=UserRole.SUPER_ADMIN),
        User(id=2, username="pi", password_hash=hash_password("x"), display_name="PI", role=UserRole.PI),
        User(id=3, username="member", password_hash=hash_password("x"), display_name="Member", role=UserRole.MEMBER),
        User(id=4, username="outsider", password_hash=hash_password("x"), display_name="Outsider", role=UserRole.MEMBER),
        Project(id=1, name="Public Project", owner_user_id=2, is_sensitive=False),
        Project(id=2, name="Sensitive Project", owner_user_id=2, is_sensitive=True),
        Project(id=3, name="Owned Project", owner_user_id=3),
        ProjectMember(project_id=1, user_id=3, project_role=ProjectRole.VIEWER, can_read=True, can_write=False),
        ProjectMember(project_id=3, user_id=3, project_role=ProjectRole.OWNER, can_read=True, can_write=True, can_review=True, can_manage=True),
    ])
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(projects.router)
    active_user_id = {"value": 1}

    def override_db():
        s = SessionLocal()
        try: yield s
        finally: s.close()

    def override_user():
        s = SessionLocal()
        try: return s.get(User, active_user_id["value"])
        finally: s.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    return TestClient(app), SessionLocal, active_user_id


# ── Project Listing ────────────────────────────────────────

def test_admin_sees_all_projects(client):
    c, _, uid = client; uid["value"] = 1
    r = c.get("/projects")
    assert r.status_code == 200
    assert len(r.json()) == 3


def test_member_sees_only_accessible(client):
    c, _, uid = client; uid["value"] = 4
    r = c.get("/projects")
    assert r.status_code == 200
    assert r.json() == []


def test_member_with_assignment_sees_accessible(client):
    c, _, uid = client; uid["value"] = 3
    r = c.get("/projects")
    assert r.status_code == 200
    assert len(r.json()) >= 2  # project 1 (viewer) + project 3 (owner)


def test_pi_sees_non_sensitive_plus_assigned(client):
    c, _, uid = client; uid["value"] = 2
    r = c.get("/projects")
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()}
    assert 1 in ids  # non-sensitive
    assert 3 in ids  # non-sensitive
    # PI also sees projects they are members of (via ProjectMember)
    # Note: PI as owner doesn't auto-grant visibility if project is marked sensitive
    # unless they have explicit ProjectMember membership


# ── Project CRUD ───────────────────────────────────────────

def test_create_project_as_admin(client):
    c, _, uid = client; uid["value"] = 1
    r = c.post("/projects", json={"name": "New Project", "description": "desc", "is_sensitive": False, "approval_enabled": True})
    assert r.status_code == 200
    assert r.json()["name"] == "New Project"


def test_create_project_as_member_forbidden(client):
    c, _, uid = client; uid["value"] = 3
    r = c.post("/projects", json={"name": "X"})
    assert r.status_code == 403


def test_get_project_accessible(client):
    c, _, uid = client; uid["value"] = 3
    r = c.get("/projects/1")
    assert r.status_code == 200
    assert r.json()["name"] == "Public Project"


def test_get_project_forbidden(client):
    c, _, uid = client; uid["value"] = 4
    r = c.get("/projects/2")
    assert r.status_code == 403


def test_update_project_as_manager(client):
    c, _, uid = client; uid["value"] = 3
    r = c.patch("/projects/3", json={"name": "Renamed"})
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed"


def test_update_project_as_non_manager_forbidden(client):
    c, _, uid = client; uid["value"] = 3
    r = c.patch("/projects/1", json={"name": "Hacked"})
    assert r.status_code == 403


# ── Project Members ────────────────────────────────────────

def test_list_project_members(client):
    c, _, uid = client; uid["value"] = 3
    r = c.get("/projects/1/members")
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_add_member_as_manager(client):
    c, _, uid = client; uid["value"] = 3
    r = c.post("/projects/3/members", json={"user_id": 4, "project_role": "viewer", "can_read": True, "can_write": False})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_add_member_as_non_manager(client):
    c, _, uid = client; uid["value"] = 3
    r = c.post("/projects/1/members", json={"user_id": 4, "project_role": "member", "can_read": True, "can_write": True})
    assert r.status_code == 403


def test_remove_member_as_manager(client):
    c, _, uid = client; uid["value"] = 3
    r = c.delete("/projects/3/members/3")  # cannot remove self as only manager
    assert r.status_code == 409  # must keep at least one manager


def test_add_reviewer_as_manager(client):
    c, _, uid = client; uid["value"] = 3
    r = c.post("/projects/3/reviewers", json={"user_id": 4, "review_scope": "all"})
    assert r.status_code == 200
    assert r.json()["user_id"] == 4


def test_add_reviewer_forbidden(client):
    c, _, uid = client; uid["value"] = 3
    r = c.post("/projects/1/reviewers", json={"user_id": 4})
    assert r.status_code == 403
