from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FileCategory(StrEnum):
    NOTE_ATTACHMENT = "note_attachment"
    KNOWLEDGE_DOCUMENT = "knowledge_document"


class FileStatus(StrEnum):
    UPLOADED = "uploaded"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class KnowledgeSyncStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    PENDING_REVIEW = "pending_review"
    PENDING_SYNC = "pending_sync"
    SYNCED = "synced"
    FAILED = "failed"


class StoredFile(Base):
    __tablename__ = "files"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    note_id: Mapped[int | None] = mapped_column(ForeignKey("experiment_notes.id"), nullable=True, index=True)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    file_category: Mapped[FileCategory] = mapped_column(Enum(FileCategory), default=FileCategory.NOTE_ATTACHMENT)
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str | None] = mapped_column(String(160), nullable=True)
    file_size: Mapped[int] = mapped_column(default=0)
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[FileStatus] = mapped_column(Enum(FileStatus), default=FileStatus.UPLOADED, index=True)
    knowledge_sync_status: Mapped[str] = mapped_column(String(40), default=KnowledgeSyncStatus.NOT_APPLICABLE.value, index=True)
    knowledge_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    knowledge_sync_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
