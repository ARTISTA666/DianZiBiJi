"""Add project alert tables (创新点四：预警与人工审核闭环)

Revision ID: 0016_project_alerts
Revises: 0015_kg_blueprint
Create Date: 2026-09-06 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op


revision = "0016_project_alerts"
down_revision = "0015_kg_blueprint"
branch_labels = None
depends_on = None

OPEN_FILTER = "status = 'open'"


def upgrade() -> None:
    op.create_table(
        "project_alert_thresholds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("metric", sa.String(length=60), nullable=False),
        sa.Column("warn_threshold", sa.Float(), nullable=False),
        sa.Column("critical_threshold", sa.Float(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("project_id", "metric", name="uq_project_alert_threshold_metric"),
    )

    op.create_table(
        "project_alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("metric", sa.String(length=60), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=False),
        sa.Column("level", sa.String(length=12), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("acknowledged_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("level IN ('warn', 'critical')", name="ck_project_alerts_level"),
        sa.CheckConstraint(
            "status IN ('open', 'acknowledged', 'resolved')",
            name="ck_project_alerts_status",
        ),
    )
    op.create_index(
        "ix_project_alerts_project_status",
        "project_alerts",
        ["project_id", "status"],
    )
    # 同一指标同时最多一条 open 告警（评估路径按此幂等去重）。
    op.create_index(
        "uq_project_alerts_open_metric",
        "project_alerts",
        ["project_id", "metric"],
        unique=True,
        postgresql_where=sa.text(OPEN_FILTER),
        sqlite_where=sa.text(OPEN_FILTER),
    )


def downgrade() -> None:
    op.drop_index("uq_project_alerts_open_metric", table_name="project_alerts")
    op.drop_index("ix_project_alerts_project_status", table_name="project_alerts")
    op.drop_table("project_alerts")
    op.drop_table("project_alert_thresholds")
