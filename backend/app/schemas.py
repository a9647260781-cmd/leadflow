import math
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from .models import ExtractionStatus, LeadStatus, NotificationKind

MAX_BUDGET = Decimal("99999999999999.99")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class ManagerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str


class LeadCreate(BaseModel):
    submission_id: uuid.UUID
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=3, max_length=40)
    description: str = Field(min_length=1, max_length=10_000)

    @field_validator("name", "phone", "description")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class LeadCreatedResponse(BaseModel):
    id: uuid.UUID
    created_at: datetime


class LeadListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    phone: str
    description: str
    status: LeadStatus
    created_at: datetime
    updated_at: datetime


class HistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    message: str
    created_at: datetime


class ExtractionEvidence(BaseModel):
    service: str | None
    budget: str | None
    timeframe: str | None


class ExtractionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: ExtractionStatus
    service: str | None
    budget_min: float | None
    budget_max: float | None
    budget_currency: str | None
    budget_text: str | None
    timeframe: str | None
    evidence: ExtractionEvidence
    error_code: str | None
    attempts: int
    updated_at: datetime
    completed_at: datetime | None
    manually_edited: bool
    revision: int


class LeadDetail(LeadListItem):
    history: list[HistoryResponse]
    extraction: ExtractionResponse


class LeadListResponse(BaseModel):
    items: list[LeadListItem]
    total: int
    page: int
    page_size: int


class LeadStatusUpdate(BaseModel):
    status: LeadStatus


class ExtractionWrite(BaseModel):
    expected_revision: int = Field(ge=0)
    service: str | None = Field(max_length=300)
    budget_min: float | None
    budget_max: float | None
    budget_currency: str | None = Field(max_length=3)
    budget_text: str | None = Field(max_length=300)
    timeframe: str | None = Field(max_length=300)
    evidence: ExtractionEvidence

    @field_validator("budget_min", "budget_max")
    @classmethod
    def validate_budget_number(cls, value: float | None) -> float | None:
        if value is not None and (not math.isfinite(value) or value < 0):
            raise ValueError("budget values must be finite and nonnegative")
        if value is not None:
            decimal = Decimal(str(value))
            if decimal > MAX_BUDGET or decimal.as_tuple().exponent < -2:
                raise ValueError("budget values support at most 14 integer and 2 decimal digits")
        return value

    @field_validator("budget_currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.upper()
        if value not in {"RUB", "USD", "EUR"}:
            raise ValueError("unsupported currency")
        return value

    @model_validator(mode="after")
    def validate_range(self) -> "ExtractionWrite":
        if (
            self.budget_min is not None
            and self.budget_max is not None
            and self.budget_min > self.budget_max
        ):
            raise ValueError("budget_min must not exceed budget_max")
        if self.budget_min is None and self.budget_max is None and self.budget_currency is not None:
            raise ValueError("budget_currency requires a numeric budget")
        return self


class ExtractionRetryRequest(BaseModel):
    overwrite_manual: bool = False


class NotificationDispatchRequest(BaseModel):
    kind: NotificationKind
    limit: int = Field(default=1, ge=1, le=20)


class NotificationDispatchResponse(BaseModel):
    kind: NotificationKind
    claimed: int
    sent: int
    retried: int
    failed: int
    delivery_unknown: int
    skipped: int
