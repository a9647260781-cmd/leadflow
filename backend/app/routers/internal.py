import hashlib
import hmac

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..database import get_db
from ..notifications import TelegramClient, dispatch_notifications
from ..schemas import NotificationDispatchRequest, NotificationDispatchResponse

router = APIRouter(prefix="/internal/notifications", tags=["internal"])


def require_notification_service(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Settings:
    authorization = request.headers.get("authorization", "")
    scheme, separator, supplied = authorization.partition(" ")
    configured_secret = settings.notifications_service_token
    expected = configured_secret.get_secret_value() if configured_secret is not None else ""
    token_matches = hmac.compare_digest(
        hashlib.sha256(supplied.encode()).digest(),
        hashlib.sha256(expected.encode()).digest(),
    )
    valid = (
        bool(expected)
        and scheme.lower() == "bearer"
        and separator == " "
        and token_matches
    )
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid notification service credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not settings.notifications_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Notifications are not configured",
        )
    return settings


def get_telegram_client(
    settings: Settings = Depends(require_notification_service),
) -> TelegramClient:
    return TelegramClient(settings)


@router.post(
    "/dispatch",
    response_model=NotificationDispatchResponse,
    responses={
        401: {"description": "Invalid notification service credentials"},
        503: {"description": "Notifications are disabled or incomplete"},
    },
)
def dispatch(
    payload: NotificationDispatchRequest,
    settings: Settings = Depends(require_notification_service),
    telegram: TelegramClient = Depends(get_telegram_client),
    db: Session = Depends(get_db),
) -> dict[str, int | str]:
    return dispatch_notifications(db, payload.kind, payload.limit, settings, telegram)
