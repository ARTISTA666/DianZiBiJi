import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import can_review_project, can_write_project, get_current_user, require_project_access
from app.core.config import get_settings
from app.core.database import get_db
from app.models.file import FileCategory, FileStatus, KnowledgeSyncStatus, StoredFile
from app.models.note import ExperimentNote
from app.models.rag import RagDocumentChunk, RagFileSync
from app.models.user import User
from app.schemas.file import FileRead, FileReviewRequest, FileUpdate
from app.services.audit import write_audit

router = APIRouter(tags=["files"])

STORAGE_ROOT = get_settings().storage_root


def _store_upload(upload: UploadFile, project_id: int) -> tuple[str, int, str]:
    project_dir = STORAGE_ROOT / "projects" / str(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(upload.filename or "file").suffix
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    target = project_dir / stored_name
    digest = hashlib.sha256()
    size = 0
    max_bytes = get_settings().upload_max_bytes
    try:
        with target.open("wb") as buffer:
            while chunk := upload.file.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds upload limit of {max_bytes} bytes",
                    )
                digest.update(chunk)
                buffer.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return str(target), size, digest.hexdigest()


def _require_file(file_id: int, db: Session, user: User) -> StoredFile:
    record = db.get(StoredFile, file_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    require_project_access(record.project_id, db, user)
    return record


@router.post("/projects/{project_id}/files", response_model=FileRead)
def upload_project_file(
    project_id: int,
    file_category: FileCategory = FileCategory.KNOWLEDGE_DOCUMENT,
    note_id: int | None = None,
    upload: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StoredFile:
    require_project_access(project_id, db, user)
    if not can_write_project(db, user, project_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Write permission required")
    if note_id is not None:
        note = db.get(ExperimentNote, note_id)
        if note is None or note.project_id != project_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    storage_path, file_size, file_hash = _store_upload(upload, project_id)
    try:
        record = StoredFile(
            project_id=project_id,
            note_id=note_id,
            uploaded_by=user.id,
            file_category=file_category,
            original_filename=upload.filename or "file",
            storage_path=storage_path,
            mime_type=upload.content_type,
            file_size=file_size,
            file_hash=file_hash,
            knowledge_sync_status=(
                KnowledgeSyncStatus.PENDING_REVIEW.value
                if file_category == FileCategory.KNOWLEDGE_DOCUMENT
                else KnowledgeSyncStatus.NOT_APPLICABLE.value
            ),
            knowledge_sync_message=(
                "等待资料审核，审核通过后进入知识库同步队列"
                if file_category == FileCategory.KNOWLEDGE_DOCUMENT
                else None
            ),
        )
        db.add(record)
        db.flush()
        write_audit(db, actor=user, action="upload_file", project_id=project_id, target_type="file", target_id=record.id)
        db.commit()
    except Exception:
        db.rollback()
        Path(storage_path).unlink(missing_ok=True)
        raise
    db.refresh(record)
    return record


@router.get("/projects/{project_id}/files", response_model=list[FileRead])
def list_project_files(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[StoredFile]:
    require_project_access(project_id, db, user)
    return db.query(StoredFile).filter(StoredFile.project_id == project_id).order_by(StoredFile.created_at.desc()).all()


@router.post("/projects/{project_id}/documents", response_model=FileRead)
def upload_project_document(
    project_id: int,
    upload: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StoredFile:
    return upload_project_file(
        project_id=project_id,
        file_category=FileCategory.KNOWLEDGE_DOCUMENT,
        note_id=None,
        upload=upload,
        user=user,
        db=db,
    )


@router.get("/projects/{project_id}/documents", response_model=list[FileRead])
def list_project_documents(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[StoredFile]:
    require_project_access(project_id, db, user)
    return (
        db.query(StoredFile)
        .filter(StoredFile.project_id == project_id, StoredFile.file_category == FileCategory.KNOWLEDGE_DOCUMENT)
        .order_by(StoredFile.created_at.desc())
        .all()
    )


@router.get("/notes/{note_id}/files", response_model=list[FileRead])
def list_note_files(note_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[StoredFile]:
    note = db.get(ExperimentNote, note_id)
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    require_project_access(note.project_id, db, user)
    return db.query(StoredFile).filter(StoredFile.note_id == note_id).order_by(StoredFile.created_at.desc()).all()


@router.get("/files/{file_id}", response_model=FileRead)
def get_file(file_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> StoredFile:
    return _require_file(file_id, db, user)


@router.patch("/files/{file_id}", response_model=FileRead)
def update_file(
    file_id: int,
    payload: FileUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StoredFile:
    record = _require_file(file_id, db, user)
    if not can_write_project(db, user, record.project_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Write permission required")
    if payload.original_filename is not None:
        filename = payload.original_filename.strip()
        if not filename:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Filename cannot be empty")
        record.original_filename = filename[:255]
    write_audit(db, actor=user, action="update_file", project_id=record.project_id, target_type="file", target_id=record.id)
    db.commit()
    db.refresh(record)
    return record


@router.post("/files/{file_id}/archive", response_model=FileRead)
def archive_file(file_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> StoredFile:
    record = _require_file(file_id, db, user)
    if not can_write_project(db, user, record.project_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Write permission required")
    record.status = FileStatus.ARCHIVED
    if record.file_category == FileCategory.KNOWLEDGE_DOCUMENT:
        db.query(RagDocumentChunk).filter(RagDocumentChunk.file_id == record.id).delete(synchronize_session=False)
        db.query(RagFileSync).filter(RagFileSync.file_id == record.id).delete(synchronize_session=False)
        record.knowledge_sync_status = KnowledgeSyncStatus.NOT_APPLICABLE.value
        record.knowledge_sync_message = "资料已归档，不再进入知识库同步队列"
        record.knowledge_synced_at = None
    write_audit(db, actor=user, action="archive_file", project_id=record.project_id, target_type="file", target_id=record.id)
    db.commit()
    db.refresh(record)
    return record


@router.post("/files/{file_id}/review", response_model=FileRead)
def review_file(
    file_id: int,
    payload: FileReviewRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StoredFile:
    record = _require_file(file_id, db, user)
    if record.file_category != FileCategory.KNOWLEDGE_DOCUMENT:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only knowledge documents can be reviewed")
    if record.status != FileStatus.UPLOADED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only uploaded documents can be reviewed")
    if not can_review_project(db, user, record.project_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Review permission required")
    if payload.action == "approve":
        record.status = FileStatus.APPROVED
        record.knowledge_sync_status = KnowledgeSyncStatus.PENDING_SYNC.value
        record.knowledge_sync_message = "资料已审核通过，等待后续 RAG/Dify 同步任务处理"
    elif payload.action == "reject":
        record.status = FileStatus.REJECTED
        record.knowledge_sync_status = KnowledgeSyncStatus.NOT_APPLICABLE.value
        record.knowledge_sync_message = payload.comment or "资料审核未通过，不进入知识库"
    else:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported review action")
    write_audit(
        db,
        actor=user,
        action="review_document",
        project_id=record.project_id,
        target_type="file",
        target_id=record.id,
        detail={"review_action": payload.action, "comment": payload.comment},
    )
    db.commit()
    db.refresh(record)
    return record


@router.post("/documents/{file_id}/approve", response_model=FileRead)
def approve_document(file_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> StoredFile:
    return review_file(file_id=file_id, payload=FileReviewRequest(action="approve"), user=user, db=db)


@router.post("/documents/{file_id}/reject", response_model=FileRead)
def reject_document(file_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> StoredFile:
    return review_file(file_id=file_id, payload=FileReviewRequest(action="reject"), user=user, db=db)


@router.get("/files/{file_id}/download")
def download_file(file_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> FileResponse:
    record = _require_file(file_id, db, user)
    path = Path(record.storage_path)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored file missing")
    write_audit(db, actor=user, action="download_file", project_id=record.project_id, target_type="file", target_id=record.id)
    db.commit()
    return FileResponse(path, filename=record.original_filename, media_type=record.mime_type)
