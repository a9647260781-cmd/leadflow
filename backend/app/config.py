from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str | None = None
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "leadflow"
    db_user: str = "leadflow"
    db_password: str = "leadflow"
    db_connect_timeout_seconds: int = 5
    app_origin: str = "http://localhost:8080"
    additional_allowed_origins: str = ""
    trusted_proxy_ips: str = ""

    session_cookie_name: str = "leadflow_session"
    session_cookie_secure: bool = False
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    session_ttl_hours: int = 24

    login_rate_limit: int = 5
    public_lead_rate_limit: int = 20
    rate_limit_window_seconds: int = 60
    extraction_retry_rate_limit: int = 10

    ai_enabled: bool = False
    yandex_api_key: SecretStr | None = None
    yandex_model_uri: str | None = None
    yandex_api_url: str = "https://ai.api.cloud.yandex.net/foundationModels/v1/completion"
    yandex_data_logging_enabled: bool = False
    extraction_poll_interval_seconds: float = 2.0
    extraction_request_timeout_seconds: float = 20.0
    extraction_max_attempts: int = 4
    extraction_lease_seconds: int = 60
    extraction_retry_base_seconds: int = 5

    notifications_enabled: bool = False
    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None
    telegram_api_base_url: str = "https://api.telegram.org"
    notifications_service_token: SecretStr | None = None
    notification_reminder_minutes: int = 30
    manager_public_url: str = "http://localhost:8080"
    notification_request_timeout_seconds: float = 10.0
    notification_lease_seconds: int = 60
    notification_max_attempts: int = 4
    notification_retry_base_seconds: int = 5
    notification_retry_cap_seconds: int = 300

    @field_validator("app_origin")
    @classmethod
    def normalize_origin(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator(
        "session_ttl_hours",
        "db_connect_timeout_seconds",
        "login_rate_limit",
        "public_lead_rate_limit",
        "extraction_retry_rate_limit",
        "rate_limit_window_seconds",
        "extraction_max_attempts",
        "extraction_lease_seconds",
        "extraction_retry_base_seconds",
        "notification_reminder_minutes",
        "notification_lease_seconds",
        "notification_max_attempts",
        "notification_retry_base_seconds",
        "notification_retry_cap_seconds",
    )
    @classmethod
    def positive_integer(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be greater than zero")
        return value

    @field_validator(
        "extraction_poll_interval_seconds",
        "extraction_request_timeout_seconds",
        "notification_request_timeout_seconds",
    )
    @classmethod
    def positive_number(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("must be greater than zero")
        return value

    @model_validator(mode="after")
    def validate_cookie_policy(self) -> "Settings":
        if self.session_cookie_samesite == "none" and not self.session_cookie_secure:
            raise ValueError("SameSite=None requires SESSION_COOKIE_SECURE=true")
        return self

    @property
    def allowed_origins(self) -> tuple[str, ...]:
        extra = [item.strip().rstrip("/") for item in self.additional_allowed_origins.split(",")]
        return tuple(dict.fromkeys([self.app_origin, *(item for item in extra if item)]))

    @property
    def sqlalchemy_database_url(self) -> URL:
        if self.database_url:
            return make_url(self.database_url)
        return URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )

    @property
    def ai_configured(self) -> bool:
        return bool(
            self.ai_enabled
            and self.yandex_api_key
            and self.yandex_api_key.get_secret_value()
            and self.yandex_model_uri
            and self.yandex_model_uri.startswith("gpt://")
        )

    @field_validator("manager_public_url", "telegram_api_base_url")
    @classmethod
    def normalize_public_url(cls, value: str) -> str:
        return value.rstrip("/")

    @property
    def notifications_configured(self) -> bool:
        return bool(
            self.notifications_enabled
            and self.telegram_bot_token
            and self.telegram_bot_token.get_secret_value()
            and self.telegram_chat_id
            and self.telegram_chat_id.strip()
            and self.notifications_service_token
            and self.notifications_service_token.get_secret_value()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
