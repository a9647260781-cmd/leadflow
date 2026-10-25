import pytest
from starlette.requests import Request

from app import dependencies
from app.config import Settings
from app.dependencies import client_ip
from app.rate_limit import FixedWindowRateLimiter
from app.security import hash_password, hash_session_token, new_session_token, verify_password


def test_passwords_are_argon2_hashed_and_verified() -> None:
    encoded = hash_password("a sufficiently long password")
    assert encoded.startswith("$argon2")
    assert verify_password("a sufficiently long password", encoded)
    assert not verify_password("wrong password", encoded)


def test_session_tokens_are_random_and_only_hash_is_stable() -> None:
    first = new_session_token()
    second = new_session_token()
    assert first != second
    assert len(hash_session_token(first)) == 64
    assert hash_session_token(first) == hash_session_token(first)
    assert hash_session_token(first) != hash_session_token(second)


def test_rate_limiter_rejects_after_limit() -> None:
    limiter = FixedWindowRateLimiter()
    assert limiter.check("client", limit=2, window_seconds=60) is None
    assert limiter.check("client", limit=2, window_seconds=60) is None
    assert limiter.check("client", limit=2, window_seconds=60) is not None
    assert limiter.check("other-client", limit=2, window_seconds=60) is None


def test_database_components_encode_special_password_characters() -> None:
    settings = Settings(database_url=None, db_password="p@ss#word%value")
    rendered = settings.sqlalchemy_database_url.render_as_string(hide_password=False)
    assert "p%40ss%23word%25value" in rendered


def _request(peer: str, forwarded_for: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"x-forwarded-for", forwarded_for.encode("ascii"))],
            "client": (peer, 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )


def test_forwarded_ip_is_ignored_from_untrusted_peer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dependencies, "get_settings", lambda: Settings(trusted_proxy_ips="10.0.0.0/24")
    )
    assert client_ip(_request("192.0.2.20", "203.0.113.8")) == "192.0.2.20"


def test_forwarded_ip_is_used_from_trusted_peer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dependencies, "get_settings", lambda: Settings(trusted_proxy_ips="10.0.0.0/24")
    )
    assert client_ip(_request("10.0.0.7", "203.0.113.8")) == "203.0.113.8"
