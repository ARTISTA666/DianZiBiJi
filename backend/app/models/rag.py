from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RagDatasetStatus(StrEnum):
    ACTIVE = "active"
    FAILED = "failed"


class RagSyncStatus(StrEnum):
    PENDING = "pending"
    SYNCED = "synced"
    FAILED = "failed"


class ProjectRagDataset(Base):
    __tablename__ = "project_rag_datasets"
    __table_args__ = (UniqueConstraint("project_id", name="uq_project_rag_dataset"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    dify_dataset_id: Mapped[str] = mapped_column(String(120), index=True)
    dify_dataset_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(40), default=RagDatasetStatus.ACTIVE.value, index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class RagFileSync(Base):
    __tablename__ = "rag_file_syncs"
    __table_args__ = (UniqueConstraint("file_id", name="uq_rag_file_sync_file"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    dify_dataset_id: Mapped[str] = mapped_column(String(120), index=True)
    dify_document_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    sync_status: Mapped[str] = mapped_column(String(40), default=RagSyncStatus.PENDING.value, index=True)
    sync_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
