from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api import ocr
from app.api.deps import get_current_user
from app.core.database import Base, get_db
from app.models import *  # noqa: F403
from app.models.audit import AuditLog
from app.models.file import StoredFile
from app.models.ocr import FileOcrResult, OcrReviewStatus
from app.models.project import Project, ProjectMember, ProjectRole
from app.models.user import User, UserRole
from app.services.ocr import OcrService


@pytest.fixture()
def test_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_engine):
    SessionLocal = sessionmaker(bind=db_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=db_engine)
    image_path = tmp_path / "note.png"
    image_path.write_bytes(b"image")

    with SessionLocal() as db:
        db.add_all(
            [
                User(id=1, username="admin", password_hash="x", display_name="Admin", role=UserRole.SUPER_ADMIN),
                User(id=2, username="outsider", password_hash="x", display_name="Outsider", role=UserRole.MEMBER),
                User(id=3, username="viewer", password_hash="x", display_name="Viewer", role=UserRole.MEMBER),
                Project(id=1, name="OCR Project", owner_user_id=1),
                ProjectMember(
                    project_id=1,
                    user_id=3,
                    project_role=ProjectRole.VIEWER,
                    can_read=True,
                ),
                StoredFile(
                    id=1,
                    project_id=1,
                    uploaded_by=1,
                    original_filename="note.png",
                    storage_path=str(image_path),
                    file_size=5,
                    file_hash="ocr-test",
                ),
            ]
        )
        db.commit()

    monkeypatch.setattr(
        OcrService,
        "extract",
        lambda _self, _db, file_id: {
            "file_id": file_id,
            "extracted_text": "实验温度 58 C",
            "source_ids": [str(file_id)],
            "character_count": 10,
            "truncated": False,
            "extraction_method": "tesseract:chi_sim+eng",
        },
    )
    active_user_id = {"value": 1}
    app = FastAPI()
    app.include_router(ocr.router)

    def override_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    def override_user():
        with SessionLocal() as session:
            return session.get(User, active_user_id["value"])

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    return TestClient(app), SessionLocal, active_user_id


def test_image_ocr_response_and_audit_are_saved(test_app):
    client, SessionLocal, _ = test_app
    response = client.post("/api/ocr/extract", json={"file_id": 1})

    assert response.status_code == 200
    assert response.json()["extraction_method"] == "tesseract:chi_sim+eng"
    assert response.json()["extracted_text"] == "实验温度 58 C"
    assert response.json()["raw_text"] == "实验温度 58 C"
    assert response.json()["review_status"] == "pending_review"
    with SessionLocal() as db:
        audit = db.query(AuditLog).filter(AuditLog.action == "extract_file_text").one()
        assert audit.target_id == 1
        assert audit.detail_json["character_count"] == 10
        saved = db.query(FileOcrResult).one()
        assert saved.review_status == OcrReviewStatus.PENDING_REVIEW.value


def test_reviewer_corrects_and_confirms_latest_ocr_result(test_app):
    client, SessionLocal, _ = test_app
    extracted = client.post("/api/ocr/extract", json={"file_id": 1}).json()

    response = client.post(
        f"/api/ocr/results/{extracted['ocr_result_id']}/confirm",
        json={"corrected_text": "实验温度 58 °C"},
    )

    assert response.status_code == 200
    assert response.json()["raw_text"] == "实验温度 58 C"
    assert response.json()["extracted_text"] == "实验温度 58 °C"
    assert response.json()["review_status"] == "confirmed"
    assert response.json()["reviewed_by"] == 1
    latest = client.get("/api/ocr/files/1/latest")
    assert latest.status_code == 200
    assert latest.json()["ocr_result_id"] == extracted["ocr_result_id"]
    assert client.post(
        f"/api/ocr/results/{extracted['ocr_result_id']}/confirm",
        json={"corrected_text": "再次修改"},
    ).status_code == 409
    with SessionLocal() as db:
        audit = db.query(AuditLog).filter(AuditLog.action == "confirm_file_ocr").one()
        assert audit.detail_json["corrected_character_count"] == len("实验温度 58 °C")


def test_viewer_cannot_confirm_ocr_result(test_app):
    client, _, active_user_id = test_app
    extracted = client.post("/api/ocr/extract", json={"file_id": 1}).json()
    active_user_id["value"] = 3

    response = client.post(
        f"/api/ocr/results/{extracted['ocr_result_id']}/confirm",
        json={"corrected_text": "实验温度 58 °C"},
    )

    assert response.status_code == 403


def test_outsider_cannot_extract_project_image(test_app):
    client, _, active_user_id = test_app
    active_user_id["value"] = 2

    response = client.post("/api/ocr/extract", json={"file_id": 1})

    assert response.status_code == 403
