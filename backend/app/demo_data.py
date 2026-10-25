import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from .models import ExtractionStatus, Lead, LeadExtraction, LeadHistory, LeadStatus

DEMO_NAMESPACE = uuid.UUID("6f58ed2a-8f79-4cb9-9938-d10f73a8b614")
DEMO_ADVISORY_LOCK_KEY = 0x4C4644454D4F0001


@dataclass(frozen=True)
class ManualExtraction:
    service: str
    budget_min: Decimal | None
    budget_max: Decimal | None
    budget_currency: str | None
    budget_text: str | None
    timeframe: str | None
    evidence_service: str | None
    evidence_budget: str | None
    evidence_timeframe: str | None


@dataclass(frozen=True)
class DemoLeadSpec:
    slug: str
    name: str
    phone: str
    description: str
    status: LeadStatus
    age: timedelta
    transitions: tuple[tuple[LeadStatus, timedelta], ...] = ()
    extraction: ManualExtraction | None = None

    @property
    def lead_id(self) -> uuid.UUID:
        return uuid.uuid5(DEMO_NAMESPACE, f"lead:{self.slug}")

    @property
    def submission_id(self) -> uuid.UUID:
        return uuid.uuid5(DEMO_NAMESPACE, f"submission:{self.slug}")

    @property
    def marker(self) -> str:
        return hashlib.sha256(f"leadflow-demo:v1:{self.slug}".encode()).hexdigest()


@dataclass(frozen=True)
class DemoSeedResult:
    created: int
    existing: int


class DemoDataCollision(RuntimeError):
    pass


DEMO_LEADS = (
    DemoLeadSpec(
        slug="kitchen-faucet",
        name="Демо · Анна, кухня",
        phone="+7 000 000-00-01",
        description=(
            "Нужно заменить смеситель на кухне и устранить течь. "
            "Бюджет до 12 000 рублей, желательно на этой неделе."
        ),
        status=LeadStatus.NEW,
        age=timedelta(minutes=8),
        extraction=ManualExtraction(
            service="Замена смесителя",
            budget_min=None,
            budget_max=Decimal("12000.00"),
            budget_currency="RUB",
            budget_text="до 12 000 рублей",
            timeframe="на этой неделе",
            evidence_service="заменить смеситель на кухне",
            evidence_budget="до 12 000 рублей",
            evidence_timeframe="на этой неделе",
        ),
    ),
    DemoLeadSpec(
        slug="electrical-outlets",
        name="Демо · Илья, электрика",
        phone="+7 000 000-00-02",
        description=(
            "Требуется перенести три розетки в гостиной. "
            "Бюджет 25 000–35 000 рублей, работы в течение двух недель."
        ),
        status=LeadStatus.IN_PROGRESS,
        age=timedelta(minutes=42),
        transitions=((LeadStatus.IN_PROGRESS, timedelta(minutes=12)),),
        extraction=ManualExtraction(
            service="Перенос розеток",
            budget_min=Decimal("25000.00"),
            budget_max=Decimal("35000.00"),
            budget_currency="RUB",
            budget_text="25 000–35 000 рублей",
            timeframe="в течение двух недель",
            evidence_service="перенести три розетки",
            evidence_budget="25 000–35 000 рублей",
            evidence_timeframe="в течение двух недель",
        ),
    ),
    DemoLeadSpec(
        slug="window-adjustment",
        name="Демо · Марина, окна",
        phone="+7 000 000-00-03",
        description=(
            "Из двух пластиковых окон дует, нужна регулировка и замена уплотнителя. "
            "Срок и бюджет пока не определены."
        ),
        status=LeadStatus.NEW,
        age=timedelta(hours=1, minutes=20),
    ),
    DemoLeadSpec(
        slug="apartment-finish",
        name="Демо · Семья, отделка",
        phone="+7 000 000-00-04",
        description=(
            "Нужна черновая отделка квартиры 62 м². "
            "Ориентир по бюджету 650 000 рублей, начать в следующем месяце."
        ),
        status=LeadStatus.IN_PROGRESS,
        age=timedelta(hours=4),
        transitions=((LeadStatus.IN_PROGRESS, timedelta(minutes=35)),),
        extraction=ManualExtraction(
            service="Черновая отделка квартиры",
            budget_min=Decimal("650000.00"),
            budget_max=Decimal("650000.00"),
            budget_currency="RUB",
            budget_text="650 000 рублей",
            timeframe="в следующем месяце",
            evidence_service="черновая отделка квартиры 62 м²",
            evidence_budget="650 000 рублей",
            evidence_timeframe="в следующем месяце",
        ),
    ),
    DemoLeadSpec(
        slug="bathroom-tile",
        name="Демо · Ольга, ванная",
        phone="+7 000 000-00-05",
        description=(
            "Нужно уложить плитку в ванной комнате площадью 18 м². "
            "Бюджет 180 000 рублей, завершить за три недели."
        ),
        status=LeadStatus.WON,
        age=timedelta(days=1, hours=3),
        transitions=(
            (LeadStatus.IN_PROGRESS, timedelta(hours=2)),
            (LeadStatus.WON, timedelta(hours=20)),
        ),
        extraction=ManualExtraction(
            service="Укладка плитки в ванной",
            budget_min=Decimal("180000.00"),
            budget_max=Decimal("180000.00"),
            budget_currency="RUB",
            budget_text="180 000 рублей",
            timeframe="за три недели",
            evidence_service="уложить плитку в ванной комнате",
            evidence_budget="180 000 рублей",
            evidence_timeframe="за три недели",
        ),
    ),
    DemoLeadSpec(
        slug="air-conditioner",
        name="Демо · Павел, кондиционер",
        phone="+7 000 000-00-06",
        description=(
            "Кондиционер шумит и перестал охлаждать. Нужна диагностика, "
            "но клиент отложил ремонт."
        ),
        status=LeadStatus.LOST,
        age=timedelta(days=2, hours=2),
        transitions=((LeadStatus.LOST, timedelta(hours=6)),),
    ),
)


STATUS_LABELS = {
    LeadStatus.NEW: "новая",
    LeadStatus.IN_PROGRESS: "в работе",
    LeadStatus.WON: "завершена",
    LeadStatus.LOST: "отказ",
}


def demo_lead_ids() -> tuple[uuid.UUID, ...]:
    return tuple(spec.lead_id for spec in DEMO_LEADS)


def _lock(db: Session) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": DEMO_ADVISORY_LOCK_KEY})


def _matching_spec(lead: Lead) -> DemoLeadSpec | None:
    for spec in DEMO_LEADS:
        if (
            lead.id == spec.lead_id
            and lead.submission_id == spec.submission_id
            and lead.payload_fingerprint == spec.marker
        ):
            return spec
    return None


def _assert_no_collisions(db: Session) -> dict[uuid.UUID, Lead]:
    lead_ids = demo_lead_ids()
    submission_ids = tuple(spec.submission_id for spec in DEMO_LEADS)
    found = list(
        db.scalars(
            select(Lead).where(
                or_(Lead.id.in_(lead_ids), Lead.submission_id.in_(submission_ids))
            )
        )
    )
    owned: dict[uuid.UUID, Lead] = {}
    for lead in found:
        spec = _matching_spec(lead)
        if spec is None:
            raise DemoDataCollision(
                "A reserved demo UUID is already used by a non-demo record; no changes made"
            )
        owned[spec.lead_id] = lead
    return owned


def _history_for(spec: DemoLeadSpec, created_at: datetime) -> list[LeadHistory]:
    history = [
        LeadHistory(
            id=uuid.uuid5(DEMO_NAMESPACE, f"history:{spec.slug}:created"),
            type="created",
            message="Заявка создана (демо)",
            created_at=created_at,
        )
    ]
    previous = LeadStatus.NEW
    for index, (current, elapsed) in enumerate(spec.transitions, start=1):
        history.append(
            LeadHistory(
                id=uuid.uuid5(DEMO_NAMESPACE, f"history:{spec.slug}:status:{index}"),
                type="status_changed",
                message=(
                    f"Статус изменён: {STATUS_LABELS[previous]} → {STATUS_LABELS[current]}"
                ),
                created_at=created_at + elapsed,
            )
        )
        previous = current
    return history


def _extraction_for(spec: DemoLeadSpec, created_at: datetime) -> LeadExtraction:
    manual = spec.extraction
    if manual is None:
        return LeadExtraction(
            status=ExtractionStatus.NOT_CONFIGURED,
            error_code="not_configured",
            manually_edited=False,
            revision=0,
            created_at=created_at,
            updated_at=created_at,
        )
    completed_at = created_at + timedelta(minutes=4)
    return LeadExtraction(
        status=ExtractionStatus.SUCCEEDED,
        service=manual.service,
        budget_min=manual.budget_min,
        budget_max=manual.budget_max,
        budget_currency=manual.budget_currency,
        budget_text=manual.budget_text,
        timeframe=manual.timeframe,
        evidence_service=manual.evidence_service,
        evidence_budget=manual.evidence_budget,
        evidence_timeframe=manual.evidence_timeframe,
        error_code=None,
        attempts=0,
        manually_edited=True,
        revision=1,
        created_at=created_at,
        updated_at=completed_at,
        completed_at=completed_at,
    )


def _new_lead(spec: DemoLeadSpec, now: datetime) -> Lead:
    created_at = now - spec.age
    updated_at = (
        created_at + spec.transitions[-1][1] if spec.transitions else created_at
    )
    lead = Lead(
        id=spec.lead_id,
        submission_id=spec.submission_id,
        payload_fingerprint=spec.marker,
        name=spec.name,
        phone=spec.phone,
        description=spec.description,
        status=spec.status,
        created_at=created_at,
        updated_at=updated_at,
    )
    lead.history = _history_for(spec, created_at)
    lead.extraction = _extraction_for(spec, created_at)
    return lead


def seed_demo_data(db: Session, now: datetime | None = None) -> DemoSeedResult:
    now = now or datetime.now(UTC)
    try:
        _lock(db)
        existing = _assert_no_collisions(db)
        missing = [spec for spec in DEMO_LEADS if spec.lead_id not in existing]
        db.add_all(_new_lead(spec, now) for spec in missing)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return DemoSeedResult(created=len(missing), existing=len(existing))


def reset_demo_data(db: Session) -> int:
    try:
        _lock(db)
        existing = _assert_no_collisions(db)
        for lead in existing.values():
            db.delete(lead)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return len(existing)
