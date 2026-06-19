"""Tests for file upload / CRUD / review endpoints (15 test cases)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import files
from app.api.deps import get_current_user
from app.core.database import Base, get_db
from app.core.security import hash_password
from app.models import *  # noqa: F403
from app.models.file import FileCategory, FileStatus, KnowledgeSyncStatus, StoredFile
from app.models.note import ExperimentNote, NoteStatus
from app.models.project import Project, ProjectMember, ProjectRole
from app.models.user import User, UserRole


@pytest.fixture()
def client(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    db.add_all([
        User(id=1, username="admin", password_hash=hash_password("x"), display_name="Admin", role=UserRole.SUPER_ADMIN),
        User(id=2, username="writer", password_hash=hash_password("x"), display_name="Writer", role=UserRole.MEMBER),
        User(id=3, username="reviewer", password_hash=hash_password("x"), display_name="Reviewer", role=UserRole.MEMBER),
        User(id=4, username="outsider", password_hash=hash_password("x"), display_name="Outsider", role=UserRole.MEMBER),
        Project(id=1, name="File Project", owner_user_id=1),
        ProjectMember(project_id=1, user_id=2, project_role=ProjectRole.MEMBER, can_read=True, can_write=True),
        ProjectMember(project_id=1, user_id=3, project_role=ProjectRole.REVIEWER, can_read=True, can_review=True),
        ExperimentNote(id=1, project_id=1, title="Note A", experiment_type="PCR", owner_user_id=2, status=NoteStatus.APPROVED),
    ])
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(files.router)
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

    # Patch STORAGE_ROOT to use tmp_path
    import app.api.files as files_mod
    original = files_mod.STORAGE_ROOT
    files_mod.STORAGE_ROOT = tmp_path
    yield TestClient(app), SessionLocal, active_user_id, tmp_path
    files_mod.STORAGE_ROOT = original


# ── File Upload ────────────────────────────────────────────

def test_upload_file_as_writer(client):
    c, _, uid, tmp = client; uid["value"] = 2
    r = c.post("/projects/1/files?file_category=knowledge_document", files={"upload": ("test.txt", b"hello world", "text/plain")})
    assert r.status_code == 200
    body = r.json()
    assert body["original_filename"] == "test.txt"
    assert body["file_hash"]
    assert body["file_size"] == 11
    assert body["status"] == "uploaded"
    assert body["knowledge_sync_status"] == "pending_review"


def test_upload_file_attached_to_note(client):
    c, _, uid, tmp = client; uid["value"] = 2
    r = c.post("/projects/1/files?file_category=note_attachment&note_id=1", files={"upload": ("attachment.txt", b"note data", "text/plain")})
    assert r.status_code == 200
    assert r.json()["note_id"] == 1
    assert r.json()["knowledge_sync_status"] == "not_applicable"


def test_upload_file_forbidden(client):
    c, _, uid, tmp = client; uid["value"] = 4
    r = c.post("/projects/1/files", files={"upload": ("bad.txt", b"x", "text/plain")})
    assert r.status_code == 403


def test_list_project_files(client):
    c, _, uid, tmp = client; uid["value"] = 2
    c.post("/projects/1/files?file_category=knowledge_document", files={"upload": ("f1.txt", b"aa", "text/plain")})
    c.post("/projects/1/files?file_category=knowledge_document", files={"upload": ("f2.txt", b"bb", "text/plain")})
    r = c.get("/projects/1/files")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_get_file_by_id(client):
    c, _, uid, tmp = client; uid["value"] = 2
    created = c.post("/projects/1/files?file_category=knowledge_document", files={"upload": ("get_me.txt", b"content", "text/plain")})
    file_id = created.json()["id"]
    r = c.get(f"/files/{file_id}")
    assert r.status_code == 200
    assert r.json()["original_filename"] == "get_me.txt"


def test_update_file_name(client):
    c, _, uid, tmp = client; uid["value"] = 2
    created = c.post("/projects/1/files?file_category=knowledge_document", files={"upload": ("old_name.txt", b"data", "text/plain")})
    file_id = created.json()["id"]
    r = c.patch(f"/files/{file_id}", json={"original_filename": "renamed.txt"})
    assert r.status_code == 200
    assert r.json()["original_filename"] == "renamed.txt"


def test_update_file_empty_name(client):
    c, _, uid, tmp = client; uid["value"] = 2
    created = c.post("/projects/1/files?file_category=knowledge_document", files={"upload": ("f.txt", b"x", "text/plain")})
    file_id = created.json()["id"]
    r = c.patch(f"/files/{file_id}", json={"original_filename": "   "})
    assert r.status_code == 422


def test_archive_file(client):
    c, _, uid, tmp = client; uid["value"] = 2
    created = c.post("/projects/1/files?file_category=knowledge_document", files={"upload": ("to_archive.txt", b"x", "text/plain")})
    file_id = created.json()["id"]
    r = c.post(f"/files/{file_id}/archive")
    assert r.status_code == 200
    assert r.json()["status"] == "archived"
    assert r.json()["knowledge_sync_status"] == "not_applicable"


def test_download_file(client):
    c, _, uid, tmp = client; uid["value"] = 2
    created = c.post("/projects/1/files?file_category=knowledge_document", files={"upload": ("download.txt", b"hello download", "text/plain")})
    file_id = created.json()["id"]
    r = c.get(f"/files/{file_id}/download")
    assert r.status_code == 200
    assert r.content == b"hello download"


# ── File Review ────────────────────────────────────────────

def test_review_file_approve(client):
    c, _, uid, tmp = client; uid["value"] = 2
    created = c.post("/projects/1/files?file_category=knowledge_document", files={"upload": ("review.txt", b"data", "text/plain")})
    file_id = created.json()["id"]
    uid["value"] = 3  # reviewer
    r = c.post(f"/files/{file_id}/review", json={"action": "approve", "comment": "Good"})
    assert r.status_code == 200
    assert r.json()["status"] == "approved"
    assert r.json()["knowledge_sync_status"] == "pending_sync"


def test_review_file_reject(client):
    c, _, uid, tmp = client; uid["value"] = 2
    created = c.post("/projects/1/files?file_category=knowledge_document", files={"upload": ("bad.txt", b"bad", "text/plain")})
    file_id = created.json()["id"]
    uid["value"] = 3
    r = c.post(f"/files/{file_id}/review", json={"action": "reject", "comment": "Rejected"})
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"
    assert r.json()["knowledge_sync_status"] == "not_applicable"


def test_review_note_attachment_forbidden(client):
    c, _, uid, tmp = client; uid["value"] = 2
    created = c.post("/projects/1/files?file_category=note_attachment&note_id=1", files={"upload": ("att.txt", b"x", "text/plain")})
    file_id = created.json()["id"]
    uid["value"] = 3
    r = c.post(f"/files/{file_id}/review", json={"action": "approve"})
    assert r.status_code == 409  # Only knowledge documents can be reviewed


def test_review_already_approved_file(client):
    c, _, uid, tmp = client; uid["value"] = 2
    created = c.post("/projects/1/files?file_category=knowledge_document", files={"upload": ("done.txt", b"x", "text/plain")})
    file_id = created.json()["id"]
    uid["value"] = 3
    c.post(f"/files/{file_id}/review", json={"action": "approve"})
    r = c.post(f"/files/{file_id}/review", json={"action": "approve"})
    assert r.status_code == 409  # Already reviewed


def test_review_requires_review_permission(client):
    c, _, uid, tmp = client; uid["value"] = 2
    created = c.post("/projects/1/files?file_category=knowledge_document", files={"upload": ("noreview.txt", b"x", "text/plain")})
    file_id = created.json()["id"]
    r = c.post(f"/files/{file_id}/review", json={"action": "approve"})
    assert r.status_code == 403  # writer not reviewer
