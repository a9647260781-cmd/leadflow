import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from .config import Settings
from .extraction import ExtractionResult, ProviderError, YandexExtractionClient
from .models import ExtractionStatus, Lead, LeadExtraction


@dataclass(frozen=True)
class ExtractionClaim:
    lead_id: uuid.UUID
    description: str
    claim_token: uuid.UUID
    revision: int
    attempts: int


def mark_unconfigured_jobs(db: Session) -> int:
    """Terminalize only unfinished automatic jobs when provider credentials are absent."""
    now = datetime.now(UTC)
    outcome = db.execute(
        update(LeadExtraction)
        .where(
            LeadExtraction.status.in_([ExtractionStatus.PENDING, ExtractionStatus.PROCESSING]),
        )
        .values(
            status=ExtractionStatus.NOT_CONFIGURED,
            error_code="not_configured",
            available_at=None,
            claim_token=None,
            claimed_at=None,
            lease_expires_at=None,
            completed_at=now,
            revision=LeadExtraction.revision + 1,
            updated_at=now,
        )
    )
    db.commit()
    return outcome.rowcount


def claim_next(db: Session, settings: Settings) -> ExtractionClaim | None:
    now = datetime.now(UTC)
    db.execute(
        update(LeadExtraction)
        .where(
            LeadExtraction.status.in_([ExtractionStatus.PENDING, ExtractionStatus.PROCESSING]),
            LeadExtraction.attempts >= settings.extraction_max_attempts,
            or_(
                LeadExtraction.status == ExtractionStatus.PENDING,
                LeadExtraction.lease_expires_at <= now,
            ),
        )
        .values(
            status=ExtractionStatus.FAILED,
            error_code="attempts_exhausted",
            completed_at=now,
            claim_token=None,
            lease_expires_at=None,
            updated_at=now,
        )
    )
    candidate = db.execute(
        select(LeadExtraction, Lead.description)
        .join(Lead, Lead.id == LeadExtraction.lead_id)
        .where(
            LeadExtraction.attempts < settings.extraction_max_attempts,
            or_(
                and_(
                    LeadExtraction.status == ExtractionStatus.PENDING,
                    or_(
                        LeadExtraction.available_at.is_(None),
                        LeadExtraction.available_at <= now,
                    ),
                ),
                and_(
                    LeadExtraction.status == ExtractionStatus.PROCESSING,
                    LeadExtraction.lease_expires_at <= now,
                ),
            ),
        )
        .order_by(LeadExtraction.available_at.asc().nullsfirst(), LeadExtraction.lead_id)
        .with_for_update(of=LeadExtraction, skip_locked=True)
        .limit(1)
    ).first()
    if candidate is None:
        db.commit()
        return None

    extraction, description = candidate
    token = uuid.uuid4()
    extraction.status = ExtractionStatus.PROCESSING
    extraction.claim_token = token
    extraction.claimed_at = now
    extraction.lease_expires_at = now + timedelta(seconds=settings.extraction_lease_seconds)
    extraction.attempts += 1
    extraction.error_code = None
    extraction.updated_at = now
    claim = ExtractionClaim(
        lead_id=extraction.lead_id,
        description=description,
        claim_token=token,
        revision=extraction.revision,
        attempts=extraction.attempts,
    )
    db.commit()
    return claim


def complete_claim(db: Session, claim: ExtractionClaim, result: ExtractionResult) -> bool:
    now = datetime.now(UTC)
    outcome = db.execute(
        update(LeadExtraction)
        .where(
            LeadExtraction.lead_id == claim.lead_id,
            LeadExtraction.claim_token == claim.claim_token,
            LeadExtraction.revision == claim.revision,
            LeadExtraction.status == ExtractionStatus.PROCESSING,
        )
        .values(
            status=ExtractionStatus.SUCCEEDED,
            service=result.service,
            budget_min=result.budget_min,
            budget_max=result.budget_max,
            budget_currency=result.budget_currency,
            budget_text=result.budget_text,
            timeframe=result.timeframe,
            evidence_service=result.evidence.service,
            evidence_budget=result.evidence.budget,
            evidence_timeframe=result.evidence.timeframe,
            error_code=None,
            available_at=None,
            claim_token=None,
            claimed_at=None,
            lease_expires_at=None,
            completed_at=now,
            manually_edited=False,
            revision=claim.revision + 1,
            updated_at=now,
        )
    )
    db.commit()
    return outcome.rowcount == 1


def fail_claim(
    db: Session,
    claim: ExtractionClaim,
    error: ProviderError,
    settings: Settings,
) -> bool:
    now = datetime.now(UTC)
    retry = error.retryable and claim.attempts < settings.extraction_max_attempts
    available_at = None
    if retry:
        delay = settings.extraction_retry_base_seconds * (2 ** (claim.attempts - 1))
        available_at = now + timedelta(seconds=delay)
    outcome = db.execute(
        update(LeadExtraction)
        .where(
            LeadExtraction.lead_id == claim.lead_id,
            LeadExtraction.claim_token == claim.claim_token,
            LeadExtraction.revision == claim.revision,
            LeadExtraction.status == ExtractionStatus.PROCESSING,
        )
        .values(
            status=ExtractionStatus.PENDING if retry else ExtractionStatus.FAILED,
            error_code=error.code,
            available_at=available_at,
            claim_token=None,
            claimed_at=None,
            lease_expires_at=None,
            completed_at=None if retry else now,
            updated_at=now,
        )
    )
    db.commit()
    return outcome.rowcount == 1


def process_one(db: Session, client: YandexExtractionClient, settings: Settings) -> bool:
    claim = claim_next(db, settings)
    if claim is None:
        return False
    try:
        result = client.extract(claim.description)
    except ProviderError as error:
        fail_claim(db, claim, error, settings)
    else:
        complete_claim(db, claim, result)
    return True
