import enum
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import exists, select, update
from sqlalchemy.orm import Session, aliased

from .config import Settings
from .models import (
    Lead,
    LeadNotification,
    LeadStatus,
    NotificationKind,
    NotificationStatus,
)

# Telegram requires the bot token in the request path. Suppress transport request tracing.
for logger_name in ("httpx", "httpcore"):
    logging.getLogger(logger_name).setLevel(logging.WARNING)


class DeliveryDisposition(enum.StrEnum):
    SENT = "sent"
    RETRY = "retry"
    FAILED = "failed"
    DELIVERY_UNKNOWN = "delivery_unknown"


@dataclass(frozen=True)
class DeliveryOutcome:
    disposition: DeliveryDisposition
    error_code: str | None = None
    message_id: int | None = None
    retry_after_seconds: int | None = None


@dataclass(frozen=True)
class NotificationClaim:
    notification_id: uuid.UUID
    claim_token: uuid.UUID
    kind: NotificationKind
    attempts: int
    chat_id: str
    text: str


class TelegramClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        token = settings.telegram_bot_token
        if token is None:
            raise ValueError("Telegram is not configured")
        self._url = (
            f"{settings.telegram_api_base_url}/bot{token.get_secret_value()}/sendMessage"
        )
        self._timeout = settings.notification_request_timeout_seconds
        self._transport = transport

    def send(self, claim: NotificationClaim) -> DeliveryOutcome:
        try:
            with httpx.Client(transport=self._transport, timeout=self._timeout) as client:
                response = client.post(
                    self._url,
                    json={"chat_id": claim.chat_id, "text": claim.text},
                )
        except (httpx.ConnectError, httpx.ConnectTimeout):
            return DeliveryOutcome(
                DeliveryDisposition.RETRY, error_code="telegram_connect_failed"
            )
        except httpx.RequestError:
            return DeliveryOutcome(
                DeliveryDisposition.DELIVERY_UNKNOWN,
                error_code="telegram_delivery_unknown",
            )

        try:
            body = response.json()
        except ValueError:
            return DeliveryOutcome(
                DeliveryDisposition.DELIVERY_UNKNOWN,
                error_code="telegram_invalid_response",
            )
        if not isinstance(body, dict):
            return DeliveryOutcome(
                DeliveryDisposition.DELIVERY_UNKNOWN,
                error_code="telegram_invalid_response",
            )

        error_code = body.get("error_code", response.status_code)
        if response.status_code == 429 or error_code == 429:
            parameters = body.get("parameters")
            raw_retry = parameters.get("retry_after") if isinstance(parameters, dict) else None
            retry_after = raw_retry if isinstance(raw_retry, int) and raw_retry > 0 else None
            return DeliveryOutcome(
                DeliveryDisposition.RETRY,
                error_code="telegram_rate_limited",
                retry_after_seconds=retry_after,
            )
        if response.status_code in {401, 403} or error_code in {401, 403}:
            return DeliveryOutcome(
                DeliveryDisposition.FAILED, error_code="telegram_auth_or_access"
            )
        if response.status_code >= 500 or (
            isinstance(error_code, int) and error_code >= 500
        ):
            return DeliveryOutcome(
                DeliveryDisposition.DELIVERY_UNKNOWN,
                error_code="telegram_server_error_unknown",
            )
        if response.status_code >= 400 or body.get("ok") is not True:
            return DeliveryOutcome(
                DeliveryDisposition.FAILED, error_code="telegram_rejected"
            )

        result = body.get("result")
        message_id = result.get("message_id") if isinstance(result, dict) else None
        if not isinstance(message_id, int) or isinstance(message_id, bool):
            return DeliveryOutcome(
                DeliveryDisposition.DELIVERY_UNKNOWN,
                error_code="telegram_invalid_response",
            )
        return DeliveryOutcome(DeliveryDisposition.SENT, message_id=message_id)


def enqueue_lead_notifications(
    db: Session,
    lead_id: uuid.UUID,
    created_at: datetime,
    settings: Settings,
) -> None:
    if not settings.notifications_configured:
        return
    db.add_all(
        [
            LeadNotification(
                lead_id=lead_id,
                kind=NotificationKind.NEW_LEAD,
                status=NotificationStatus.PENDING,
                available_at=created_at,
            ),
            LeadNotification(
                lead_id=lead_id,
                kind=NotificationKind.REMINDER,
                status=NotificationStatus.PENDING,
                available_at=created_at
                + timedelta(minutes=settings.notification_reminder_minutes),
            ),
        ]
    )


def cancel_reminder(db: Session, lead_id: uuid.UUID, now: datetime | None = None) -> None:
    reminder = db.scalar(
        select(LeadNotification)
        .where(
            LeadNotification.lead_id == lead_id,
            LeadNotification.kind == NotificationKind.REMINDER,
        )
        .with_for_update()
    )
    if reminder is None:
        return
    now = now or datetime.now(UTC)
    if reminder.status in {NotificationStatus.PENDING, NotificationStatus.RETRY}:
        reminder.status = NotificationStatus.CANCELLED
        reminder.error_code = "lead_status_changed"
        reminder.available_at = now
        reminder.updated_at = now
    elif reminder.status == NotificationStatus.SENDING:
        # The request may already have reached Telegram, so cancellation cannot claim non-delivery.
        reminder.status = NotificationStatus.DELIVERY_UNKNOWN
        reminder.error_code = "status_changed_during_delivery"
        reminder.claim_token = None
        reminder.lease_expires_at = None
        reminder.updated_at = now


def recover_stale_sending(
    db: Session, kind: NotificationKind, now: datetime | None = None
) -> int:
    now = now or datetime.now(UTC)
    result = db.execute(
        update(LeadNotification)
        .where(
            LeadNotification.kind == kind,
            LeadNotification.status == NotificationStatus.SENDING,
            LeadNotification.lease_expires_at <= now,
        )
        .values(
            status=NotificationStatus.DELIVERY_UNKNOWN,
            error_code="stale_delivery_unknown",
            claim_token=None,
            lease_expires_at=None,
            updated_at=now,
        )
    )
    db.commit()
    return result.rowcount


def _plain_text(value: str, limit: int) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 1].rstrip()}…"


def _message_text(lead: Lead, kind: NotificationKind, manager_public_url: str) -> str:
    heading = "Новая заявка" if kind == NotificationKind.NEW_LEAD else "Напоминание о заявке"
    return "\n".join(
        [
            heading,
            f"Номер: {lead.id}",
            f"Имя: {_plain_text(lead.name, 120)}",
            f"Описание: {_plain_text(lead.description, 500)}",
            f"Открыть: {manager_public_url}/manager/leads/{lead.id}",
        ]
    )


def claim_next_notification(
    db: Session,
    kind: NotificationKind,
    settings: Settings,
    now: datetime | None = None,
) -> NotificationClaim | None:
    now = now or datetime.now(UTC)
    filters = [
        LeadNotification.kind == kind,
        LeadNotification.status.in_([NotificationStatus.PENDING, NotificationStatus.RETRY]),
        LeadNotification.available_at <= now,
    ]
    if kind == NotificationKind.REMINDER:
        initial_notification = aliased(LeadNotification)
        initial_sent = exists(
            select(initial_notification.id).where(
                initial_notification.lead_id == Lead.id,
                initial_notification.kind == NotificationKind.NEW_LEAD,
                initial_notification.status == NotificationStatus.SENT,
            )
        )
        filters.extend([Lead.status == LeadStatus.NEW, initial_sent])

    lead = db.scalar(
        select(Lead)
        .join(LeadNotification, LeadNotification.lead_id == Lead.id)
        .where(*filters)
        .order_by(LeadNotification.available_at, LeadNotification.id)
        .with_for_update(of=Lead, skip_locked=True)
        .limit(1)
    )
    if lead is None:
        db.rollback()
        return None
    notification = db.scalar(
        select(LeadNotification)
        .where(
            LeadNotification.lead_id == lead.id,
            LeadNotification.kind == kind,
        )
        .with_for_update()
    )
    if notification is None or notification.status not in {
        NotificationStatus.PENDING,
        NotificationStatus.RETRY,
    }:
        db.rollback()
        return None

    token = uuid.uuid4()
    notification.status = NotificationStatus.SENDING
    notification.attempts += 1
    notification.claimed_at = now
    notification.lease_expires_at = now + timedelta(seconds=settings.notification_lease_seconds)
    notification.claim_token = token
    notification.error_code = None
    notification.updated_at = now
    claim = NotificationClaim(
        notification_id=notification.id,
        claim_token=token,
        kind=kind,
        attempts=notification.attempts,
        chat_id=settings.telegram_chat_id or "",
        text=_message_text(lead, kind, settings.manager_public_url),
    )
    db.commit()
    return claim


def finish_notification(
    db: Session,
    claim: NotificationClaim,
    outcome: DeliveryOutcome,
    settings: Settings,
    now: datetime | None = None,
) -> DeliveryDisposition | None:
    now = now or datetime.now(UTC)
    notification = db.scalar(
        select(LeadNotification)
        .where(
            LeadNotification.id == claim.notification_id,
            LeadNotification.status == NotificationStatus.SENDING,
            LeadNotification.claim_token == claim.claim_token,
        )
        .with_for_update()
    )
    if notification is None:
        db.rollback()
        return None

    final_disposition = outcome.disposition
    notification.error_code = outcome.error_code
    notification.claim_token = None
    notification.lease_expires_at = None
    notification.updated_at = now
    if outcome.disposition == DeliveryDisposition.SENT:
        notification.status = NotificationStatus.SENT
        notification.message_id = outcome.message_id
        notification.sent_at = now
    elif outcome.disposition == DeliveryDisposition.RETRY:
        if notification.attempts >= settings.notification_max_attempts:
            notification.status = NotificationStatus.FAILED
            notification.error_code = "telegram_retry_exhausted"
            final_disposition = DeliveryDisposition.FAILED
        else:
            exponential = settings.notification_retry_base_seconds * (
                2 ** (notification.attempts - 1)
            )
            requested = outcome.retry_after_seconds or exponential
            delay = min(max(1, requested), settings.notification_retry_cap_seconds)
            notification.status = NotificationStatus.RETRY
            notification.available_at = now + timedelta(seconds=delay)
    elif outcome.disposition == DeliveryDisposition.FAILED:
        notification.status = NotificationStatus.FAILED
    else:
        notification.status = NotificationStatus.DELIVERY_UNKNOWN
    db.commit()
    return final_disposition


def claim_still_eligible(db: Session, claim: NotificationClaim) -> bool:
    statement = (
        select(LeadNotification.id)
        .join(Lead, Lead.id == LeadNotification.lead_id)
        .where(
            LeadNotification.id == claim.notification_id,
            LeadNotification.status == NotificationStatus.SENDING,
            LeadNotification.claim_token == claim.claim_token,
        )
    )
    if claim.kind == NotificationKind.REMINDER:
        statement = statement.where(Lead.status == LeadStatus.NEW)
    eligible = db.scalar(statement) is not None
    # Never keep a read transaction open across the external request.
    db.rollback()
    return eligible


def dispatch_notifications(
    db: Session,
    kind: NotificationKind,
    limit: int,
    settings: Settings,
    client: TelegramClient,
) -> dict[str, int | str]:
    counts = {
        "kind": kind.value,
        "claimed": 0,
        "sent": 0,
        "retried": 0,
        "failed": 0,
        "delivery_unknown": recover_stale_sending(db, kind),
        "skipped": 0,
    }
    for _ in range(limit):
        claim = claim_next_notification(db, kind, settings)
        if claim is None:
            break
        counts["claimed"] += 1
        if not claim_still_eligible(db, claim):
            counts["skipped"] += 1
            continue
        final = finish_notification(db, claim, client.send(claim), settings)
        if final is None:
            counts["skipped"] += 1
        elif final == DeliveryDisposition.SENT:
            counts["sent"] += 1
        elif final == DeliveryDisposition.RETRY:
            counts["retried"] += 1
        elif final == DeliveryDisposition.FAILED:
            counts["failed"] += 1
        else:
            counts["delivery_unknown"] += 1
    return counts
