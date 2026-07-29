"""Dataset lifecycle endpoints: init, status and per-file indexing."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_project_access
from app.api.rag.common import _build_status, _get_project_dataset, _require_rag_manager
from app.core.config import get_settings
from app.core.database import get_db
from app.models.file import FileCategory, FileStatus, KnowledgeSyncStatus, StoredFile
from app.models.rag import ProjectRagDataset, RagFileSync, RagSyncStatus
from app.models.user import User
from app.schemas.rag import RagStatusRead
from app.services.audit import write_audit
from app.services.embedding import EmbeddingServiceError
from app.services.local_rag import LocalRagService

router = APIRouter(tags=["rag"])


@router.post("/projects/{project_id}/rag/init", response_model=RagStatusRead)
async def init_project_rag(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RagStatusRead:
    settings = get_settings()
    project = require_project_access(project_id, db, user)
    _require_rag_manager(db, user, project_id)
    existing = _get_project_dataset(db, project_id)
    if existing is None:
        db.add(
            ProjectRagDataset(
                project_id=project_id,
                dify_dataset_id=f"local-project-{project_id}",
                dify_dataset_name=f"ELN Project {project.id} - {project.name}",
                provider="local_deepseek",
                embedding_model=settings.embedding_model,
                generation_model=settings.normalized_deepseek_model,
                created_by=user.id,
            )
        )
    else:
        existing.provider = "local_deepseek"
        existing.embedding_model = settings.embedding_model
        existing.generation_model = settings.normalized_deepseek_model
    write_audit(
        db,
        actor=user,
        action="init_local_rag",
        project_id=project_id,
        target_type="project",
        target_id=project_id,
        detail={
            "embedding_model": settings.embedding_model,
            "generation_model": settings.normalized_deepseek_model,
        },
    )
    db.commit()
    return _build_status(project_id, db)


@router.get("/projects/{project_id}/rag/status", response_model=RagStatusRead)
def get_project_rag_status(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RagStatusRead:
    require_project_access(project_id, db, user)
    return _build_status(project_id, db)


@router.post("/files/{file_id}/rag/sync", response_model=RagStatusRead)
async def sync_file_to_rag(
    file_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RagStatusRead:
    record = db.get(StoredFile, file_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    require_project_access(record.project_id, db, user)
    _require_rag_manager(db, user, record.project_id)
    if record.file_category != FileCategory.KNOWLEDGE_DOCUMENT:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only knowledge documents can be indexed")
    if record.status != FileStatus.APPROVED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only approved documents can be indexed")
    dataset = _get_project_dataset(db, record.project_id)
    if dataset is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="RAG dataset is not initialized")

    sync = db.query(RagFileSync).filter(RagFileSync.file_id == record.id).first()
    if sync is None:
        sync = RagFileSync(
            file_id=record.id,
            project_id=record.project_id,
            dify_dataset_id=dataset.dify_dataset_id,
        )
        db.add(sync)
        db.flush()
    sync.sync_status = RagSyncStatus.PENDING.value
    sync.sync_message = "Extracting, chunking and embedding document"
    record.knowledge_sync_status = KnowledgeSyncStatus.PENDING_SYNC.value
    record.knowledge_sync_message = sync.sync_message
    db.commit()

    try:
        chunk_count = await LocalRagService().index_file(db, record)
    except (EmbeddingServiceError, FileNotFoundError, ValueError) as exc:
        sync.sync_status = RagSyncStatus.FAILED.value
        sync.sync_message = str(exc)
        record.knowledge_sync_status = KnowledgeSyncStatus.FAILED.value
        record.knowledge_sync_message = str(exc)
        write_audit(
            db,
            actor=user,
            action="index_rag_document_failed",
            project_id=record.project_id,
            target_type="file",
            target_id=record.id,
            detail={"error": str(exc)},
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    now = datetime.now(timezone.utc)
    sync.dify_document_id = f"local-file-{record.id}"
    sync.chunk_count = chunk_count
    sync.content_hash = record.file_hash
    sync.sync_status = RagSyncStatus.SYNCED.value
    sync.sync_message = f"Indexed {chunk_count} chunks with {dataset.embedding_model}"
    sync.synced_at = now
    record.knowledge_sync_status = KnowledgeSyncStatus.SYNCED.value
    record.knowledge_sync_message = sync.sync_message
    record.knowledge_synced_at = now
    write_audit(
        db,
        actor=user,
        action="index_rag_document",
        project_id=record.project_id,
        target_type="file",
        target_id=record.id,
        detail={"chunk_count": chunk_count, "embedding_model": dataset.embedding_model},
    )
    db.commit()
    return _build_status(record.project_id, db)
