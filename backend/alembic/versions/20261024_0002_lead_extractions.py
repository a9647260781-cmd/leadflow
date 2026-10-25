"""Add durable lead extraction jobs and results.

Revision ID: 20261024_0002
Revises: 20261024_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261024_0002"
down_revision: str | None = "20261024_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    extraction_status = postgresql.ENUM(
        "not_requested",
        "pending",
        "processing",
        "succeeded",
        "failed",
        "not_configured",
        name="extraction_status",
        create_type=False,
    )
    extraction_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "lead_extractions",
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", extraction_status, server_default="not_requested", nullable=False),
        sa.Column("service", sa.String(length=300), nullable=True),
        sa.Column("budget_min", sa.Numeric(precision=16, scale=2), nullable=True),
        sa.Column("budget_max", sa.Numeric(precision=16, scale=2), nullable=True),
        sa.Column("budget_currency", sa.String(length=3), nullable=True),
        sa.Column("budget_text", sa.String(length=300), nullable=True),
        sa.Column("timeframe", sa.String(length=300), nullable=True),
        sa.Column("evidence_service", sa.Text(), nullable=True),
        sa.Column("evidence_budget", sa.Text(), nullable=True),
        sa.Column("evidence_timeframe", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_token", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("manually_edited", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("lead_id"),
    )
    op.create_index("ix_lead_extractions_available_at", "lead_extractions", ["available_at"])
    op.create_index("ix_lead_extractions_claim_token", "lead_extractions", ["claim_token"])
    op.create_index(
        "ix_lead_extractions_lease_expires_at", "lead_extractions", ["lease_expires_at"]
    )
    op.create_index(
        "ix_lead_extractions_queue",
        "lead_extractions",
        ["status", "available_at", "lease_expires_at"],
    )
    op.create_index("ix_lead_extractions_status", "lead_extractions", ["status"])

    # Existing leads remain explicitly unprocessed; this is not an automatic backfill.
    op.execute(
        sa.text(
            """
            INSERT INTO lead_extractions (lead_id, status)
            SELECT id, 'not_requested'::extraction_status FROM leads
            ON CONFLICT (lead_id) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_lead_extractions_status", table_name="lead_extractions")
    op.drop_index("ix_lead_extractions_queue", table_name="lead_extractions")
    op.drop_index("ix_lead_extractions_lease_expires_at", table_name="lead_extractions")
    op.drop_index("ix_lead_extractions_claim_token", table_name="lead_extractions")
    op.drop_index("ix_lead_extractions_available_at", table_name="lead_extractions")
    op.drop_table("lead_extractions")
    postgresql.ENUM(name="extraction_status").drop(op.get_bind(), checkfirst=True)
