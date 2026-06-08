import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import notes
from app.api.deps import get_current_user
from app.core.database import Base, get_db
from app.models import *  # noqa: F403
from app.models.knowledge_graph import KnowledgeEntity, KnowledgeExtractionRun, KnowledgeRelation
from app.models.project import Project
from app.models.user import User, UserRole


@pytest.fixture()
def test_app():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    db.add_all(
        [
            User(id=1, username="admin", password_hash="x", display_name="Admin", role=UserRole.SUPER_ADMIN),
            Project(id=1, name="Project A", owner_user_id=1),
        ]
    )
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(notes.router)

    def override_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    def override_user():
        session = SessionLocal()
        try:
            return session.get(User, 1)
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    return TestClient(app), SessionLocal


def test_approved_note_extracts_knowledge_graph(test_app):
    client, SessionLocal = test_app

    response = client.post(
        "/projects/1/notes",
        json={
            "title": "PCR test",
            "experiment_type": "PCR",
            "fixed_fields_json": {"reagents": "PBS、Taq polymerase", "instrument": "PCR仪"},
            "content_json": {"text": "样本: DNA sample A\n结果: 条带清晰"},
        },
    )

    assert response.status_code == 200
    note_id = response.json()["id"]
    with SessionLocal() as db:
        assert db.query(KnowledgeEntity).count() == 0
        assert db.query(KnowledgeExtractionRun).count() == 0

    assert client.post(f"/notes/{note_id}/submit").status_code == 200
    assert client.post(f"/notes/{note_id}/approve", json={"comment": "ok"}).status_code == 200

    with SessionLocal() as db:
        labels = {entity.label for entity in db.query(KnowledgeEntity).all()}
        relation_types = {relation.relation_type for relation in db.query(KnowledgeRelation).all()}
        run = db.query(KnowledgeExtractionRun).filter(KnowledgeExtractionRun.note_id == note_id).one()
        assert {"Project A", "PCR test", "Admin", "PCR", "PBS", "Taq polymerase", "PCR仪", "DNA sample A", "条带清晰"}.issubset(labels)
        assert {"has_note", "created_by", "has_experiment_type", "uses_reagent", "uses_instrument", "uses_sample", "produces_result"}.issubset(relation_types)
        assert run.extracted_entities >= 8


def test_draft_update_is_extracted_only_after_approval(test_app):
    client, SessionLocal = test_app

    create_response = client.post(
        "/projects/1/notes",
        json={
            "title": "Buffer test",
            "experiment_type": "Assay",
            "fixed_fields_json": {"reagents": "PBS"},
            "content_json": {"text": "结果: 初始结果"},
        },
    )
    note_id = create_response.json()["id"]

    update_response = client.patch(
        f"/notes/{note_id}",
        json={
            "fixed_fields_json": {"reagents": "Tris buffer"},
            "content_json": {"text": "结果: 更新结果"},
            "change_summary": "Change reagent",
        },
    )

    assert update_response.status_code == 200
    with SessionLocal() as db:
        assert db.query(KnowledgeEntity).count() == 0
        assert db.query(KnowledgeExtractionRun).count() == 0

    assert client.post(f"/notes/{note_id}/submit").status_code == 200
    assert client.post(f"/notes/{note_id}/approve", json={"comment": "ok"}).status_code == 200

    with SessionLocal() as db:
        labels = {entity.label for entity in db.query(KnowledgeEntity).all()}
        relation_targets = {
            db.get(KnowledgeEntity, relation.target_entity_id).label
            for relation in db.query(KnowledgeRelation).filter(KnowledgeRelation.relation_type.in_(("uses_reagent", "produces_result"))).all()
        }
        assert "Tris buffer" in labels
        assert "更新结果" in labels
        assert "PBS" not in labels
        assert "初始结果" not in labels
        assert "Tris buffer" in relation_targets
        assert "更新结果" in relation_targets
        assert db.query(KnowledgeExtractionRun).filter(KnowledgeExtractionRun.note_id == note_id).count() == 1
