from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class NoteStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    RETURNED = "returned"
    ARCHIVED = "archived"
    VOIDED = "voided"


class ExperimentNote(Base):
    __tablename__ = "experiment_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    template_id: Mapped[int | None] = mapped_column(nullable=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    experiment_type: Mapped[str] = mapped_column(String(120), index=True)
    experiment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[NoteStatus] = mapped_column(Enum(NoteStatus), default=NoteStatus.DRAFT, index=True)
    current_version_id: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class NoteVersion(Base):
    __tablename__ = "note_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    note_id: Mapped[int] = mapped_column(ForeignKey("experiment_notes.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    fixed_fields_json: Mapped[dict] = mapped_column(JSON, default=dict)
    content_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_locked: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NoteApproval(Base):
    __tablename__ = "note_approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    note_id: Mapped[int] = mapped_column(ForeignKey("experiment_notes.id"), index=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("note_versions.id"), index=True)
    reviewer_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
