"""Tests for notes CRUD + state machine + approval flow (22 test cases)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import notes
from app.api.deps import get_current_user
from app.core.database import Base, get_db
from app.core.security import hash_password
from app.models import *  # noqa: F403
from app.models.note import ExperimentNote, NoteApproval, NoteStatus, NoteVersion
from app.models.project import Project, ProjectMember, ProjectRole
from app.models.user import User, UserRole


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    db.add_all([
        User(id=1, username="admin", password_hash=hash_password("x"), display_name="Admin", role=UserRole.SUPER_ADMIN),
        User(id=2, username="writer", password_hash=hash_password("x"), display_name="Writer", role=UserRole.MEMBER),
        User(id=3, username="reviewer", password_hash=hash_password("x"), display_name="Reviewer", role=UserRole.MEMBER),
        User(id=4, username="outsider", password_hash=hash_password("x"), display_name="Outsider", role=UserRole.MEMBER),
        # Project with approval enabled
        Project(id=1, name="Approval Project", owner_user_id=1, approval_enabled=True),
        ProjectMember(project_id=1, user_id=2, project_role=ProjectRole.MEMBER, can_read=True, can_write=True),
        ProjectMember(project_id=1, user_id=3, project_role=ProjectRole.REVIEWER, can_read=True, can_write=False, can_review=True),
        # Project without approval
        Project(id=2, name="No-Approval Project", owner_user_id=1, approval_enabled=False),
        ProjectMember(project_id=2, user_id=2, project_role=ProjectRole.MEMBER, can_read=True, can_write=True),
    ])
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(notes.router)
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


# ── Note CRUD ──────────────────────────────────────────────

def test_create_note_as_writer(client):
    c, _, uid = client; uid["value"] = 2
    r = c.post("/projects/1/notes", json={
        "title": "PCR Test", "experiment_type": "PCR",
        "fixed_fields_json": {"reagent": "Taq"}, "content_json": {"text": "Test content."},
    })
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "PCR Test"
    assert body["status"] == "draft"
    assert body["owner_user_id"] == 2


def test_create_note_forbidden_no_write(client):
    c, _, uid = client; uid["value"] = 3  # reviewer, no write
    r = c.post("/projects/1/notes", json={"title": "X", "experiment_type": "PCR"})
    assert r.status_code == 403


def test_create_note_outside_project(client):
    c, _, uid = client; uid["value"] = 4  # outsider
    r = c.post("/projects/1/notes", json={"title": "X", "experiment_type": "PCR"})
    assert r.status_code == 403


def test_list_notes_in_project(client):
    # First create a note, then list
    c, _, uid = client; uid["value"] = 2
    c.post("/projects/1/notes", json={"title": "N1", "experiment_type": "PCR"})
    r = c.get("/projects/1/notes")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_get_note_by_id(client):
    c, _, uid = client; uid["value"] = 2
    created = c.post("/projects/1/notes", json={"title": "N1", "experiment_type": "PCR"})
    note_id = created.json()["id"]
    r = c.get(f"/notes/{note_id}")
    assert r.status_code == 200
    assert r.json()["title"] == "N1"


def test_get_note_forbidden(client):
    c, _, uid = client; uid["value"] = 2
    created = c.post("/projects/1/notes", json={"title": "N1", "experiment_type": "PCR"})
    note_id = created.json()["id"]
    uid["value"] = 4  # outsider
    r = c.get(f"/notes/{note_id}")
    assert r.status_code == 403


def test_update_note_draft(client):
    c, _, uid = client; uid["value"] = 2
    created = c.post("/projects/1/notes", json={"title": "N1", "experiment_type": "PCR"})
    note_id = created.json()["id"]
    r = c.patch(f"/notes/{note_id}", json={"title": "Updated Title", "change_summary": "updated draft"})
    assert r.status_code == 200
    assert r.json()["title"] == "Updated Title"


def test_cannot_update_approved_note(client):
    c, S, uid = client; uid["value"] = 2
    # Create + submit in no-approval project → auto approved
    created = c.post("/projects/2/notes", json={"title": "Auto Approved", "experiment_type": "PCR"})
    note_id = created.json()["id"]
    c.post(f"/notes/{note_id}/submit")
    r2 = c.patch(f"/notes/{note_id}", json={"title": "Edit attempt"})
    assert r2.status_code == 409


# ── Note State Machine ─────────────────────────────────────

def test_submit_draft_for_approval(client):
    c, _, uid = client; uid["value"] = 2
    created = c.post("/projects/1/notes", json={"title": "Draft", "experiment_type": "PCR"})
    note_id = created.json()["id"]
    r = c.post(f"/notes/{note_id}/submit")
    assert r.status_code == 200
    assert r.json()["status"] == "submitted"


def test_submit_note_not_owner(client):
    c, _, uid = client; uid["value"] = 2
    created = c.post("/projects/1/notes", json={"title": "Owner's Note", "experiment_type": "PCR"})
    note_id = created.json()["id"]
    uid["value"] = 1  # admin but not owner
    r = c.post(f"/notes/{note_id}/submit")
    assert r.status_code == 403


def test_approve_submitted_note(client):
    c, _, uid = client; uid["value"] = 2
    created = c.post("/projects/1/notes", json={"title": "For Approval", "experiment_type": "PCR"})
    note_id = created.json()["id"]
    c.post(f"/notes/{note_id}/submit")
    # Now approve as reviewer
    uid["value"] = 3  # reviewer
    r = c.post(f"/notes/{note_id}/approve", json={"comment": "Looks good"})
    assert r.status_code == 200
    assert r.json()["status"] == "approved"


def test_cannot_approve_non_submitted(client):
    c, _, uid = client; uid["value"] = 3
    created = client[0].post("/projects/1/notes", json={"title": "X", "experiment_type": "PCR"})  # logged in as admin
    # Actually, need to use check: create as writer first, then try to approve as reviewer without submitting
    uid["value"] = 2
    created = c.post("/projects/1/notes", json={"title": "Draft Only", "experiment_type": "PCR"})
    note_id = created.json()["id"]
    uid["value"] = 3
    r = c.post(f"/notes/{note_id}/approve", json={"comment": "X"})
    assert r.status_code == 409  # Only submitted notes can be approved


def test_return_note_to_draft(client):
    c, _, uid = client; uid["value"] = 2
    created = c.post("/projects/1/notes", json={"title": "Return Me", "experiment_type": "PCR"})
    note_id = created.json()["id"]
    c.post(f"/notes/{note_id}/submit")
    uid["value"] = 3
    r = c.post(f"/notes/{note_id}/return", json={"comment": "Needs revision"})
    assert r.status_code == 200
    assert r.json()["status"] == "returned"


def test_archive_note(client):
    c, _, uid = client; uid["value"] = 2
    # Create in no-approval project → auto approved
    created = c.post("/projects/2/notes", json={"title": "To Archive", "experiment_type": "PCR"})
    note_id = created.json()["id"]
    r = c.post(f"/notes/{note_id}/archive")
    assert r.status_code == 200
    assert r.json()["status"] == "archived"


def test_void_note(client):
    c, _, uid = client; uid["value"] = 2
    created = c.post("/projects/2/notes", json={"title": "To Void", "experiment_type": "PCR"})
    note_id = created.json()["id"]
    c.post(f"/notes/{note_id}/submit")  # auto-approved
    uid["value"] = 1  # super_admin has review permission
    r = c.post(f"/notes/{note_id}/void", json={"comment": "Invalid data"})
    assert r.status_code == 200
    assert r.json()["status"] == "voided"


def test_void_note_requires_review(client):
    c, _, uid = client; uid["value"] = 2
    created = c.post("/projects/1/notes", json={"title": "Void attempt", "experiment_type": "PCR"})
    note_id = created.json()["id"]
    r = c.post(f"/notes/{note_id}/void", json={"comment": "X"})
    assert r.status_code == 403  # writer is not reviewer


def test_no_approval_project_auto_approves(client):
    c, _, uid = client; uid["value"] = 2
    created = c.post("/projects/2/notes", json={"title": "Auto", "experiment_type": "PCR"})
    note_id = created.json()["id"]
    r = c.post(f"/notes/{note_id}/submit")
    assert r.status_code == 200
    assert r.json()["status"] == "approved"


# ── Versions & Approvals ───────────────────────────────────

def test_note_versions_are_tracked(client):
    c, _, uid = client; uid["value"] = 2
    created = c.post("/projects/1/notes", json={"title": "V1", "experiment_type": "PCR"})
    note_id = created.json()["id"]
    c.patch(f"/notes/{note_id}", json={"title": "V2", "change_summary": "second edit"})
    r = c.get(f"/notes/{note_id}/versions")
    assert r.status_code == 200
    versions = r.json()
    assert len(versions) == 2
    assert versions[0]["version_number"] == 2


def test_note_approvals_are_recorded(client):
    c, _, uid = client; uid["value"] = 2
    created = c.post("/projects/1/notes", json={"title": "Approval Test", "experiment_type": "PCR"})
    note_id = created.json()["id"]
    c.post(f"/notes/{note_id}/submit")
    uid["value"] = 3
    c.post(f"/notes/{note_id}/approve", json={"comment": "Approved"})
    r = c.get(f"/notes/{note_id}/approvals")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["action"] == "approved"


def test_pending_approvals_list(client):
    c, _, uid = client; uid["value"] = 2
    created = c.post("/projects/1/notes", json={"title": "Pending", "experiment_type": "PCR"})
    note_id = created.json()["id"]
    c.post(f"/notes/{note_id}/submit")
    uid["value"] = 3
    r = c.get("/approvals/pending")
    assert r.status_code == 200
    ids = {n["id"] for n in r.json()}
    assert note_id in ids
