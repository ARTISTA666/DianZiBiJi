"""Add agent suggestion feedback table (创新点二：建议采纳留痕)

Revision ID: 0017_agent_suggestion_feedback
Revises: 0016_project_alerts
Create Date: 2026-09-08 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op


revision = "0017_agent_suggestion_feedback"
down_revision = "0016_project_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_suggestion_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("suggestion_key", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("related_labels", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("summary", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("acted_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("acted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('accepted', 'ignored', 'expired')", name="ck_agent_suggestion_feedback_status"
        ),
        sa.UniqueConstraint(
            "project_id",
            "suggestion_key",
            name="uq_agent_suggestion_feedback_project_key",
        ),
    )
    op.create_index(
        "ix_agent_suggestion_feedback_project",
        "agent_suggestion_feedback",
        ["project_id"],
    )


def downgrade() -> None:
    op.drop_table("agent_suggestion_feedback")
