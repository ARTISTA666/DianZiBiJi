import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import dashboard, notifications, search
from app.api.deps import get_current_user
from app.core.database import Base, get_db
from app.models import *  # noqa: F403
from app.models.file import StoredFile
from app.models.note import ExperimentNote, NoteStatus
from app.models.notification import Notification
from app.models.project import Project, ProjectMember, ProjectRole
from app.models.search_document import SearchDocument
from app.models.user import User, UserRole


@pytest.fixture()
def test_app(tmp_path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

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
            Notification(project_id=None, title="Global notice", message="visible to everyone"),
            Notification(project_id=1, title="Allowed notice", message="project 1"),
            Notification(project_id=2, title="Forbidden notice", message="project 2"),
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
    app.include_router(notifications.router)
    app.include_router(dashboard.router)

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


def test_notifications_are_project_scoped(test_app):
    client, active_user_id = test_app
    active_user_id["value"] = 2

    response = client.get("/api/notifications")
    assert response.status_code == 200
    titles = {item["title"] for item in response.json()}
    assert {"Global notice", "Allowed notice"}.issubset(titles)
    assert "Forbidden notice" not in titles

    assert client.get("/api/notifications?project_id=2").status_code == 403
    assert client.post("/api/notifications", json={"project_id": 2, "title": "bad"}).status_code == 403
    assert client.post("/api/notifications", json={"title": "global bad"}).status_code == 403


def test_dashboard_summary_is_scoped_for_regular_users(test_app):
    client, active_user_id = test_app
    active_user_id["value"] = 2

    response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["projects"] == 1
    assert body["experiments"] == 1
    assert body["attachments"] == 1
    assert body["users"] == 0

    active_user_id["value"] = 1
    admin_response = client.get("/api/dashboard/summary")
    assert admin_response.status_code == 200
    admin_body = admin_response.json()
    assert admin_body["projects"] == 2
    assert admin_body["experiments"] == 2
    assert admin_body["attachments"] == 2
    assert admin_body["users"] == 3
