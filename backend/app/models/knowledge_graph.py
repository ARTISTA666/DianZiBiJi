from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Float, ForeignKey, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class KnowledgeEntityType(StrEnum):
    PROJECT = "project"
    NOTE = "note"
    USER = "user"
    FILE = "file"
    EXPERIMENT_TYPE = "experiment_type"
    REAGENT = "reagent"
    INSTRUMENT = "instrument"
    SAMPLE = "sample"
    RESULT = "result"


class KnowledgeRelationType(StrEnum):
    HAS_NOTE = "has_note"
    CREATED_BY = "created_by"
    HAS_ATTACHMENT = "has_attachment"
    HAS_EXPERIMENT_TYPE = "has_experiment_type"
    USES_REAGENT = "uses_reagent"
    USES_INSTRUMENT = "uses_instrument"
    USES_SAMPLE = "uses_sample"
    PRODUCES_RESULT = "produces_result"


class KnowledgeExtractionStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class KnowledgeEntity(Base):
    __tablename__ = "kg_entities"
    __table_args__ = (UniqueConstraint("project_id", "natural_key", name="uq_kg_entity_project_natural_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    label: Mapped[str] = mapped_column(String(255), index=True)
    normalized_label: Mapped[str] = mapped_column(String(255), index=True)
    natural_key: Mapped[str] = mapped_column(String(320), index=True)
    source_type: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    source_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    properties: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class KnowledgeRelation(Base):
    __tablename__ = "kg_relations"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "source_entity_id",
            "target_entity_id",
            "relation_type",
            name="uq_kg_relation_project_source_target_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    source_entity_id: Mapped[int] = mapped_column(ForeignKey("kg_entities.id"), index=True)
    target_entity_id: Mapped[int] = mapped_column(ForeignKey("kg_entities.id"), index=True)
    relation_type: Mapped[str] = mapped_column(String(60), index=True)
    source_type: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    source_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    properties: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeExtractionRun(Base):
    __tablename__ = "kg_extraction_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    note_id: Mapped[int] = mapped_column(ForeignKey("experiment_notes.id"), index=True)
    triggered_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), default=KnowledgeExtractionStatus.COMPLETED.value, index=True)
    extracted_entities: Mapped[int] = mapped_column(default=0)
    extracted_relations: Mapped[int] = mapped_column(default=0)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
