from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import knowledge_graph
from app.api.deps import get_current_user
from app.core.database import Base, get_db
from app.models import *  # noqa: F403
from app.models.file import FileCategory, FileStatus, KnowledgeSyncStatus, StoredFile
from app.models.knowledge_graph import KnowledgeEntity, KnowledgeEntityType, KnowledgeRelation
from app.models.note import ExperimentNote, NoteStatus, NoteVersion
from app.models.project import Project, ProjectMember, ProjectRole
from app.models.user import User, UserRole
from app.services.knowledge_graph import KnowledgeGraphService


@pytest.fixture()
def test_app(tmp_path: Path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    upload_path = tmp_path / "protocol.pdf"
    upload_path.write_text("protocol", encoding="utf-8")

    db = SessionLocal()
    db.add_all(
        [
            User(id=1, username="admin", password_hash="x", display_name="Admin", role=UserRole.SUPER_ADMIN),
            User(id=2, username="reader", password_hash="x", display_name="Reader", role=UserRole.MEMBER),
            User(id=3, username="outsider", password_hash="x", display_name="Outsider", role=UserRole.MEMBER),
            Project(id=1, name="Project A", owner_user_id=1),
            ProjectMember(project_id=1, user_id=2, project_role=ProjectRole.VIEWER, can_read=True, can_write=False),
        ]
    )
    db.flush()
    note = ExperimentNote(
        id=1,
        project_id=1,
        title="Cell viability assay",
        experiment_type="Cell assay",
        owner_user_id=1,
        status=NoteStatus.APPROVED,
    )
    db.add(note)
    db.flush()
    version = NoteVersion(
        id=1,
        note_id=1,
        version_number=1,
        fixed_fields_json={
            "reagents": ["PBS", "Trypsin"],
            "instrument": "Centrifuge",
            "sample": "Cell sample A",
            "result": "Cells remained viable",
        },
        content_json={
            "text": "试剂: PBS、Trypsin\n仪器: Centrifuge\n样本: Cell sample A\n结果: Cells remained viable"
        },
        created_by=1,
    )
    db.add(version)
    db.flush()
    note.current_version_id = version.id
    db.add(
        StoredFile(
            id=1,
            project_id=1,
            note_id=1,
            uploaded_by=1,
            file_category=FileCategory.NOTE_ATTACHMENT,
            original_filename="protocol.pdf",
            storage_path=str(upload_path),
            mime_type="application/pdf",
            file_size=8,
            file_hash="hash-1",
            status=FileStatus.APPROVED,
            knowledge_sync_status=KnowledgeSyncStatus.NOT_APPLICABLE.value,
        )
    )
    db.commit()
    db.close()

    active_user_id = {"value": 1}
    app = FastAPI()
    app.include_router(knowledge_graph.router)

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


def test_extract_note_builds_graph(test_app):
    client, _, active_user_id = test_app
    active_user_id["value"] = 1

    response = client.post("/notes/1/kg/extract", json={"rebuild": True})
    assert response.status_code == 200
    run = response.json()
    assert run["status"] == "completed"
    assert run["extracted_entities"] >= 8
    assert run["extracted_relations"] >= 7

    graph_response = client.get("/notes/1/kg/graph")
    assert graph_response.status_code == 200
    graph = graph_response.json()
    labels = {entity["label"] for entity in graph["entities"]}
    relation_types = {relation["relation_type"] for relation in graph["relations"]}

    assert {"Project A", "Cell viability assay", "Admin", "protocol.pdf", "PBS", "Trypsin"}.issubset(labels)
    assert {
        "has_note",
        "created_by",
        "has_attachment",
        "has_experiment_type",
        "uses_reagent",
        "uses_instrument",
        "uses_sample",
        "produces_result",
    }.issubset(relation_types)


def test_project_rebuild_is_idempotent(test_app):
    client, SessionLocal, active_user_id = test_app
    active_user_id["value"] = 1

    assert client.post("/projects/1/kg/rebuild").status_code == 200
    with SessionLocal() as db:
        first_entity_count = db.query(KnowledgeEntity).count()
        first_relation_count = db.query(KnowledgeRelation).count()

    assert client.post("/projects/1/kg/rebuild").status_code == 200
    with SessionLocal() as db:
        assert db.query(KnowledgeEntity).count() == first_entity_count
        assert db.query(KnowledgeRelation).count() == first_relation_count


def test_entity_normalization_unifies_width_case_and_punctuation(test_app):
    _, SessionLocal, _ = test_app
    service = KnowledgeGraphService()

    with SessionLocal() as db:
        legacy = KnowledgeEntity(
            project_id=1,
            entity_type=KnowledgeEntityType.REAGENT.value,
            label="Ｔａｑ-DNA Polymerase",
            normalized_label="ｔａｑ-dna polymerase",
            natural_key="reagent:ｔａｑ-dna polymerase",
            properties={},
        )
        db.add(legacy)
        db.flush()
        second = service._upsert_entity(
            db,
            1,
            KnowledgeEntityType.REAGENT,
            "taq DNA polymerase",
        )

        assert legacy.id == second.id
        assert second.normalized_label == "taq dna polymerase"
        assert second.natural_key == "reagent:taq dna polymerase"
        assert db.query(KnowledgeEntity).filter(KnowledgeEntity.entity_type == "reagent").count() == 1


def test_reader_can_view_graph_but_cannot_extract(test_app):
    client, _, active_user_id = test_app
    active_user_id["value"] = 2

    assert client.get("/projects/1/kg/graph").status_code == 200
    assert client.post("/notes/1/kg/extract", json={"rebuild": True}).status_code == 403


def test_outsider_cannot_view_graph(test_app):
    client, _, active_user_id = test_app
    active_user_id["value"] = 3

    assert client.get("/projects/1/kg/graph").status_code == 403
