"""Invalidate existing access tokens after logout or password changes.

Revision ID: 0003_user_auth_version
Revises: 0002_runtime_schema
Create Date: 2026-07-16
"""

import sqlalchemy as sa
from alembic import op


revision = "0003_user_auth_version"
down_revision = "0002_runtime_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")}
    if "auth_version" not in existing:
        op.add_column(
            "users",
            sa.Column("auth_version", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    raise RuntimeError("Runtime schema downgrade is intentionally disabled to protect existing data")
