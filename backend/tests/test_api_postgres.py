import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    pytest.skip(
        "TEST_DATABASE_URL is required for PostgreSQL integration tests", allow_module_level=True
    )

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["APP_ORIGIN"] = "http://localhost:8080"

from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from alembic import command  # noqa: E402
from app.config import Settings, get_settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.demo_data import (  # noqa: E402
    DEMO_LEADS,
    DemoDataCollision,
    demo_lead_ids,
    reset_demo_data,
    seed_demo_data,
)
from app.extraction import ExtractionEvidenceData, ExtractionResult, ProviderError  # noqa: E402
from app.extraction_jobs import (  # noqa: E402
    claim_next,
    complete_claim,
    fail_claim,
    mark_unconfigured_jobs,
)
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    ExtractionStatus,
    Lead,
    LeadExtraction,
    LeadHistory,
    LeadNotification,
    LeadStatus,
    Manager,
    ManagerSession,
    NotificationKind,
    NotificationStatus,
)
from app.notifications import (  # noqa: E402
    DeliveryDisposition,
    DeliveryOutcome,
    claim_next_notification,
    claim_still_eligible,
    dispatch_notifications,
    finish_notification,
    recover_stale_sending,
)
from app.rate_limit import rate_limiter  # noqa: E402
from app.routers.internal import get_telegram_client  # noqa: E402
from app.security import hash_password, hash_session_token  # noqa: E402

ORIGIN = {"Origin": "http://localhost:8080"}


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    yield
    command.downgrade(config, "base")


@pytest.fixture(autouse=True)
def clean_database() -> None:
    rate_limiter.clear()
    with SessionLocal() as db:
        manager = Manager(
            email="manager@example.com",
            name="Main Manager",
            password_hash=hash_password("correct horse battery staple"),
        )
        db.add(manager)
        db.commit()
    yield
    with SessionLocal() as db:
        for table in reversed(Manager.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()


def login(client: TestClient) -> dict:
    response = client.post(
        "/api/auth/login",
        headers=ORIGIN,
        json={"email": "MANAGER@example.com", "password": "correct horse battery staple"},
    )
    assert response.status_code == 200
    return response.json()


def test_origin_auth_idempotency_cabinet_history_and_logout() -> None:
    with TestClient(app) as public_client:
        payload = {
            "submission_id": str(uuid.uuid4()),
            "name": "Ada Lovelace",
            "phone": "+44 20 1234 5678",
            "description": "Needs a conversion-focused launch page.",
        }

        assert public_client.post("/api/leads", json=payload).status_code == 403
        assert public_client.post("/api/auth/login", json={}).status_code == 403
        assert public_client.get("/api/leads").status_code == 401

        first = public_client.post("/api/leads", headers=ORIGIN, json=payload)
        assert first.status_code == 201
        assert set(first.json()) == {"id", "created_at"}

        replay = public_client.post("/api/leads", headers=ORIGIN, json=payload)
        assert replay.status_code == 200
        assert replay.json() == first.json()

        changed = {**payload, "description": "Changed request"}
        conflict = public_client.post("/api/leads", headers=ORIGIN, json=changed)
        assert conflict.status_code == 409

    with TestClient(app) as manager_client:
        manager = login(manager_client)
        assert manager["email"] == "manager@example.com"
        assert manager_client.get("/api/auth/me").json() == manager

        listed = manager_client.get("/api/leads?search=Ada&status=new&page=1&page_size=10")
        assert listed.status_code == 200
        assert listed.json()["total"] == 1
        lead_id = listed.json()["items"][0]["id"]

        detail = manager_client.get(f"/api/leads/{lead_id}")
        assert detail.status_code == 200
        assert [event["type"] for event in detail.json()["history"]] == ["created"]

        assert (
            manager_client.patch(f"/api/leads/{lead_id}", json={"status": "won"}).status_code == 403
        )
        updated = manager_client.patch(
            f"/api/leads/{lead_id}", headers=ORIGIN, json={"status": "won"}
        )
        assert updated.status_code == 200
        assert updated.json()["status"] == "won"
        assert [event["type"] for event in updated.json()["history"]] == [
            "created",
            "status_changed",
        ]

        logout = manager_client.post("/api/auth/logout", headers=ORIGIN)
        assert logout.status_code == 204
        assert manager_client.get("/api/auth/me").status_code == 401

        with SessionLocal() as db:
            sessions = list(db.scalars(select(ManagerSession)))
            assert len(sessions) == 1
            assert sessions[0].revoked_at is not None


def test_validation_and_auth_failures() -> None:
    with TestClient(app) as client:
        invalid = client.post(
            "/api/leads",
            headers=ORIGIN,
            json={
                "submission_id": str(uuid.uuid4()),
                "name": " ",
                "phone": "12",
                "description": " ",
            },
        )
        assert invalid.status_code == 422
        bad_login = client.post(
            "/api/auth/login",
            headers=ORIGIN,
            json={"email": "manager@example.com", "password": "wrong"},
        )
        assert bad_login.status_code == 401
        assert bad_login.json() == {"detail": "Invalid email or password"}


def test_concurrent_identical_submissions_create_one_lead() -> None:
    payload = {
        "submission_id": str(uuid.uuid4()),
        "name": "Concurrency Test",
        "phone": "+1 555 0100",
        "description": "The same browser retry reached two workers.",
    }

    def submit() -> tuple[int, str]:
        with TestClient(app) as client:
            response = client.post("/api/leads", headers=ORIGIN, json=payload)
            return response.status_code, response.json()["id"]

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: submit(), range(2)))

    assert sorted(status_code for status_code, _ in results) == [200, 201]
    assert len({lead_id for _, lead_id in results}) == 1


def test_expired_session_is_rejected() -> None:
    raw_token = "expired-test-session-token"
    with SessionLocal() as db:
        manager = db.scalar(select(Manager).where(Manager.email == "manager@example.com"))
        assert manager is not None
        db.add(
            ManagerSession(
                manager_id=manager.id,
                token_hash=hash_session_token(raw_token),
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
        db.commit()

    with TestClient(app) as client:
        client.cookies.set("leadflow_session", raw_token, path="/api")
        assert client.get("/api/auth/me").status_code == 401


def _stored_lead(db, *, extraction_status: ExtractionStatus = ExtractionStatus.PENDING) -> Lead:
    lead = Lead(
        submission_id=uuid.uuid4(),
        payload_fingerprint="a" * 64,
        name="AI Queue",
        phone="+7 900 000-00-00",
        description="Нужен ремонт кухни за 500000 рублей, срок два месяца.",
        status=LeadStatus.NEW,
    )
    lead.extraction = LeadExtraction(
        status=extraction_status,
        available_at=datetime.now(UTC) if extraction_status == ExtractionStatus.PENDING else None,
    )
    db.add(lead)
    db.commit()
    return lead


def _result(service: str = "ремонт кухни") -> ExtractionResult:
    return ExtractionResult(
        service=service,
        budget_min=500000,
        budget_max=500000,
        budget_currency="RUB",
        budget_text="500000 рублей",
        timeframe="два месяца",
        evidence=ExtractionEvidenceData(
            service="ремонт кухни",
            budget="500000 рублей",
            timeframe="два месяца",
        ),
    )


def test_claim_is_atomic_and_expired_lease_is_recovered() -> None:
    settings = Settings(extraction_lease_seconds=30)
    with SessionLocal() as db:
        lead = _stored_lead(db)
        lead_id = lead.id

    def claim_in_own_session():
        with SessionLocal() as db:
            return claim_next(db, settings)

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(lambda _: claim_in_own_session(), range(2)))
    claimed = [claim for claim in claims if claim is not None]
    assert len(claimed) == 1
    first_token = claimed[0].claim_token

    with SessionLocal() as db:
        extraction = db.get(LeadExtraction, lead_id)
        assert extraction is not None
        extraction.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    with SessionLocal() as db:
        recovered = claim_next(db, settings)
    assert recovered is not None
    assert recovered.lead_id == lead_id
    assert recovered.claim_token != first_token
    assert recovered.attempts == 2


def test_manual_revision_fences_stale_worker_completion() -> None:
    settings = Settings()
    with SessionLocal() as db:
        lead = _stored_lead(db)
        lead_id = lead.id
    with SessionLocal() as db:
        claim = claim_next(db, settings)
    assert claim is not None

    with SessionLocal() as db:
        extraction = db.get(LeadExtraction, lead_id)
        assert extraction is not None
        extraction.service = "исправлено менеджером"
        extraction.status = ExtractionStatus.SUCCEEDED
        extraction.manually_edited = True
        extraction.revision += 1
        extraction.claim_token = None
        db.commit()

    with SessionLocal() as db:
        assert not complete_claim(db, claim, _result())
    with SessionLocal() as db:
        extraction = db.get(LeadExtraction, lead_id)
        assert extraction is not None
        assert extraction.service == "исправлено менеджером"
        assert extraction.manually_edited


def test_worker_completion_increments_revision_and_rejects_open_manual_draft() -> None:
    settings = Settings()
    with SessionLocal() as db:
        lead = _stored_lead(db)
        lead_id = lead.id
    with TestClient(app) as client:
        login(client)
        opened = client.get(f"/api/leads/{lead_id}").json()["extraction"]
        assert opened["revision"] == 0

        with SessionLocal() as db:
            claim = claim_next(db, settings)
        assert claim is not None
        with SessionLocal() as db:
            assert complete_claim(db, claim, _result())
        with SessionLocal() as db:
            completed = db.get(LeadExtraction, lead_id)
            assert completed is not None
            assert completed.revision == 1

        stale_body = {
            "expected_revision": opened["revision"],
            "service": "ремонт кухни",
            "budget_min": 500000,
            "budget_max": 500000,
            "budget_currency": "RUB",
            "budget_text": "500000 рублей",
            "timeframe": "два месяца",
            "evidence": {
                "service": "ремонт кухни",
                "budget": "500000 рублей",
                "timeframe": "два месяца",
            },
        }
        response = client.patch(f"/api/leads/{lead_id}/extraction", headers=ORIGIN, json=stale_body)
        assert response.status_code == 409


def test_retry_is_bounded_and_auth_failure_is_permanent() -> None:
    settings = Settings(extraction_max_attempts=2, extraction_retry_base_seconds=1)
    with SessionLocal() as db:
        first_lead = _stored_lead(db)
        first_id = first_lead.id
    with SessionLocal() as db:
        first_claim = claim_next(db, settings)
        assert first_claim is not None
        assert fail_claim(
            db,
            first_claim,
            ProviderError("provider_rate_limited", retryable=True),
            settings,
        )
    with SessionLocal() as db:
        extraction = db.get(LeadExtraction, first_id)
        assert extraction is not None
        extraction.available_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    with SessionLocal() as db:
        second_claim = claim_next(db, settings)
        assert second_claim is not None
        assert fail_claim(
            db,
            second_claim,
            ProviderError("provider_unavailable", retryable=True),
            settings,
        )
    with SessionLocal() as db:
        exhausted = db.get(LeadExtraction, first_id)
        assert exhausted is not None
        assert exhausted.status == ExtractionStatus.FAILED
        assert exhausted.error_code == "provider_unavailable"

        second_lead = _stored_lead(db)
        second_id = second_lead.id
    with SessionLocal() as db:
        auth_claim = claim_next(db, settings)
        assert auth_claim is not None and auth_claim.lead_id == second_id
        fail_claim(db, auth_claim, ProviderError("provider_auth", retryable=False), settings)
    with SessionLocal() as db:
        permanent = db.get(LeadExtraction, second_id)
        assert permanent is not None
        assert permanent.status == ExtractionStatus.FAILED
        assert permanent.attempts == 1


def test_extraction_api_auth_manual_provenance_and_retry_fencing() -> None:
    payload = {
        "submission_id": str(uuid.uuid4()),
        "name": "Manual AI",
        "phone": "+7 900 000-00-00",
        "description": "Нужен ремонт кухни за 500000 рублей, срок два месяца.",
    }
    with TestClient(app) as client:
        created = client.post("/api/leads", headers=ORIGIN, json=payload)
        lead_id = created.json()["id"]
        assert (
            client.patch(f"/api/leads/{lead_id}/extraction", headers=ORIGIN, json={}).status_code
            == 401
        )
        login(client)
        detail = client.get(f"/api/leads/{lead_id}").json()
        assert detail["extraction"]["status"] == "not_configured"

        manual = {
            "expected_revision": detail["extraction"]["revision"],
            "service": "ремонт кухни",
            "budget_min": 500000,
            "budget_max": 500000,
            "budget_currency": "rub",
            "budget_text": "500000 рублей",
            "timeframe": "два месяца",
            "evidence": {
                "service": "ремонт кухни",
                "budget": "500000 рублей",
                "timeframe": "два месяца",
            },
        }
        bad = {**manual, "evidence": {**manual["evidence"], "service": "выдумано"}}
        assert (
            client.patch(f"/api/leads/{lead_id}/extraction", headers=ORIGIN, json=bad).status_code
            == 422
        )
        saved = client.patch(f"/api/leads/{lead_id}/extraction", headers=ORIGIN, json=manual)
        assert saved.status_code == 200
        assert saved.json()["manually_edited"] is True
        assert saved.json()["budget_currency"] == "RUB"
        revision = saved.json()["revision"]

        stale = client.patch(f"/api/leads/{lead_id}/extraction", headers=ORIGIN, json=manual)
        assert stale.status_code == 409
        assert stale.json() == {"detail": "Extraction was changed; reload before saving"}

        configured = Settings(
            ai_enabled=True,
            yandex_api_key="test-key",
            yandex_model_uri="gpt://folder/yandexgpt-5.1",
        )
        app.dependency_overrides[get_settings] = lambda: configured
        try:
            protected = client.post(
                f"/api/leads/{lead_id}/extraction/retry", headers=ORIGIN, json={}
            )
            assert protected.status_code == 409
            queued = client.post(
                f"/api/leads/{lead_id}/extraction/retry",
                headers=ORIGIN,
                json={"overwrite_manual": True},
            )
            assert queued.status_code == 202
            assert queued.json()["status"] == "pending"
            assert queued.json()["service"] == "ремонт кухни"
            assert queued.json()["revision"] == revision + 1
            duplicate = client.post(
                f"/api/leads/{lead_id}/extraction/retry", headers=ORIGIN, json={}
            )
            assert duplicate.status_code == 200
        finally:
            app.dependency_overrides.pop(get_settings, None)


def test_new_lead_is_queued_when_provider_is_configured() -> None:
    configured = Settings(
        ai_enabled=True,
        yandex_api_key="test-key",
        yandex_model_uri="gpt://folder/yandexgpt-5.1",
    )
    app.dependency_overrides[get_settings] = lambda: configured
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/leads",
                headers=ORIGIN,
                json={
                    "submission_id": str(uuid.uuid4()),
                    "name": "Queued Lead",
                    "phone": "+7 900 000-00-01",
                    "description": "Нужен аудит.",
                },
            )
            assert created.status_code == 201
            with SessionLocal() as db:
                extraction = db.get(LeadExtraction, created.json()["id"])
                assert extraction is not None
                assert extraction.status == ExtractionStatus.PENDING
                assert extraction.available_at is not None
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_migration_preserves_old_lead_as_not_requested() -> None:
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    command.downgrade(config, "20261024_0001")
    old_id = uuid.uuid4()
    try:
        with SessionLocal() as db:
            db.add(
                Lead(
                    id=old_id,
                    submission_id=uuid.uuid4(),
                    payload_fingerprint="b" * 64,
                    name="Old lead",
                    phone="+7 900 000-00-02",
                    description="Created before extraction existed.",
                    status=LeadStatus.NEW,
                )
            )
            db.commit()
        command.upgrade(config, "head")
        with SessionLocal() as db:
            assert db.get(Lead, old_id) is not None
            extraction = db.get(LeadExtraction, old_id)
            assert extraction is not None
            assert extraction.status == ExtractionStatus.NOT_REQUESTED
            assert list(
                db.scalars(
                    select(LeadNotification).where(LeadNotification.lead_id == old_id)
                )
            ) == []
    finally:
        command.upgrade(config, "head")


def test_disabled_provider_terminalizes_unfinished_jobs_and_fences_workers() -> None:
    with SessionLocal() as db:
        pending = _stored_lead(db)
        pending_id = pending.id
        manual = _stored_lead(db)
        manual_id = manual.id
        manual.extraction.manually_edited = True
        manual.extraction.service = "ручное значение"
        db.commit()
    with SessionLocal() as db:
        claim = claim_next(db, Settings())
    assert claim is not None

    with SessionLocal() as db:
        assert mark_unconfigured_jobs(db) == 2
    with SessionLocal() as db:
        for lead_id in (pending_id, manual_id):
            extraction = db.get(LeadExtraction, lead_id)
            assert extraction is not None
            assert extraction.status == ExtractionStatus.NOT_CONFIGURED
            assert extraction.error_code == "not_configured"
            assert extraction.claim_token is None
        preserved = db.get(LeadExtraction, manual_id)
        assert preserved is not None
        assert preserved.service == "ручное значение"
        assert preserved.manually_edited is True
        assert not complete_claim(db, claim, _result())


def test_not_configured_retry_is_explicit_after_configuration() -> None:
    payload = {
        "submission_id": str(uuid.uuid4()),
        "name": "Later Configured",
        "phone": "+7 900 000-00-03",
        "description": "Нужен ремонт.",
    }
    with TestClient(app) as client:
        lead_id = client.post("/api/leads", headers=ORIGIN, json=payload).json()["id"]
        login(client)
        unavailable = client.post(f"/api/leads/{lead_id}/extraction/retry", headers=ORIGIN, json={})
        assert unavailable.status_code == 409
        assert unavailable.json() == {"detail": "Extraction provider is not configured"}

        configured = Settings(
            ai_enabled=True,
            yandex_api_key="test-key",
            yandex_model_uri="gpt://folder/yandexgpt-5.1",
        )
        app.dependency_overrides[get_settings] = lambda: configured
        try:
            queued = client.post(f"/api/leads/{lead_id}/extraction/retry", headers=ORIGIN, json={})
            assert queued.status_code == 202
            assert queued.json()["status"] == "pending"
        finally:
            app.dependency_overrides.pop(get_settings, None)


def _notification_settings(**overrides) -> Settings:
    values = {
        "notifications_enabled": True,
        "telegram_bot_token": "123:test-token",
        "telegram_chat_id": "-100123",
        "notifications_service_token": "service-secret",
        "notification_reminder_minutes": 30,
    }
    values.update(overrides)
    return Settings(**values)


class FakeTelegram:
    def __init__(self, outcome: DeliveryOutcome | None = None) -> None:
        self.outcome = outcome or DeliveryOutcome(DeliveryDisposition.SENT, message_id=42)
        self.calls = 0
        self.messages: list[str] = []
        self._lock = threading.Lock()

    def send(self, claim):
        with self._lock:
            self.calls += 1
            self.messages.append(claim.text)
        return self.outcome


def _submit_notification_lead(client: TestClient, submission_id: uuid.UUID | None = None) -> dict:
    return client.post(
        "/api/leads",
        headers=ORIGIN,
        json={
            "submission_id": str(submission_id or uuid.uuid4()),
            "name": "Telegram Client <admin>",
            "phone": "+7 900 111-22-33",
            "description": "Нужна диагностика <b>срочно</b> и ремонт.",
        },
    ).json()


def test_notification_enqueue_is_idempotent_and_concurrent_dispatch_claims_once() -> None:
    settings = _notification_settings()
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        submission_id = uuid.uuid4()
        with TestClient(app) as client:
            first = _submit_notification_lead(client, submission_id)
            replay = _submit_notification_lead(client, submission_id)
            assert replay == first
        with SessionLocal() as db:
            notifications = list(
                db.scalars(
                    select(LeadNotification)
                    .where(LeadNotification.lead_id == uuid.UUID(first["id"]))
                    .order_by(LeadNotification.kind)
                )
            )
            assert len(notifications) == 2
            assert {item.kind for item in notifications} == {
                NotificationKind.NEW_LEAD,
                NotificationKind.REMINDER,
            }

        telegram = FakeTelegram()

        def dispatch_once() -> dict:
            with SessionLocal() as db:
                return dispatch_notifications(
                    db, NotificationKind.NEW_LEAD, 20, settings, telegram
                )

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: dispatch_once(), range(2)))

        assert sum(int(result["claimed"]) for result in results) == 1
        assert sum(int(result["sent"]) for result in results) == 1
        assert telegram.calls == 1
        assert "<b>срочно</b>" in telegram.messages[0]
        with SessionLocal() as db:
            sent = db.scalar(
                select(LeadNotification).where(
                    LeadNotification.lead_id == uuid.UUID(first["id"]),
                    LeadNotification.kind == NotificationKind.NEW_LEAD,
                )
            )
            assert sent is not None
            assert sent.status == NotificationStatus.SENT
            assert sent.message_id == 42
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_reminder_uses_creation_time_requires_initial_delivery_and_is_cancelled_forever() -> None:
    settings = _notification_settings(notification_reminder_minutes=30)
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            created = _submit_notification_lead(client)
            lead_id = uuid.UUID(created["id"])
            created_at = datetime.fromisoformat(created["created_at"])

            with SessionLocal() as db:
                assert (
                    claim_next_notification(
                        db,
                        NotificationKind.REMINDER,
                        settings,
                        created_at + timedelta(minutes=30),
                    )
                    is None
                )
            with SessionLocal() as db:
                initial = claim_next_notification(
                    db, NotificationKind.NEW_LEAD, settings, created_at
                )
                assert initial is not None
                assert finish_notification(
                    db,
                    initial,
                    DeliveryOutcome(DeliveryDisposition.SENT, message_id=7),
                    settings,
                    created_at,
                ) == DeliveryDisposition.SENT
            with SessionLocal() as db:
                assert (
                    claim_next_notification(
                        db,
                        NotificationKind.REMINDER,
                        settings,
                        created_at + timedelta(minutes=30) - timedelta(microseconds=1),
                    )
                    is None
                )

            login(client)
            changed = client.patch(
                f"/api/leads/{lead_id}", headers=ORIGIN, json={"status": "in_progress"}
            )
            assert changed.status_code == 200
            reopened = client.patch(
                f"/api/leads/{lead_id}", headers=ORIGIN, json={"status": "new"}
            )
            assert reopened.status_code == 200

        with SessionLocal() as db:
            reminder = db.scalar(
                select(LeadNotification).where(
                    LeadNotification.lead_id == lead_id,
                    LeadNotification.kind == NotificationKind.REMINDER,
                )
            )
            assert reminder is not None
            assert reminder.status == NotificationStatus.CANCELLED
            assert (
                claim_next_notification(
                    db,
                    NotificationKind.REMINDER,
                    settings,
                    created_at + timedelta(days=1),
                )
                is None
            )
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_notification_retries_are_bounded_and_stale_sending_is_unknown() -> None:
    settings = _notification_settings(
        notification_max_attempts=2,
        notification_retry_cap_seconds=20,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            created = _submit_notification_lead(client)
        lead_id = uuid.UUID(created["id"])
        now = datetime.fromisoformat(created["created_at"])
        with SessionLocal() as db:
            first = claim_next_notification(db, NotificationKind.NEW_LEAD, settings, now)
            assert first is not None
            assert finish_notification(
                db,
                first,
                DeliveryOutcome(
                    DeliveryDisposition.RETRY,
                    error_code="telegram_rate_limited",
                    retry_after_seconds=999,
                ),
                settings,
                now,
            ) == DeliveryDisposition.RETRY
        with SessionLocal() as db:
            queued = db.scalar(
                select(LeadNotification).where(
                    LeadNotification.lead_id == lead_id,
                    LeadNotification.kind == NotificationKind.NEW_LEAD,
                )
            )
            assert queued is not None
            assert queued.status == NotificationStatus.RETRY
            assert queued.available_at == now + timedelta(seconds=20)
        with SessionLocal() as db:
            second = claim_next_notification(
                db, NotificationKind.NEW_LEAD, settings, now + timedelta(seconds=20)
            )
            assert second is not None
            assert finish_notification(
                db,
                second,
                DeliveryOutcome(
                    DeliveryDisposition.RETRY,
                    error_code="telegram_connect_failed",
                ),
                settings,
                now + timedelta(seconds=20),
            ) == DeliveryDisposition.FAILED
        with SessionLocal() as db:
            exhausted = db.scalar(
                select(LeadNotification).where(
                    LeadNotification.lead_id == lead_id,
                    LeadNotification.kind == NotificationKind.NEW_LEAD,
                )
            )
            assert exhausted is not None
            assert exhausted.status == NotificationStatus.FAILED
            assert exhausted.error_code == "telegram_retry_exhausted"

            reminder = db.scalar(
                select(LeadNotification).where(
                    LeadNotification.lead_id == lead_id,
                    LeadNotification.kind == NotificationKind.REMINDER,
                )
            )
            assert reminder is not None
            reminder.status = NotificationStatus.SENDING
            reminder.claim_token = uuid.uuid4()
            reminder.lease_expires_at = now - timedelta(seconds=1)
            db.commit()
            assert recover_stale_sending(db, NotificationKind.REMINDER, now) == 1
            db.refresh(reminder)
            assert reminder.status == NotificationStatus.DELIVERY_UNKNOWN
            assert reminder.error_code == "stale_delivery_unknown"
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_status_change_fences_claimed_reminder_before_transport() -> None:
    settings = _notification_settings(notification_reminder_minutes=1)
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            created = _submit_notification_lead(client)
            lead_id = uuid.UUID(created["id"])
            created_at = datetime.fromisoformat(created["created_at"])
            with SessionLocal() as db:
                initial = claim_next_notification(
                    db, NotificationKind.NEW_LEAD, settings, created_at
                )
                assert initial is not None
                finish_notification(
                    db,
                    initial,
                    DeliveryOutcome(DeliveryDisposition.SENT, message_id=8),
                    settings,
                    created_at,
                )
            with SessionLocal() as db:
                reminder_claim = claim_next_notification(
                    db,
                    NotificationKind.REMINDER,
                    settings,
                    created_at + timedelta(minutes=1),
                )
                assert reminder_claim is not None

            login(client)
            changed = client.patch(
                f"/api/leads/{lead_id}", headers=ORIGIN, json={"status": "in_progress"}
            )
            assert changed.status_code == 200

        with SessionLocal() as db:
            assert not claim_still_eligible(db, reminder_claim)
            reminder = db.scalar(
                select(LeadNotification).where(
                    LeadNotification.lead_id == lead_id,
                    LeadNotification.kind == NotificationKind.REMINDER,
                )
            )
            assert reminder is not None
            assert reminder.status == NotificationStatus.DELIVERY_UNKNOWN
            assert reminder.error_code == "status_changed_during_delivery"
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_permanent_and_ambiguous_delivery_outcomes_are_terminal() -> None:
    settings = _notification_settings()
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            failed_lead = _submit_notification_lead(client)
            with SessionLocal() as db:
                claim = claim_next_notification(
                    db, NotificationKind.NEW_LEAD, settings
                )
                assert claim is not None
                failed = DeliveryOutcome(
                    DeliveryDisposition.FAILED,
                    error_code="telegram_auth_or_access",
                )
                assert finish_notification(db, claim, failed, settings) == failed.disposition
            unknown_lead = _submit_notification_lead(client)
            with SessionLocal() as db:
                claim = claim_next_notification(
                    db, NotificationKind.NEW_LEAD, settings
                )
                assert claim is not None
                unknown = DeliveryOutcome(
                    DeliveryDisposition.DELIVERY_UNKNOWN,
                    error_code="telegram_delivery_unknown",
                )
                assert finish_notification(db, claim, unknown, settings) == unknown.disposition

        with SessionLocal() as db:
            failed_stored = db.scalar(
                select(LeadNotification).where(
                    LeadNotification.lead_id == uuid.UUID(failed_lead["id"]),
                    LeadNotification.kind == NotificationKind.NEW_LEAD,
                )
            )
            unknown_stored = db.scalar(
                    select(LeadNotification).where(
                        LeadNotification.lead_id == uuid.UUID(unknown_lead["id"]),
                        LeadNotification.kind == NotificationKind.NEW_LEAD,
                    )
                )
            assert failed_stored is not None
            assert failed_stored.status == NotificationStatus.FAILED
            assert failed_stored.error_code == "telegram_auth_or_access"
            assert unknown_stored is not None
            assert unknown_stored.status == NotificationStatus.DELIVERY_UNKNOWN
            assert unknown_stored.error_code == "telegram_delivery_unknown"
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_internal_dispatch_uses_only_service_bearer_and_returns_counts() -> None:
    settings = _notification_settings()
    telegram = FakeTelegram()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_telegram_client] = lambda: telegram
    try:
        with TestClient(app) as client:
            assert (
                client.post(
                    "/api/internal/notifications/dispatch",
                    json={"kind": "new_lead", "limit": 20},
                ).status_code
                == 401
            )
            assert (
                client.post(
                    "/api/internal/notifications/dispatch",
                    headers={"Authorization": "Bearer wrong"},
                    json={"kind": "new_lead", "limit": 20},
                ).status_code
                == 401
            )
            response = client.post(
                "/api/internal/notifications/dispatch",
                headers={"Authorization": "Bearer service-secret"},
                json={"kind": "new_lead", "limit": 20},
            )
            assert response.status_code == 200
            assert response.json() == {
                "kind": "new_lead",
                "claimed": 0,
                "sent": 0,
                "retried": 0,
                "failed": 0,
                "delivery_unknown": 0,
                "skipped": 0,
            }
    finally:
        app.dependency_overrides.pop(get_telegram_client, None)
        app.dependency_overrides.pop(get_settings, None)


def test_internal_dispatch_reports_disabled_configuration_without_network() -> None:
    settings = _notification_settings(notifications_enabled=False)
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/internal/notifications/dispatch",
                headers={"Authorization": "Bearer service-secret"},
                json={"kind": "new_lead"},
            )
            assert response.status_code == 503
            assert response.json() == {"detail": "Notifications are not configured"}
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_demo_seed_is_idempotent_scoped_and_preserves_unrelated_rows() -> None:
    now = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
    unrelated_id = uuid.uuid4()
    with SessionLocal() as db:
        unrelated = Lead(
            id=unrelated_id,
            submission_id=uuid.uuid4(),
            payload_fingerprint="f" * 64,
            name="Unrelated user row",
            phone="+7 900 000-00-99",
            description="Must survive demo reset.",
            status=LeadStatus.NEW,
        )
        unrelated.extraction = LeadExtraction(
            status=ExtractionStatus.NOT_CONFIGURED,
            error_code="not_configured",
        )
        db.add(unrelated)
        db.commit()

    with SessionLocal() as db:
        first = seed_demo_data(db, now)
    assert first.created == 6
    assert first.existing == 0

    ids = demo_lead_ids()
    with SessionLocal() as db:
        leads = list(db.scalars(select(Lead).where(Lead.id.in_(ids))))
        assert len(leads) == 6
        assert all(lead.name.startswith("Демо · ") for lead in leads)
        assert all(lead.phone.startswith("+7 000 ") for lead in leads)
        assert {lead.status for lead in leads} == {
            LeadStatus.NEW,
            LeadStatus.IN_PROGRESS,
            LeadStatus.WON,
            LeadStatus.LOST,
        }
        extractions = list(
            db.scalars(select(LeadExtraction).where(LeadExtraction.lead_id.in_(ids)))
        )
        assert len(extractions) == 6
        assert sum(item.manually_edited for item in extractions) == 4
        assert {
            item.status for item in extractions if not item.manually_edited
        } == {ExtractionStatus.NOT_CONFIGURED}
        assert all(
            item.status == ExtractionStatus.SUCCEEDED
            for item in extractions
            if item.manually_edited
        )
        leads_by_id = {lead.id: lead for lead in leads}
        for item in extractions:
            if not item.manually_edited:
                continue
            description = leads_by_id[item.lead_id].description
            assert item.evidence_service in description
            assert item.evidence_budget in description
            assert item.evidence_timeframe in description
        histories = list(db.scalars(select(LeadHistory).where(LeadHistory.lead_id.in_(ids))))
        assert len(histories) == 11
        assert any(item.type == "status_changed" for item in histories)
        assert list(
            db.scalars(select(LeadNotification).where(LeadNotification.lead_id.in_(ids)))
        ) == []

        changed = db.get(Lead, ids[0])
        assert changed is not None
        changed.status = LeadStatus.WON
        db.commit()

    with SessionLocal() as db:
        repeated = seed_demo_data(db, now + timedelta(days=1))
        preserved = db.get(Lead, ids[0])
        assert preserved is not None
        assert preserved.status == LeadStatus.WON
    assert repeated.created == 0
    assert repeated.existing == 6

    with SessionLocal() as db:
        deleted = reset_demo_data(db)
    assert deleted == 6
    with SessionLocal() as db:
        assert db.get(Lead, unrelated_id) is not None
        assert list(db.scalars(select(Lead).where(Lead.id.in_(ids)))) == []


def test_demo_seed_and_reset_abort_on_reserved_uuid_collision() -> None:
    spec = DEMO_LEADS[0]
    with SessionLocal() as db:
        db.add(
            Lead(
                id=spec.lead_id,
                submission_id=uuid.uuid4(),
                payload_fingerprint="c" * 64,
                name="Unrelated collision",
                phone="+7 900 000-00-98",
                description="Must not be overwritten or deleted.",
                status=LeadStatus.NEW,
            )
        )
        db.commit()

    with SessionLocal() as db, pytest.raises(DemoDataCollision):
        seed_demo_data(db)
    with SessionLocal() as db, pytest.raises(DemoDataCollision):
        reset_demo_data(db)
    with SessionLocal() as db:
        collision = db.get(Lead, spec.lead_id)
        assert collision is not None
        assert collision.name == "Unrelated collision"
