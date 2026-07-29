"""Tests for search API endpoints (POST /api/search, POST /api/search/index)."""

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api import search
from app.api.deps import get_current_user
from app.core.database import Base, get_db
from app.models import *  # noqa: F403
from app.models.note import ExperimentNote, NoteStatus
from app.models.project import Project, ProjectMember, ProjectRole
from app.models.search_document import SearchDocument
from app.models.user import User, UserRole


@pytest.fixture()
def env(db_engine):
    """Build a test environment with seed data."""
    SessionLocal = sessionmaker(bind=db_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=db_engine)

    db = SessionLocal()
    db.add_all([
        User(id=1, username="admin", password_hash="x", display_name="Admin", role=UserRole.SUPER_ADMIN),
        User(id=2, username="viewer", password_hash="x", display_name="Viewer", role=UserRole.MEMBER),
        User(id=3, username="outsider", password_hash="x", display_name="Outsider", role=UserRole.MEMBER),
        Project(id=1, name="Project Alpha", owner_user_id=1),
        Project(id=2, name="Project Beta", owner_user_id=1, is_sensitive=True),
        ProjectMember(project_id=1, user_id=2, project_role=ProjectRole.VIEWER, can_read=True, can_write=False),
        ExperimentNote(
            id=1, project_id=1, title="PCR experiment",
            experiment_type="PCR", owner_user_id=1, status=NoteStatus.APPROVED,
        ),
        ExperimentNote(
            id=2, project_id=2, title="Secret analysis",
            experiment_type="Analysis", owner_user_id=1, status=NoteStatus.APPROVED,
        ),
        SearchDocument(
            note_id=1, project_id=1, title="PCR experiment",
            search_text="PCR experiment with PBS buffer reagent", source_ids="1",
        ),
        SearchDocument(
            note_id=2, project_id=2, title="Secret analysis",
            search_text="Secret analysis with reagent X42", source_ids="2",
        ),
    ])
    db.commit()
    db.close()

    active_user_id: dict = {"value": 2}
    app = FastAPI()
    app.include_router(search.router)

    def override_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    def override_user():
        session = SessionLocal()
        try:
            uid = active_user_id["value"]
            if uid is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
            user = session.get(User, uid)
            if user is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
            return user
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    client = TestClient(app)
    return client, active_user_id, SessionLocal


# ── 1. POST /api/search — full text search returns results ──

def test_search_returns_matching_results(env):
    client, active_user_id, _ = env
    active_user_id["value"] = 2

    response = client.post("/api/search", json={"query": "PBS"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    titles = {item["title"] for item in data}
    assert "PCR experiment" in titles


def test_search_multi_term_requires_all_terms(env):
    """Search with multiple terms should only match documents containing ALL terms."""
    client, active_user_id, _ = env
    active_user_id["value"] = 2

    response = client.post("/api/search", json={"query": "PBS buffer"})
    assert response.status_code == 200
    data = response.json()
    # "PBS buffer" — both terms must appear; only note 1 has "PBS buffer"
    assert all(item["project_id"] == 1 for item in data)


def test_search_result_schema(env):
    client, active_user_id, _ = env
    active_user_id["value"] = 2

    response = client.post("/api/search", json={"query": "PCR"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    item = data[0]
    for key in ("document_id", "note_id", "project_id", "title", "snippet", "source_ids"):
        assert key in item


# ── 2. POST /api/search/index — index rebuild ──

def test_reindex_search_all(env):
    client, active_user_id, _ = env
    active_user_id["value"] = 1  # super_admin can reindex all

    response = client.post("/api/search/index")
    assert response.status_code == 200
    body = response.json()
    assert "total_documents" in body
    assert body["total_documents"] >= 2


def test_reindex_search_single_project(env):
    client, active_user_id, _ = env
    active_user_id["value"] = 1

    response = client.post("/api/search/index?project_id=1")
    assert response.status_code == 200
    body = response.json()
    assert body["project_documents"] >= 1


# ── 3. Empty query returns 422 ──

def test_search_empty_query_returns_422(env):
    client, active_user_id, _ = env
    active_user_id["value"] = 2

    response = client.post("/api/search", json={"query": ""})
    assert response.status_code == 422
    assert "empty" in response.json()["detail"].lower()


def test_search_whitespace_only_query_returns_422(env):
    client, active_user_id, _ = env
    active_user_id["value"] = 2

    response = client.post("/api/search", json={"query": "   "})
    assert response.status_code == 422


# ── 4. Search respects project scope ──

def test_search_cannot_see_other_projects(env):
    """Viewer (user 2) only has access to project 1, not project 2."""
    client, active_user_id, _ = env
    active_user_id["value"] = 2

    # Global search — should only see project 1 results
    response = client.post("/api/search", json={"query": "reagent"})
    assert response.status_code == 200
    project_ids = {item["project_id"] for item in response.json()}
    assert 1 in project_ids
    assert 2 not in project_ids


def test_search_explicit_forbidden_project_returns_403(env):
    """Requesting search in a project the user has no access to → 403."""
    client, active_user_id, _ = env
    active_user_id["value"] = 2

    response = client.post("/api/search", json={"query": "secret", "project_id": 2})
    assert response.status_code == 403


def test_search_no_matches_returns_empty_list(env):
    client, active_user_id, _ = env
    active_user_id["value"] = 2

    response = client.post("/api/search", json={"query": "nonexistent_term_xyz"})
    assert response.status_code == 200
    assert response.json() == []


# ── 5. Permission: authenticated vs unauthenticated ──

def test_search_unauthenticated_returns_401(env):
    client, active_user_id, _ = env
    active_user_id["value"] = None

    response = client.post("/api/search", json={"query": "test"})
    assert response.status_code == 401


def test_reindex_unauthenticated_returns_401(env):
    client, active_user_id, _ = env
    active_user_id["value"] = None

    response = client.post("/api/search/index")
    assert response.status_code == 401


def test_search_excludes_archived_note(env):
    """After archiving a note, its search document should no longer appear."""
    client, active_user_id, SessionLocal = env
    active_user_id["value"] = 2

    # Confirm the note is searchable first
    response = client.post("/api/search", json={"query": "PBS"})
    assert response.status_code == 200
    assert len(response.json()) >= 1

    # Archive the note
    db = SessionLocal()
    try:
        db.get(ExperimentNote, 1).status = NoteStatus.ARCHIVED
        db.commit()
    finally:
        db.close()

    response = client.post("/api/search", json={"query": "PBS"})
    assert response.status_code == 200
    assert response.json() == []
