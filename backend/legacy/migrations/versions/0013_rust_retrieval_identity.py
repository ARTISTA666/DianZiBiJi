"""Add the structural identity fields required by Rust retrieval.

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-13

``legacy-unknown`` is a compatibility placeholder for rows created before
the Rust retrieval identity was recorded.  It is deliberately not an index,
chunk, embedding, corpus, or model provenance claim.  This migration makes
the fields and ordering index reproducible; it does not freeze an experiment.
"""

import sqlalchemy as sa
from alembic import op


revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


LEGACY_UNKNOWN = "legacy-unknown"
INDEX_NAME = "ix_rag_chunks_project_version"


def _column_names(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _ensure_identity_column(table_name: str, column_name: str) -> None:
    column = sa.Column(
        column_name,
        sa.String(80),
        nullable=False,
        server_default=sa.text(f"'{LEGACY_UNKNOWN}'"),
    )
    if column_name not in _column_names(table_name):
        op.add_column(table_name, column)
        return

    # Rust's startup repair existed before this migration and used the
    # ambiguous legacy-v1 default.  Normalize that default when the column
    # already exists, without changing any explicit non-default row value.
    op.alter_column(
        table_name,
        column_name,
        existing_type=sa.String(80),
        server_default=sa.text(f"'{LEGACY_UNKNOWN}'"),
    )


def upgrade() -> None:
    _ensure_identity_column("rag_file_syncs", "index_version")
    _ensure_identity_column("rag_document_chunks", "chunk_version")
    _ensure_identity_column("rag_document_chunks", "index_version")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Normalize the ambiguous marker emitted by the pre-0013 Rust startup
        # repair.  Other explicit values are preserved because they may
        # identify a real rebuild, while legacy-v1 cannot make that claim
        # safely.  SQLite is only a structural migration fallback; the
        # PostgreSQL test below is the authoritative backfill contract.
        for table_name, column_name in (
            ("rag_file_syncs", "index_version"),
            ("rag_document_chunks", "chunk_version"),
            ("rag_document_chunks", "index_version"),
        ):
            op.execute(
                sa.text(
                    f"UPDATE {table_name} SET {column_name} = :legacy_unknown "
                    f"WHERE {column_name} = 'legacy-v1'"
                ).bindparams(legacy_unknown=LEGACY_UNKNOWN)
            )

    if INDEX_NAME not in {
        index["name"] for index in sa.inspect(bind).get_indexes("rag_document_chunks")
    }:
        op.create_index(
            INDEX_NAME,
            "rag_document_chunks",
            ["project_id", "index_version", "id"],
        )

    if bind.dialect.name == "postgresql":
        # Rows that predate explicit index identity cannot be treated as
        # synced for a versioned Rust retrieval run.  Marking them stale is
        # conservative; no embedding/model/corpus provenance is fabricated.
        op.execute(
            sa.text(
                """
                UPDATE rag_file_syncs
                SET sync_status = 'stale',
                    sync_message = COALESCE(sync_message, 'Index identity unknown; explicit rebuild required'),
                    updated_at = now()
                WHERE index_version = :legacy_unknown
                  AND sync_status = 'synced'
                """
            ).bindparams(legacy_unknown=LEGACY_UNKNOWN)
        )


def downgrade() -> None:
    raise RuntimeError("Rust retrieval identity migration downgrade is intentionally disabled")
