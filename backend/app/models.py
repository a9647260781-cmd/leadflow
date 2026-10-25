import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class LeadStatus(enum.StrEnum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    WON = "won"
    LOST = "lost"


class ExtractionStatus(enum.StrEnum):
    NOT_REQUESTED = "not_requested"
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    NOT_CONFIGURED = "not_configured"


class NotificationKind(enum.StrEnum):
    NEW_LEAD = "new_lead"
    REMINDER = "reminder"


class NotificationStatus(enum.StrEnum):
    PENDING = "pending"
    SENDING = "sending"
    RETRY = "retry"
    SENT = "sent"
    FAILED = "failed"
    DELIVERY_UNKNOWN = "delivery_unknown"
    CANCELLED = "cancelled"


class Manager(Base):
    __tablename__ = "managers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ManagerSession(Base):
    __tablename__ = "manager_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    manager_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("managers.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    manager: Mapped[Manager] = relationship()


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=False
    )
    payload_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[LeadStatus] = mapped_column(
        Enum(
            LeadStatus, name="lead_status", values_callable=lambda values: [v.value for v in values]
        ),
        default=LeadStatus.NEW,
        server_default=LeadStatus.NEW.value,
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    history: Mapped[list["LeadHistory"]] = relationship(
        back_populates="lead",
        cascade="all, delete-orphan",
        order_by="LeadHistory.created_at, LeadHistory.id",
    )
    extraction: Mapped["LeadExtraction"] = relationship(
        back_populates="lead", cascade="all, delete-orphan", uselist=False
    )
    notifications: Mapped[list["LeadNotification"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_leads_created_at", created_at.desc()),)


class LeadHistory(Base):
    __tablename__ = "lead_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    lead: Mapped[Lead] = relationship(back_populates="history")


class LeadExtraction(Base):
    __tablename__ = "lead_extractions"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[ExtractionStatus] = mapped_column(
        Enum(
            ExtractionStatus,
            name="extraction_status",
            values_callable=lambda values: [v.value for v in values],
        ),
        default=ExtractionStatus.NOT_REQUESTED,
        server_default=ExtractionStatus.NOT_REQUESTED.value,
        nullable=False,
        index=True,
    )
    service: Mapped[str | None] = mapped_column(String(300))
    budget_min: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    budget_max: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    budget_currency: Mapped[str | None] = mapped_column(String(3))
    budget_text: Mapped[str | None] = mapped_column(String(300))
    timeframe: Mapped[str | None] = mapped_column(String(300))
    evidence_service: Mapped[str | None] = mapped_column(Text)
    evidence_budget: Mapped[str | None] = mapped_column(Text)
    evidence_timeframe: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(80))
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    claim_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    manually_edited: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    lead: Mapped[Lead] = relationship(back_populates="extraction")

    @property
    def evidence(self) -> dict[str, str | None]:
        return {
            "service": self.evidence_service,
            "budget": self.evidence_budget,
            "timeframe": self.evidence_timeframe,
        }

    __table_args__ = (Index("ix_lead_extractions_queue", status, available_at, lease_expires_at),)


class LeadNotification(Base):
    __tablename__ = "lead_notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[NotificationKind] = mapped_column(
        Enum(
            NotificationKind,
            name="notification_kind",
            values_callable=lambda values: [v.value for v in values],
        ),
        nullable=False,
    )
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(
            NotificationStatus,
            name="notification_status",
            values_callable=lambda values: [v.value for v in values],
        ),
        default=NotificationStatus.PENDING,
        server_default=NotificationStatus.PENDING.value,
        nullable=False,
        index=True,
    )
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    claim_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    message_id: Mapped[int | None] = mapped_column(BigInteger)
    error_code: Mapped[str | None] = mapped_column(String(80))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    lead: Mapped[Lead] = relationship(back_populates="notifications")

    __table_args__ = (
        UniqueConstraint("lead_id", "kind", name="uq_lead_notifications_lead_kind"),
        Index("ix_lead_notifications_dispatch", kind, status, available_at),
    )
