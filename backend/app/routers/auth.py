from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..database import get_db
from ..dependencies import enforce_rate_limit, get_current_manager, get_current_session
from ..models import Manager, ManagerSession
from ..schemas import LoginRequest, ManagerResponse
from ..security import hash_password, hash_session_token, new_session_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

# Keeps the nonexistent-user path computationally similar to a bad password.
_DUMMY_PASSWORD_HASH = hash_password("not-a-real-password")


@router.post("/login", response_model=ManagerResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Manager:
    enforce_rate_limit(request, "login", settings.login_rate_limit)
    manager = db.scalar(select(Manager).where(Manager.email == str(payload.email).lower()))
    encoded = manager.password_hash if manager else _DUMMY_PASSWORD_HASH
    if not verify_password(payload.password, encoded) or manager is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = new_session_token()
    expires_at = datetime.now(UTC) + timedelta(hours=settings.session_ttl_hours)
    db.add(
        ManagerSession(
            manager_id=manager.id,
            token_hash=hash_session_token(token),
            expires_at=expires_at,
        )
    )
    db.commit()

    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_hours * 60 * 60,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        path="/api",
    )
    return manager


@router.get("/me", response_model=ManagerResponse)
def me(manager: Manager = Depends(get_current_manager)) -> Manager:
    return manager


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    current_session: ManagerSession = Depends(get_current_session),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> None:
    db.execute(
        update(ManagerSession)
        .where(ManagerSession.id == current_session.id)
        .values(revoked_at=datetime.now(UTC))
    )
    db.commit()
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/api",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite=settings.session_cookie_samesite,
    )
