import ipaddress
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .database import get_db
from .models import Manager, ManagerSession
from .rate_limit import rate_limiter
from .security import hash_session_token


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    trusted = get_settings().trusted_proxy_ips
    if not trusted:
        return peer
    try:
        peer_ip = ipaddress.ip_address(peer)
        networks = [
            ipaddress.ip_network(item.strip(), strict=False)
            for item in trusted.split(",")
            if item.strip()
        ]
    except ValueError:
        return peer
    if not any(peer_ip in network for network in networks):
        return peer
    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded:
        return peer
    candidate = forwarded.split(",", 1)[0].strip()
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return peer


def enforce_rate_limit(request: Request, bucket: str, limit: int) -> None:
    retry_after = rate_limiter.check(
        f"{bucket}:{client_ip(request)}", limit, get_settings().rate_limit_window_seconds
    )
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests",
            headers={"Retry-After": str(retry_after)},
        )


def get_current_session(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ManagerSession:
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    session = db.scalar(
        select(ManagerSession).where(
            ManagerSession.token_hash == hash_session_token(raw_token),
            ManagerSession.revoked_at.is_(None),
            ManagerSession.expires_at > datetime.now(UTC),
        )
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return session


def get_current_manager(
    session: ManagerSession = Depends(get_current_session),
) -> Manager:
    return session.manager
