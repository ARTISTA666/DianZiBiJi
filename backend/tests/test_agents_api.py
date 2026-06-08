from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import agents
from app.api.deps import get_current_user
from app.core.database import Base, get_db
from app.models import *  # noqa: F403
from app.models.ai import AgentGenerationRun
from app.models.file import FileCategory, FileStatus, KnowledgeSyncStatus, StoredFile
from app.models.knowledge_graph import KnowledgeEntity, KnowledgeRelation
from app.models.note import ExperimentNote, NoteStatus, NoteVersion
from app.models.project import Project, ProjectMember, ProjectRole
from app.models.user import User, UserRole


@pytest.fixture()
def test_app(tmp_path: Path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    upload_path = tmp_path / "paper.pdf"
    upload_path.write_text("paper", encoding="utf-8")

    db = SessionLocal()
    db.add_all(
        [
            User(id=1, username="admin", password_hash="x", display_name="Admin", role=UserRole.SUPER_ADMIN),
            User(id=2, username="outsider", password_hash="x", display_name="Outsider", role=UserRole.MEMBER),
            User(id=3, username="reader", password_hash="x", display_name="Reader", role=UserRole.MEMBER),
            Project(id=1, name="Project A", owner_user_id=1),
            Project(id=2, name="Project B", owner_user_id=1),
            ProjectMember(project_id=1, user_id=3, project_role=ProjectRole.VIEWER, can_read=True, can_write=False),
        ]
    )
    db.flush()
    note = ExperimentNote(
        id=1,
        project_id=1,
        title="Cell viability assay",
        experiment_type="Cell assay",
        experiment_date=date(2026, 6, 5),
        owner_user_id=1,
        status=NoteStatus.APPROVED,
    )
    draft_note = ExperimentNote(
        id=2,
        project_id=1,
        title="Draft note",
        experiment_type="PCR",
        experiment_date=date(2026, 6, 5),
        owner_user_id=1,
        status=NoteStatus.DRAFT,
    )
    db.add_all([note, draft_note])
    db.flush()
    version = NoteVersion(
        id=1,
        note_id=1,
        version_number=1,
        fixed_fields_json={"reagents": "PBS", "result": "Cells remained viable"},
        content_json={"text": "结果: Cells remained viable"},
        created_by=1,
        is_locked=True,
    )
    db.add(version)
    db.flush()
    note.current_version_id = version.id
    db.add(
        StoredFile(
            id=1,
            project_id=1,
            uploaded_by=1,
            file_category=FileCategory.KNOWLEDGE_DOCUMENT,
            original_filename="paper.pdf",
            storage_path=str(upload_path),
            file_size=5,
            file_hash="hash-1",
            status=FileStatus.APPROVED,
            knowledge_sync_status=KnowledgeSyncStatus.SYNCED.value,
        )
    )
    note_entity = KnowledgeEntity(
        id=1,
        project_id=1,
        entity_type="note",
        label="Cell viability assay",
        normalized_label="cell viability assay",
        natural_key="note:note:1",
        source_type="note",
        source_id=1,
    )
    result_entity = KnowledgeEntity(
        id=2,
        project_id=1,
        entity_type="result",
        label="Cells remained viable",
        normalized_label="cells remained viable",
        natural_key="result:cells remained viable",
    )
    db.add_all([note_entity, result_entity])
    db.flush()
    db.add(
        KnowledgeRelation(
            id=1,
            project_id=1,
            source_entity_id=1,
            target_entity_id=2,
            relation_type="produces_result",
            source_type="note_extraction",
            source_id=1,
            confidence=0.7,
        )
    )
    db.commit()
    db.close()

    active_user_id = {"value": 1}
    app = FastAPI()
    app.include_router(agents.router)

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
    return TestClient(app), SessionLocal, active_user_id


def test_agent_generation_uses_approved_notes_and_records_run(test_app):
    client, SessionLocal, active_user_id = test_app
    active_user_id["value"] = 1

    response = client.post(
        "/api/agents/generate",
        json={"project_id": 1, "task_type": "experiment_summary", "date_from": "2026-06-01", "date_to": "2026-06-06"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["task_type"] == "experiment_summary"
    assert body["source_note_ids_json"] == [1]
    assert body["source_file_ids_json"] == [1]
    assert body["source_graph_relation_ids_json"] == [1]
    assert "Cell viability assay" in body["body"]
    assert "Draft note" not in body["body"]

    with SessionLocal() as db:
        run = db.get(AgentGenerationRun, body["id"])
        assert run is not None
        assert run.status == "completed"

    history_response = client.get("/projects/1/agents/runs")
    assert history_response.status_code == 200
    assert history_response.json()[0]["id"] == body["id"]


def test_agent_generation_records_empty_range(test_app):
    client, _, active_user_id = test_app
    active_user_id["value"] = 1

    response = client.post(
        "/api/agents/generate",
        json={"project_id": 1, "task_type": "weekly_report", "date_from": "2026-05-01", "date_to": "2026-05-02"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source_note_ids_json"] == []
    assert body["message"] == "No approved notes in selected range"
    assert "暂无已审核实验笔记" in body["body"]


def test_outsider_cannot_generate_or_view_agent_runs(test_app):
    client, _, active_user_id = test_app
    active_user_id["value"] = 2

    assert client.post("/api/agents/generate", json={"project_id": 1, "task_type": "experiment_summary"}).status_code == 403
    assert client.get("/projects/1/agents/runs").status_code == 403


def test_reader_can_view_but_cannot_generate_agent_runs(test_app):
    client, _, active_user_id = test_app
    active_user_id["value"] = 3

    assert client.get("/projects/1/agents/runs").status_code == 200
    assert client.post("/api/agents/generate", json={"project_id": 1, "task_type": "experiment_summary"}).status_code == 403
