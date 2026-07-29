import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api import search
from app.api.deps import get_current_user
from app.core.database import Base, get_db
from app.models import *  # noqa: F403
from app.models.file import StoredFile
from app.models.note import ExperimentNote, NoteStatus
from app.models.project import Project, ProjectMember, ProjectRole
from app.models.search_document import SearchDocument
from app.models.user import User, UserRole


@pytest.fixture()
def test_app(tmp_path, db_engine):
    SessionLocal = sessionmaker(bind=db_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=db_engine)

    upload_path = tmp_path / "demo.txt"
    upload_path.write_text("demo", encoding="utf-8")

    db = SessionLocal()
    db.add_all(
        [
            User(id=1, username="admin", password_hash="x", display_name="Admin", role=UserRole.SUPER_ADMIN),
            User(id=2, username="member", password_hash="x", display_name="Member", role=UserRole.MEMBER),
            User(id=3, username="outsider", password_hash="x", display_name="Outsider", role=UserRole.MEMBER),
            Project(id=1, name="Allowed Project", owner_user_id=1),
            Project(id=2, name="Forbidden Project", owner_user_id=1, is_sensitive=True),
            ProjectMember(project_id=1, user_id=2, project_role=ProjectRole.VIEWER, can_read=True, can_write=False),
            ExperimentNote(id=1, project_id=1, title="Allowed note", experiment_type="PCR", owner_user_id=1, status=NoteStatus.APPROVED),
            ExperimentNote(id=2, project_id=2, title="Forbidden secret note", experiment_type="Secret", owner_user_id=1, status=NoteStatus.APPROVED),
            SearchDocument(note_id=1, project_id=1, title="Allowed note", search_text="allowed reagent PBS", source_ids="1"),
            SearchDocument(note_id=2, project_id=2, title="Forbidden secret note", search_text="secret reagent X42", source_ids="2"),
            StoredFile(
                project_id=1,
                uploaded_by=1,
                original_filename="allowed.txt",
                storage_path=str(upload_path),
                file_size=4,
                file_hash="hash-1",
            ),
            StoredFile(
                project_id=2,
                uploaded_by=1,
                original_filename="forbidden.txt",
                storage_path=str(upload_path),
                file_size=4,
                file_hash="hash-2",
            ),
        ]
    )
    db.commit()
    db.close()

    active_user_id = {"value": 2}
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
            return session.get(User, active_user_id["value"])
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    return TestClient(app), active_user_id


def test_global_search_is_limited_to_accessible_projects(test_app):
    client, active_user_id = test_app
    active_user_id["value"] = 2

    allowed_response = client.post("/api/search", json={"query": "reagent"})
    assert allowed_response.status_code == 200
    titles = {item["title"] for item in allowed_response.json()}
    assert "Allowed note" in titles
    assert "Forbidden secret note" not in titles

    forbidden_response = client.post("/api/search", json={"query": "secret"})
    assert forbidden_response.status_code == 200
    assert forbidden_response.json() == []

    assert client.post("/api/search", json={"query": "secret", "project_id": 2}).status_code == 403


def test_search_excludes_stale_index_for_archived_note(test_app):
    client, active_user_id = test_app
    active_user_id["value"] = 2

    assert client.post("/api/search", json={"query": "PBS"}).json()

    from app.core.database import get_db as dependency

    override = client.app.dependency_overrides[dependency]
    db = next(override())
    try:
        db.get(ExperimentNote, 1).status = NoteStatus.ARCHIVED
        db.commit()
    finally:
        db.close()

    assert client.post("/api/search", json={"query": "PBS"}).json() == []
