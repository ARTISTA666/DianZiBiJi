"""Change file_size column from integer to bigint

Revision ID: 0010
Revises: 0009_add_foreign_key_indexes
Create Date: 2026-07-30
"""

from alembic import op
import sqlalchemy as sa

revision = '0010'
down_revision = '0009_add_foreign_key_indexes'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("files")}
    if "file_size" not in columns:
        return
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("files") as batch_op:
            batch_op.alter_column(
                "file_size",
                existing_type=sa.Integer(),
                type_=sa.BigInteger(),
                existing_nullable=False,
            )
    else:
        op.alter_column(
            "files",
            "file_size",
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            existing_nullable=False,
        )


def downgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("files")}
    if "file_size" not in columns:
        return
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("files") as batch_op:
            batch_op.alter_column(
                "file_size",
                existing_type=sa.BigInteger(),
                type_=sa.Integer(),
                existing_nullable=False,
            )
    else:
        op.alter_column(
            "files",
            "file_size",
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
