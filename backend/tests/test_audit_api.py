"""Tests for audit log API endpoint (3 test cases)."""

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api import audit
from app.api.deps import get_current_user
from app.core.database import Base, get_db
from app.core.security import hash_password
from app.models import *  # noqa: F403
from app.models.audit import AuditLog
from app.models.user import User, UserRole


@pytest.fixture()
def client(db_engine):
    SessionLocal = sessionmaker(bind=db_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=db_engine)

    db = SessionLocal()
    db.add_all([
        User(id=1, username="admin", password_hash=hash_password("x"), display_name="Admin", role=UserRole.SUPER_ADMIN),
        User(id=2, username="member", password_hash=hash_password("x"), display_name="Member", role=UserRole.MEMBER),
        AuditLog(id=1, action="login", actor_user_id=1, target_type="user", target_id=1),
        AuditLog(id=2, action="create_project", actor_user_id=1, project_id=1, target_type="project", target_id=1),
        AuditLog(id=3, action="login", actor_user_id=2, target_type="user", target_id=2),
        AuditLog(id=4, action="update_experiment", actor_user_id=2, project_id=1, target_type="experiment", target_id=5),
    ])
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(audit.router)
    active_user_id: dict[int | None] = {"value": 1}

    def override_db():
        s = SessionLocal()
        try:
            yield s
        finally:
            s.close()

    def override_user():
        s = SessionLocal()
        try:
            uid = active_user_id["value"]
            if uid is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
            return s.get(User, int(uid))
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    return TestClient(app), SessionLocal, active_user_id


# ── 1. GET /audit-logs returns entries ─────────────────────

def test_list_audit_logs_as_admin(client):
    c, _, uid = client
    uid["value"] = 1
    r = c.get("/audit-logs")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 4


# ── 2. Filter by actor / project / action ──────────────────

def test_filter_by_actor_and_action(client):
    c, _, uid = client
    uid["value"] = 1
    r = c.get("/audit-logs?actor_user_id=2&action=login")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["id"] == 3

    r2 = c.get("/audit-logs?project_id=1")
    assert r2.status_code == 200
    body2 = r2.json()
    assert len(body2) == 2
    assert all(log["project_id"] == 1 for log in body2)


# ── 3. Permission: admin ok, non-admin 403 ─────────────────

def test_admin_can_access(client):
    c, _, uid = client
    uid["value"] = 1
    r = c.get("/audit-logs")
    assert r.status_code == 200


def test_non_admin_gets_403(client):
    c, _, uid = client
    uid["value"] = 2
    r = c.get("/audit-logs")
    assert r.status_code == 403
