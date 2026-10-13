"""Application settings, loaded once from the environment."""

from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

SUPPORTED_LOCALES: tuple[str, ...] = ("sv-SE", "en-GB")


class Environment(StrEnum):
    LOCAL = "local"
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


def _split_csv(value: object) -> object:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)

    # --- App ---------------------------------------------------------------
    app_env: Environment = Environment.LOCAL
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] | None = None
    docs_enabled: bool = True
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # --- Boost -------------------------------------------------------------
    boost_base_url: AnyHttpUrl = AnyHttpUrl("https://boost.fordona.io")
    boost_public_base_url: AnyHttpUrl | None = None
    boost_delivery_token: SecretStr = SecretStr("")
    boost_connect_timeout: float = Field(default=2.0, gt=0)
    boost_read_timeout: float = Field(default=5.0, gt=0)
    boost_max_retries: int = Field(default=2, ge=0, le=5)
    boost_total_budget: float = Field(default=8.0, gt=0)

    # --- Storage -----------------------------------------------------------
    database_url: str = "postgresql+asyncpg://bridge:bridge@localhost:5432/boost_bridge"
    redis_url: str = "redis://localhost:6379/0"

    # --- Cache -------------------------------------------------------------
    cache_soft_ttl_seconds: int = Field(default=300, ge=1)
    cache_hard_ttl_seconds: int = Field(default=86_400, ge=1)
    cache_negative_ttl_seconds: int = Field(default=30, ge=1)

    # --- Auth --------------------------------------------------------------
    auth_enabled: bool = True
    kinde_issuer_uri: str = ""
    kinde_jwks_uri: str = ""
    kinde_audience: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # --- Locale ------------------------------------------------------------
    default_locale: str = "sv-SE"

    _split = field_validator("cors_allowed_origins", "kinde_audience", mode="before")(_split_csv)

    @field_validator("default_locale")
    @classmethod
    def _known_locale(cls, value: str) -> str:
        if value not in SUPPORTED_LOCALES:
            raise ValueError(f"DEFAULT_LOCALE must be one of {SUPPORTED_LOCALES}")
        return value

    @model_validator(mode="after")
    def _check_consistency(self) -> "Settings":
        if self.cache_hard_ttl_seconds < self.cache_soft_ttl_seconds:
            raise ValueError("CACHE_HARD_TTL_SECONDS must be >= CACHE_SOFT_TTL_SECONDS")
        if not self.auth_enabled and self.app_env is not Environment.LOCAL:
            # A misplaced env var must never silently open the content bank.
            raise ValueError("AUTH_ENABLED=false is only permitted when APP_ENV=local")
        if self.auth_enabled and not (
            self.kinde_issuer_uri and self.kinde_jwks_uri and self.kinde_audience
        ):
            raise ValueError(
                "KINDE_ISSUER_URI, KINDE_JWKS_URI and KINDE_AUDIENCE are required "
                "when AUTH_ENABLED=true"
            )
        if self.app_env is not Environment.LOCAL and not self.boost_delivery_token:
            raise ValueError("BOOST_DELIVERY_TOKEN is required outside APP_ENV=local")
        return self

    @property
    def effective_log_format(self) -> str:
        if self.log_format:
            return self.log_format
        return "console" if self.app_env is Environment.LOCAL else "json"

    @property
    def asset_base_url(self) -> str:
        return str(self.boost_public_base_url or self.boost_base_url).rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()
