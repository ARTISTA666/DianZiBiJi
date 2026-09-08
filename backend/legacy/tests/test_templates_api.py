"""Tests for experiment templates API endpoint (3 test cases)."""

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api import templates
from app.api.deps import get_current_user
from app.core.database import Base, get_db
from app.core.security import hash_password
from app.models import *  # noqa: F403
from app.models.template import ExperimentTemplate
from app.models.user import User, UserRole


@pytest.fixture()
def client(db_engine):
    SessionLocal = sessionmaker(bind=db_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=db_engine)

    db = SessionLocal()
    db.add_all([
        User(id=1, username="admin", password_hash=hash_password("x"), display_name="Admin", role=UserRole.SUPER_ADMIN),
        User(id=2, username="member", password_hash=hash_password("x"), display_name="Member", role=UserRole.MEMBER),
        ExperimentTemplate(id=1, name="PCR", experiment_type="molecular_biology",
                           schema_json={"fields": ["primer", "annealing_temp"]},
                           default_content_json={"steps": 3}, is_active=True),
        ExperimentTemplate(id=2, name="WB", experiment_type="protein_analysis",
                           schema_json={"fields": ["antibody", "exposure_time"]},
                           default_content_json={"steps": 5}, is_active=True),
        ExperimentTemplate(id=3, name="Old Protocol", experiment_type="general",
                           schema_json={}, default_content_json={}, is_active=False),
    ])
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(templates.router)
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


# ── 1. GET /templates returns active templates ─────────────

def test_list_templates_returns_active_only(client):
    c, _, uid = client
    uid["value"] = 1
    r = c.get("/templates")
    assert r.status_code == 200
    body = r.json()
    # Only active templates (PCR, WB); inactive "Old Protocol" excluded
    assert len(body) == 2
    names = {t["name"] for t in body}
    assert names == {"PCR", "WB"}


# ── 2. Seed data contains expected templates ───────────────

def test_seed_templates_have_expected_fields(client):
    c, _, uid = client
    uid["value"] = 1
    r = c.get("/templates")
    body = r.json()
    pcr = next(t for t in body if t["name"] == "PCR")
    assert pcr["experiment_type"] == "molecular_biology"
    assert "primer" in pcr["schema_json"]["fields"]

    wb = next(t for t in body if t["name"] == "WB")
    assert wb["experiment_type"] == "protein_analysis"
    assert "antibody" in wb["schema_json"]["fields"]


# ── 3. Auth: any authenticated user ok, unauthenticated 401 ─

def test_authenticated_user_can_access(client):
    c, _, uid = client
    uid["value"] = 2  # member
    r = c.get("/templates")
    assert r.status_code == 200


def test_unauthenticated_gets_401(client):
    c, _, uid = client
    uid["value"] = None
    r = c.get("/templates")
    assert r.status_code == 401
