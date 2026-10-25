import hashlib
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, selectinload

from ..config import Settings, get_settings
from ..database import get_db
from ..dependencies import enforce_rate_limit, get_current_manager
from ..models import ExtractionStatus, Lead, LeadExtraction, LeadHistory, LeadStatus, Manager
from ..notifications import cancel_reminder, enqueue_lead_notifications
from ..schemas import (
    ExtractionResponse,
    ExtractionRetryRequest,
    ExtractionWrite,
    LeadCreate,
    LeadCreatedResponse,
    LeadDetail,
    LeadListResponse,
    LeadStatusUpdate,
)

router = APIRouter(prefix="/leads", tags=["leads"])


def _fingerprint(payload: LeadCreate) -> str:
    canonical = json.dumps(
        payload.model_dump(mode="json", exclude={"submission_id"}),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _load_lead(db: Session, lead_id: uuid.UUID) -> Lead:
    lead = db.scalar(
        select(Lead)
        .options(selectinload(Lead.history), selectinload(Lead.extraction))
        .where(Lead.id == lead_id)
    )
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return lead


@router.post("", response_model=LeadCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_lead(
    payload: LeadCreate,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> LeadCreatedResponse:
    enforce_rate_limit(request, "lead", settings.public_lead_rate_limit)
    fingerprint = _fingerprint(payload)
    statement = (
        pg_insert(Lead)
        .values(
            id=uuid.uuid4(),
            submission_id=payload.submission_id,
            payload_fingerprint=fingerprint,
            name=payload.name,
            phone=payload.phone,
            description=payload.description,
            status=LeadStatus.NEW,
        )
        .on_conflict_do_nothing(index_elements=[Lead.submission_id])
        .returning(Lead.id, Lead.created_at)
    )
    inserted = db.execute(statement).first()
    if inserted is not None:
        db.add(LeadHistory(lead_id=inserted.id, type="created", message="Lead submitted"))
        configured = settings.ai_configured
        db.add(
            LeadExtraction(
                lead_id=inserted.id,
                status=(
                    ExtractionStatus.PENDING if configured else ExtractionStatus.NOT_CONFIGURED
                ),
                available_at=datetime.now(UTC) if configured else None,
                error_code=None if configured else "not_configured",
            )
        )
        enqueue_lead_notifications(db, inserted.id, inserted.created_at, settings)
        db.commit()
        return LeadCreatedResponse(id=inserted.id, created_at=inserted.created_at)

    existing = db.scalar(select(Lead).where(Lead.submission_id == payload.submission_id))
    if existing is None:
        raise HTTPException(status_code=409, detail="Submission conflict")
    if existing.payload_fingerprint != fingerprint:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Submission ID was already used with different data",
        )
    response.status_code = status.HTTP_200_OK
    return LeadCreatedResponse(id=existing.id, created_at=existing.created_at)


@router.get("", response_model=LeadListResponse)
def list_leads(
    search: str | None = Query(default=None, max_length=200),
    lead_status: LeadStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _manager: Manager = Depends(get_current_manager),
    db: Session = Depends(get_db),
) -> LeadListResponse:
    filters = []
    if search and search.strip():
        pattern = f"%{_escape_like(search.strip())}%"
        filters.append(
            or_(
                Lead.name.ilike(pattern, escape="\\"),
                Lead.phone.ilike(pattern, escape="\\"),
                Lead.description.ilike(pattern, escape="\\"),
            )
        )
    if lead_status is not None:
        filters.append(Lead.status == lead_status)

    total = db.scalar(select(func.count()).select_from(Lead).where(*filters)) or 0
    items = list(
        db.scalars(
            select(Lead)
            .where(*filters)
            .order_by(Lead.created_at.desc(), Lead.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return LeadListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{lead_id}", response_model=LeadDetail)
def get_lead(
    lead_id: uuid.UUID,
    _manager: Manager = Depends(get_current_manager),
    db: Session = Depends(get_db),
) -> Lead:
    return _load_lead(db, lead_id)


@router.patch("/{lead_id}", response_model=LeadDetail)
def update_lead_status(
    lead_id: uuid.UUID,
    payload: LeadStatusUpdate,
    _manager: Manager = Depends(get_current_manager),
    db: Session = Depends(get_db),
) -> Lead:
    lead = db.scalar(select(Lead).where(Lead.id == lead_id).with_for_update())
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    if lead.status != payload.status:
        previous = lead.status
        lead.status = payload.status
        db.add(
            LeadHistory(
                lead_id=lead.id,
                type="status_changed",
                message=f"Status changed from {previous.value} to {payload.status.value}",
            )
        )
        if payload.status != LeadStatus.NEW:
            cancel_reminder(db, lead.id)
        db.commit()
    return _load_lead(db, lead.id)


def _get_extraction_for_update(db: Session, lead_id: uuid.UUID) -> tuple[Lead, LeadExtraction]:
    lead = db.scalar(select(Lead).where(Lead.id == lead_id).with_for_update())
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    extraction = db.scalar(
        select(LeadExtraction).where(LeadExtraction.lead_id == lead_id).with_for_update()
    )
    if extraction is None:
        extraction = LeadExtraction(lead_id=lead_id, status=ExtractionStatus.NOT_REQUESTED)
        db.add(extraction)
        db.flush()
    return lead, extraction


def _validate_manual_evidence(payload: ExtractionWrite, description: str) -> None:
    quotes = (
        payload.evidence.service,
        payload.evidence.budget,
        payload.evidence.timeframe,
    )
    if any(quote is not None and (not quote or quote not in description) for quote in quotes):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Evidence must be an exact substring of the lead description",
        )


@router.patch("/{lead_id}/extraction", response_model=ExtractionResponse)
def update_extraction(
    lead_id: uuid.UUID,
    payload: ExtractionWrite,
    _manager: Manager = Depends(get_current_manager),
    db: Session = Depends(get_db),
) -> LeadExtraction:
    lead, extraction = _get_extraction_for_update(db, lead_id)
    if extraction.revision != payload.expected_revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Extraction was changed; reload before saving",
        )
    _validate_manual_evidence(payload, lead.description)
    now = datetime.now(UTC)
    extraction.service = payload.service
    extraction.budget_min = (
        Decimal(str(payload.budget_min)) if payload.budget_min is not None else None
    )
    extraction.budget_max = (
        Decimal(str(payload.budget_max)) if payload.budget_max is not None else None
    )
    extraction.budget_currency = payload.budget_currency
    extraction.budget_text = payload.budget_text
    extraction.timeframe = payload.timeframe
    extraction.evidence_service = payload.evidence.service
    extraction.evidence_budget = payload.evidence.budget
    extraction.evidence_timeframe = payload.evidence.timeframe
    extraction.status = ExtractionStatus.SUCCEEDED
    extraction.error_code = None
    extraction.available_at = None
    extraction.claimed_at = None
    extraction.lease_expires_at = None
    extraction.claim_token = None
    extraction.manually_edited = True
    extraction.revision += 1
    extraction.completed_at = now
    extraction.updated_at = now
    db.commit()
    db.refresh(extraction)
    return extraction


@router.post("/{lead_id}/extraction/retry", response_model=ExtractionResponse)
def retry_extraction(
    lead_id: uuid.UUID,
    response: Response,
    request: Request,
    payload: ExtractionRetryRequest | None = None,
    _manager: Manager = Depends(get_current_manager),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> LeadExtraction:
    enforce_rate_limit(request, f"extraction-retry:{lead_id}", settings.extraction_retry_rate_limit)
    _, extraction = _get_extraction_for_update(db, lead_id)
    if extraction.status in {ExtractionStatus.PENDING, ExtractionStatus.PROCESSING}:
        response.status_code = status.HTTP_200_OK
        db.commit()
        return extraction
    if not settings.ai_configured:
        if not extraction.manually_edited:
            extraction.status = ExtractionStatus.NOT_CONFIGURED
            extraction.error_code = "not_configured"
            extraction.updated_at = datetime.now(UTC)
            db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Extraction provider is not configured",
        )
    overwrite_manual = payload.overwrite_manual if payload is not None else False
    if extraction.manually_edited and not overwrite_manual:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Manual extraction is protected; confirm overwrite to rerun",
        )

    now = datetime.now(UTC)
    extraction.status = ExtractionStatus.PENDING
    extraction.error_code = None
    extraction.attempts = 0
    extraction.available_at = now
    extraction.claimed_at = None
    extraction.lease_expires_at = None
    extraction.claim_token = None
    extraction.completed_at = None
    extraction.revision += 1
    extraction.updated_at = now
    db.commit()
    db.refresh(extraction)
    response.status_code = status.HTTP_202_ACCEPTED
    return extraction
