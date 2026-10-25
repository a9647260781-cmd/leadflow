"""Initial LeadFlow schema.

Revision ID: 20261024_0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261024_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    lead_status = postgresql.ENUM(
        "new", "in_progress", "won", "lost", name="lead_status", create_type=False
    )
    lead_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "managers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_managers_email", "managers", ["email"])

    op.create_table(
        "leads",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("phone", sa.String(length=40), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", lead_status, server_default="new", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("submission_id"),
    )
    op.create_index("ix_leads_created_at", "leads", [sa.text("created_at DESC")])
    op.create_index("ix_leads_status", "leads", ["status"])

    op.create_table(
        "manager_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("manager_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["manager_id"], ["managers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_manager_sessions_expires_at", "manager_sessions", ["expires_at"])
    op.create_index("ix_manager_sessions_manager_id", "manager_sessions", ["manager_id"])
    op.create_index("ix_manager_sessions_token_hash", "manager_sessions", ["token_hash"])

    op.create_table(
        "lead_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lead_history_lead_id", "lead_history", ["lead_id"])


def downgrade() -> None:
    op.drop_index("ix_lead_history_lead_id", table_name="lead_history")
    op.drop_table("lead_history")
    op.drop_index("ix_manager_sessions_token_hash", table_name="manager_sessions")
    op.drop_index("ix_manager_sessions_manager_id", table_name="manager_sessions")
    op.drop_index("ix_manager_sessions_expires_at", table_name="manager_sessions")
    op.drop_table("manager_sessions")
    op.drop_index("ix_leads_status", table_name="leads")
    op.drop_index("ix_leads_created_at", table_name="leads")
    op.drop_table("leads")
    op.drop_index("ix_managers_email", table_name="managers")
    op.drop_table("managers")
    postgresql.ENUM(name="lead_status").drop(op.get_bind(), checkfirst=True)
