"""Add HNSW vector index on rag_document_chunks embedding column.

Revision ID: 0005_rag_chunks_hnsw_index
Revises: 0004_experiment_single_active
Create Date: 2026-07-28
"""

from alembic import op


revision = "0005_rag_chunks_hnsw_index"
down_revision = "0004_experiment_single_active"
branch_labels = None
depends_on = None


INDEX_NAME = "ix_rag_chunks_embedding_hnsw"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME} "
                "ON rag_document_chunks USING hnsw (embedding vector_cosine_ops)"
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
