"""Isolated PostgreSQL outage and backup/restore assertions.

The orchestration script points this helper only at its dedicated QA cluster.
No provider or Telegram network calls are made.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, func, select, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.database import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    ExtractionStatus,
    Lead,
    LeadExtraction,
    LeadHistory,
    LeadNotification,
    LeadStatus,
    NotificationKind,
    NotificationStatus,
)

LEAD_ID = uuid.UUID("9f6edcf0-4247-4d3d-8888-8cc9b6660001")
SUBMISSION_ID = uuid.UUID("9f6edcf0-4247-4d3d-8888-8cc9b6661001")


def seed_app() -> None:
    now = datetime.now(UTC)
    with SessionLocal() as db:
        if db.get(Lead, LEAD_ID) is not None:
            raise AssertionError("isolated recovery lead already exists")
        lead = Lead(
            id=LEAD_ID,
            submission_id=SUBMISSION_ID,
            payload_fingerprint="b" * 64,
            name="Synthetic Recovery Fixture",
            phone="+7 000 000-00-01",
            description=(
                "Нужен ремонт стиральной машины, бюджет 7000 рублей, "
                "срок завтра. [delay-first]"
            ),
            status=LeadStatus.IN_PROGRESS,
        )
        db.add(lead)
        db.add_all(
            [
                LeadHistory(
                    lead_id=LEAD_ID,
                    type="created",
                    message="Synthetic recovery lead created",
                ),
                LeadHistory(
                    lead_id=LEAD_ID,
                    type="status_changed",
                    message="Synthetic recovery lead moved to in_progress",
                ),
                LeadExtraction(
                    lead_id=LEAD_ID,
                    status=ExtractionStatus.PENDING,
                    available_at=now,
                ),
                LeadNotification(
                    id=uuid.UUID("9f6edcf0-4247-4d3d-8888-8cc9b6662001"),
                    lead_id=LEAD_ID,
                    kind=NotificationKind.NEW_LEAD,
                    status=NotificationStatus.SENT,
                    available_at=now,
                    attempts=1,
                    message_id=7001,
                    sent_at=now,
                ),
                LeadNotification(
                    id=uuid.UUID("9f6edcf0-4247-4d3d-8888-8cc9b6662002"),
                    lead_id=LEAD_ID,
                    kind=NotificationKind.REMINDER,
                    status=NotificationStatus.CANCELLED,
                    available_at=now + timedelta(minutes=30),
                    error_code="lead_status_changed",
                ),
            ]
        )
        db.commit()
    print("PASS seeded isolated app recovery fixture")


def wait_extraction(expected: ExtractionStatus, timeout_seconds: float) -> LeadExtraction:
    deadline = time.monotonic() + timeout_seconds
    last: LeadExtraction | None = None
    while time.monotonic() < deadline:
        try:
            with SessionLocal() as db:
                last = db.get(LeadExtraction, LEAD_ID)
                if last is not None and last.status == expected:
                    return last
        except Exception:
            # The orchestrator deliberately makes PostgreSQL unavailable.
            pass
        time.sleep(0.1)
    status = last.status if last is not None else None
    raise AssertionError(f"extraction did not reach {expected.value}; last={status}")


def verify_app() -> None:
    with SessionLocal() as db:
        lead = db.get(Lead, LEAD_ID)
        extraction = db.get(LeadExtraction, LEAD_ID)
        history = db.scalars(
            select(LeadHistory).where(LeadHistory.lead_id == LEAD_ID)
        ).all()
        notifications = db.scalars(
            select(LeadNotification).where(LeadNotification.lead_id == LEAD_ID)
        ).all()
        assert lead is not None and lead.status == LeadStatus.IN_PROGRESS
        assert extraction is not None
        assert extraction.status == ExtractionStatus.SUCCEEDED
        assert extraction.attempts == 2
        assert extraction.revision == 1
        assert extraction.service == "ремонт стиральной машины"
        assert extraction.budget_min == Decimal("7000.00")
        assert extraction.budget_max == Decimal("7000.00")
        assert extraction.budget_currency == "RUB"
        assert extraction.timeframe == "завтра"
        assert extraction.evidence_service == "ремонт стиральной машины"
        assert extraction.evidence_budget == "7000 рублей"
        assert extraction.evidence_timeframe == "завтра"
        assert len(history) == 2
        assert db.scalar(
            select(func.count()).select_from(LeadExtraction).where(
                LeadExtraction.lead_id == LEAD_ID
            )
        ) == 1
        assert {(row.kind, row.status) for row in notifications} == {
            (NotificationKind.NEW_LEAD, NotificationStatus.SENT),
            (NotificationKind.REMINDER, NotificationStatus.CANCELLED),
        }
    print("PASS app history, extraction and outbox persisted")


def n8n_metadata(url: str) -> list[dict[str, object]]:
    engine = create_engine(url, connect_args={"connect_timeout": 3})
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    'SELECT id, name, active, nodes FROM workflow_entity '
                    "WHERE id IN ('leadflow-new-lead-notifications-v1', "
                    "'leadflow-reminder-notifications-v1') ORDER BY id"
                )
            ).mappings()
            result = []
            for row in rows:
                nodes = row["nodes"]
                if isinstance(nodes, str):
                    nodes = json.loads(nodes)
                result.append(
                    {
                        "id": row["id"],
                        "name": row["name"],
                        "active": row["active"],
                        "node_count": len(nodes),
                    }
                )
            return result
    finally:
        engine.dispose()


def verify_n8n() -> None:
    source = n8n_metadata(os.environ["SOURCE_DATABASE_URL"])
    restored = n8n_metadata(os.environ["RESTORED_DATABASE_URL"])
    assert source == restored
    assert len(restored) == 2
    assert all(item["active"] is False and item["node_count"] == 5 for item in restored)
    print("PASS two inactive five-node n8n workflows restored with matching metadata")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=("seed-app", "wait-processing", "wait-succeeded", "verify-app", "verify-n8n"),
    )
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()
    if args.action == "seed-app":
        seed_app()
    elif args.action == "wait-processing":
        row = wait_extraction(ExtractionStatus.PROCESSING, args.timeout)
        assert row.attempts == 1 and row.claim_token is not None
        print("PASS worker claimed extraction before database outage")
    elif args.action == "wait-succeeded":
        row = wait_extraction(ExtractionStatus.SUCCEEDED, args.timeout)
        assert row.attempts == 2 and row.claim_token is None
        print("PASS worker recovered after database outage and expired lease")
    elif args.action == "verify-app":
        verify_app()
    else:
        verify_n8n()


if __name__ == "__main__":
    main()
