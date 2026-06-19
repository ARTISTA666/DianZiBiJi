from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.types import TypeDecorator, UserDefinedType
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RagDatasetStatus(StrEnum):
    ACTIVE = "active"
    FAILED = "failed"


class RagSyncStatus(StrEnum):
    PENDING = "pending"
    SYNCED = "synced"
    FAILED = "failed"


class PostgreSQLVector(UserDefinedType):
    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **_kw) -> str:
        return f"VECTOR({self.dimensions})"

    def bind_processor(self, _dialect):
        def process(value):
            if value is None or isinstance(value, str):
                return value
            return "[" + ",".join(format(float(item), ".9g") for item in value) + "]"

        return process

    def result_processor(self, _dialect, _coltype):
        def process(value):
            if value is None or isinstance(value, list):
                return value
            return [float(item) for item in str(value).strip("[]").split(",") if item]

        return process


class EmbeddingVector(TypeDecorator):
    """Use pgvector in PostgreSQL and JSON in SQLite-based tests."""

    impl = JSON
    cache_ok = True

    def __init__(self, dimensions: int = 512) -> None:
        super().__init__()
        self.dimensions = dimensions

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PostgreSQLVector(self.dimensions))
        return dialect.type_descriptor(JSON())

    class comparator_factory(TypeDecorator.Comparator):
        def cosine_distance(self, other):
            return self.expr.op("<=>", return_type=Float)(other)


class ProjectRagDataset(Base):
    __tablename__ = "project_rag_datasets"
    __table_args__ = (UniqueConstraint("project_id", name="uq_project_rag_dataset"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    dify_dataset_id: Mapped[str] = mapped_column(String(120), index=True)
    dify_dataset_name: Mapped[str] = mapped_column(String(255))
    provider: Mapped[str] = mapped_column(String(40), default="local_deepseek", index=True)
    embedding_model: Mapped[str] = mapped_column(String(160), default="BAAI/bge-small-zh-v1.5")
    generation_model: Mapped[str] = mapped_column(String(120), default="deepseek-v4-flash")
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
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    sync_status: Mapped[str] = mapped_column(String(40), default=RagSyncStatus.PENDING.value, index=True)
    sync_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class RagDocumentChunk(Base):
    __tablename__ = "rag_document_chunks"
    __table_args__ = (UniqueConstraint("file_id", "chunk_index", name="uq_rag_chunk_file_index"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    character_count: Mapped[int] = mapped_column(Integer, default=0)
    embedding: Mapped[list[float]] = mapped_column(EmbeddingVector(512))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
