"""Tests for group management + audit logs (8 test cases)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api import audit, groups
from app.api.deps import get_current_user
from app.core.database import Base, get_db
from app.core.security import hash_password
from app.models import *  # noqa: F403
from app.models.audit import AuditLog
from app.models.group import Group, GroupMember
from app.models.user import User, UserRole


@pytest.fixture()
def client(db_engine):
    SessionLocal = sessionmaker(bind=db_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=db_engine)

    db = SessionLocal()
    db.add_all([
        User(id=1, username="admin", password_hash=hash_password("x"), display_name="Admin", role=UserRole.SUPER_ADMIN),
        User(id=2, username="member", password_hash=hash_password("x"), display_name="Member", role=UserRole.MEMBER),
        Group(id=1, name="Lab Group", description="Test group", leader_user_id=2),
        GroupMember(id=1, group_id=1, user_id=2, group_role="leader"),
        AuditLog(id=1, action="login", actor_user_id=1, target_type="user", target_id=1),
    ])
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(groups.router)
    app.include_router(audit.router)
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


# ── Groups ─────────────────────────────────────────────────

def test_list_groups_as_admin(client):
    c, _, uid = client; uid["value"] = 1
    r = c.get("/groups")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_list_groups_as_member_forbidden(client):
    c, _, uid = client; uid["value"] = 2
    r = c.get("/groups")
    assert r.status_code == 403


def test_create_group_as_admin(client):
    c, _, uid = client; uid["value"] = 1
    r = c.post("/groups", json={"name": "New Group", "description": "desc"})
    assert r.status_code == 200
    assert r.json()["name"] == "New Group"


def test_get_group_members(client):
    c, _, uid = client; uid["value"] = 1
    r = c.get("/groups/1/members")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["group_role"] == "leader"


def test_add_group_member(client):
    c, _, uid = client; uid["value"] = 1
    r = c.post("/groups/1/members", json={"user_id": 1, "group_role": "member"})
    assert r.status_code == 200
    r2 = c.get("/groups/1/members")
    assert len(r2.json()) == 2


# ── Audit Logs ─────────────────────────────────────────────

def test_list_audit_logs_as_admin(client):
    c, _, uid = client; uid["value"] = 1
    r = c.get("/audit-logs")
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_list_audit_logs_as_member_forbidden(client):
    c, _, uid = client; uid["value"] = 2
    r = c.get("/audit-logs")
    assert r.status_code == 403


def test_filter_audit_logs_by_action(client):
    c, _, uid = client; uid["value"] = 1
    r = c.get("/audit-logs?action=login")
    assert r.status_code == 200
    assert all(log["action"] == "login" for log in r.json())
