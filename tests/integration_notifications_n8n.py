"""Fixture-only notification E2E driven by the real n8n CLI."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    LeadNotification,
    NotificationKind,
    NotificationStatus,
)


API = "http://127.0.0.1:18000/api"
ORIGIN = "http://localhost:8080"
NEW_WORKFLOW = "leadflow-new-lead-notifications-v1"
REMINDER_WORKFLOW = "leadflow-reminder-notifications-v1"


def load_env(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name, value = line.split("=", 1)
        os.environ[name] = value


def call(opener, method: str, path: str, payload=None, headers=None):
    data = None if payload is None else json.dumps(payload).encode()
    request_headers = {"Accept": "application/json", **(headers or {})}
    if data is not None:
        request_headers["Content-Type"] = "application/json"
    request = Request(f"{API}{path}", data=data, headers=request_headers, method=method)
    try:
        with opener.open(request, timeout=5) as response:
            body = response.read()
            return response.status, json.loads(body) if body else None
    except HTTPError as exc:
        body = exc.read()
        return exc.code, json.loads(body) if body else None


def create_lead(opener, description: str, submission_id: str | None = None):
    submission_id = submission_id or str(uuid.uuid4())
    payload = {
        "submission_id": submission_id,
        "name": "Notification Fixture",
        "phone": "+7 999 000-25-10",
        "description": description,
    }
    status, created = call(opener, "POST", "/leads", payload, {"Origin": ORIGIN})
    assert status == 201
    return created["id"], submission_id, payload


def notifications(lead_id: str) -> dict[NotificationKind, LeadNotification]:
    with SessionLocal() as db:
        rows = db.scalars(
            select(LeadNotification).where(LeadNotification.lead_id == uuid.UUID(lead_id))
        ).all()
        return {row.kind: row for row in rows}


def force_due(lead_id: str, kind: NotificationKind) -> None:
    with SessionLocal() as db:
        row = db.scalar(
            select(LeadNotification).where(
                LeadNotification.lead_id == uuid.UUID(lead_id),
                LeadNotification.kind == kind,
            )
        )
        assert row is not None
        row.available_at = datetime.now(UTC)
        db.commit()


def run_workflow(workflow_id: str) -> None:
    result = subprocess.run(
        [os.environ["LEADFLOW_N8N_NODE"], os.environ["LEADFLOW_N8N_CLI"], "execute", "--id", workflow_id],
        cwd=ROOT,
        env=os.environ,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        detail = re.sub(
            r"Bearer\s+[^\s\"']+", "Bearer [redacted]", f"{result.stdout}\n{result.stderr}"
        )[-2000:]
        raise AssertionError(
            f"n8n workflow {workflow_id} failed with exit {result.returncode}: {detail}"
        )


def fixture_total() -> int:
    with urlopen("http://127.0.0.1:18081/state", timeout=3) as response:
        return json.load(response)["total"]


def main() -> int:
    load_env(ROOT / ".runtime" / "demo-credentials.env")
    opener = build_opener(HTTPCookieProcessor(CookieJar()))

    missing, _ = call(opener, "POST", "/internal/notifications/dispatch", {"kind": "new_lead", "limit": 1})
    assert missing == 401
    bad, _ = call(
        opener,
        "POST",
        "/internal/notifications/dispatch",
        {"kind": "new_lead", "limit": 1},
        {"Authorization": "Bearer wrong"},
    )
    assert bad == 401

    login_status, _ = call(
        opener,
        "POST",
        "/auth/login",
        {"email": os.environ["MANAGER_EMAIL"], "password": os.environ["MANAGER_PASSWORD"]},
        {"Origin": ORIGIN},
    )
    assert login_status == 200

    lead_id, _, payload = create_lead(opener, "Уведомление и напоминание: тест успешной доставки.")
    replay, replay_body = call(opener, "POST", "/leads", payload, {"Origin": ORIGIN})
    assert replay == 200 and replay_body["id"] == lead_id
    rows = notifications(lead_id)
    assert set(rows) == {NotificationKind.NEW_LEAD, NotificationKind.REMINDER}
    run_workflow(NEW_WORKFLOW)
    rows = notifications(lead_id)
    assert rows[NotificationKind.NEW_LEAD].status == NotificationStatus.SENT
    assert rows[NotificationKind.NEW_LEAD].attempts == 1
    assert rows[NotificationKind.NEW_LEAD].message_id is not None
    assert rows[NotificationKind.REMINDER].status == NotificationStatus.PENDING
    force_due(lead_id, NotificationKind.REMINDER)
    run_workflow(REMINDER_WORKFLOW)
    assert notifications(lead_id)[NotificationKind.REMINDER].status == NotificationStatus.SENT

    cancelled_id, _, _ = create_lead(opener, "Напоминание должно отмениться после смены статуса.")
    run_workflow(NEW_WORKFLOW)
    changed, _ = call(
        opener,
        "PATCH",
        f"/leads/{cancelled_id}",
        {"status": "in_progress"},
        {"Origin": ORIGIN},
    )
    assert changed == 200
    cancelled = notifications(cancelled_id)[NotificationKind.REMINDER]
    assert cancelled.status == NotificationStatus.CANCELLED
    assert cancelled.error_code == "lead_status_changed"
    before_cancel_dispatch = fixture_total()
    run_workflow(REMINDER_WORKFLOW)
    assert fixture_total() == before_cancel_dispatch
    reopened, _ = call(
        opener,
        "PATCH",
        f"/leads/{cancelled_id}",
        {"status": "new"},
        {"Origin": ORIGIN},
    )
    assert reopened == 200
    assert notifications(cancelled_id)[NotificationKind.REMINDER].status == NotificationStatus.CANCELLED

    retry_id, _, _ = create_lead(opener, "Повтор после 429. [rate-limit-once]")
    run_workflow(NEW_WORKFLOW)
    retry_row = notifications(retry_id)[NotificationKind.NEW_LEAD]
    assert retry_row.status == NotificationStatus.RETRY
    assert retry_row.attempts == 1 and retry_row.error_code == "telegram_rate_limited"
    force_due(retry_id, NotificationKind.NEW_LEAD)
    run_workflow(NEW_WORKFLOW)
    retry_row = notifications(retry_id)[NotificationKind.NEW_LEAD]
    assert retry_row.status == NotificationStatus.SENT and retry_row.attempts == 2

    timeout_id, _, _ = create_lead(opener, "Неопределённая доставка после timeout. [timeout]")
    run_workflow(NEW_WORKFLOW)
    timeout_row = notifications(timeout_id)[NotificationKind.NEW_LEAD]
    assert timeout_row.status == NotificationStatus.DELIVERY_UNKNOWN
    assert timeout_row.error_code == "telegram_delivery_unknown"
    before_second_timeout = fixture_total()
    run_workflow(NEW_WORKFLOW)
    assert fixture_total() == before_second_timeout
    assert notifications(timeout_id)[NotificationKind.NEW_LEAD].attempts == 1

    print(
        "PASS real n8n CLI + loopback Telegram: auth guard, duplicate outbox, new lead, "
        "due reminder, cancellation, 429 retry, timeout delivery_unknown"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
