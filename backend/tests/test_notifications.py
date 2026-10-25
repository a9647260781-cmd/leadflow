import json
import uuid

import httpx
import pytest

from app.config import Settings
from app.models import NotificationKind
from app.notifications import (
    DeliveryDisposition,
    NotificationClaim,
    TelegramClient,
)


def _settings() -> Settings:
    return Settings(
        notifications_enabled=True,
        telegram_bot_token="123:test-token",
        telegram_chat_id="-100123",
        notifications_service_token="service-secret",
    )


def _claim() -> NotificationClaim:
    return NotificationClaim(
        notification_id=uuid.uuid4(),
        claim_token=uuid.uuid4(),
        kind=NotificationKind.NEW_LEAD,
        attempts=1,
        chat_id="-100123",
        text="Plain <b>untrusted</b> text",
    )


def test_telegram_success_uses_plain_text_and_reads_message_id() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 9876543210}})

    outcome = TelegramClient(
        _settings(), transport=httpx.MockTransport(handler)
    ).send(_claim())

    assert outcome.disposition == DeliveryDisposition.SENT
    assert outcome.message_id == 9876543210
    assert seen == {"chat_id": "-100123", "text": "Plain <b>untrusted</b> text"}
    assert "parse_mode" not in seen


@pytest.mark.parametrize(
    ("status_code", "body", "disposition", "error_code"),
    [
        (
            429,
            {"ok": False, "error_code": 429, "parameters": {"retry_after": 17}},
            DeliveryDisposition.RETRY,
            "telegram_rate_limited",
        ),
        (
            401,
            {"ok": False, "error_code": 401},
            DeliveryDisposition.FAILED,
            "telegram_auth_or_access",
        ),
        (
            403,
            {"ok": False, "error_code": 403},
            DeliveryDisposition.FAILED,
            "telegram_auth_or_access",
        ),
        (
            502,
            {"ok": False, "error_code": 502},
            DeliveryDisposition.DELIVERY_UNKNOWN,
            "telegram_server_error_unknown",
        ),
    ],
)
def test_telegram_rejection_classification(
    status_code: int,
    body: dict,
    disposition: DeliveryDisposition,
    error_code: str,
) -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(status_code, json=body))
    outcome = TelegramClient(_settings(), transport=transport).send(_claim())

    assert outcome.disposition == disposition
    assert outcome.error_code == error_code
    if status_code == 429:
        assert outcome.retry_after_seconds == 17


def test_connect_failure_retries_but_ambiguous_timeout_does_not() -> None:
    def connect_failure(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("not connected", request=request)

    def read_timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("response lost", request=request)

    retry = TelegramClient(
        _settings(), transport=httpx.MockTransport(connect_failure)
    ).send(_claim())
    unknown = TelegramClient(
        _settings(), transport=httpx.MockTransport(read_timeout)
    ).send(_claim())

    assert retry.disposition == DeliveryDisposition.RETRY
    assert unknown.disposition == DeliveryDisposition.DELIVERY_UNKNOWN


def test_invalid_success_response_is_delivery_unknown() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, json={"ok": True, "result": {}})
    )
    outcome = TelegramClient(_settings(), transport=transport).send(_claim())
    assert outcome.disposition == DeliveryDisposition.DELIVERY_UNKNOWN
