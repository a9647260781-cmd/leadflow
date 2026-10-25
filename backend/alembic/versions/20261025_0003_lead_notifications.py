"""Add the durable notification outbox.

Revision ID: 20261025_0003
Revises: 20261024_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261025_0003"
down_revision: str | None = "20261024_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


notification_kind = postgresql.ENUM(
    "new_lead", "reminder", name="notification_kind", create_type=False
)
notification_status = postgresql.ENUM(
    "pending",
    "sending",
    "retry",
    "sent",
    "failed",
    "delivery_unknown",
    "cancelled",
    name="notification_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    notification_kind.create(bind, checkfirst=True)
    notification_status.create(bind, checkfirst=True)
    op.create_table(
        "lead_notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", notification_kind, nullable=False),
        sa.Column("status", notification_status, server_default="pending", nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_token", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("message_id", sa.BigInteger(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lead_id", "kind", name="uq_lead_notifications_lead_kind"),
    )
    op.create_index("ix_lead_notifications_lead_id", "lead_notifications", ["lead_id"])
    op.create_index("ix_lead_notifications_status", "lead_notifications", ["status"])
    op.create_index(
        "ix_lead_notifications_lease_expires_at",
        "lead_notifications",
        ["lease_expires_at"],
    )
    op.create_index("ix_lead_notifications_claim_token", "lead_notifications", ["claim_token"])
    op.create_index(
        "ix_lead_notifications_dispatch",
        "lead_notifications",
        ["kind", "status", "available_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_lead_notifications_dispatch", table_name="lead_notifications")
    op.drop_index("ix_lead_notifications_claim_token", table_name="lead_notifications")
    op.drop_index("ix_lead_notifications_lease_expires_at", table_name="lead_notifications")
    op.drop_index("ix_lead_notifications_status", table_name="lead_notifications")
    op.drop_index("ix_lead_notifications_lead_id", table_name="lead_notifications")
    op.drop_table("lead_notifications")
    postgresql.ENUM(name="notification_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="notification_kind").drop(op.get_bind(), checkfirst=True)
