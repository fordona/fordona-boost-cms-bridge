"""Application settings, loaded once from the environment."""

from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

SUPPORTED_LOCALES: tuple[str, ...] = ("sv-SE", "en-GB")


class BoostAuthMode(StrEnum):
    """Which credential the bridge presents to Boost's delivery API.

    * ``forward_learner_token`` (default): forward the caller's verified Kinde
      access token. Boost's docs make Boost-audience learner tokens the primary
      delivery credential, and no extra secret is needed. Published content is
      identical for every learner, so the shared cache stays correct.
    * ``service_token``: Boost's shared delivery service token
      (``BOOST_DELIVERY_TOKEN``), described by Boost as the credential for
      existing trusted delivery consumers.
    """

    FORWARD_LEARNER_TOKEN = "forward_learner_token"  # noqa: S105 - mode name, not a secret
    SERVICE_TOKEN = "service_token"  # noqa: S105 - mode name, not a secret


class Environment(StrEnum):
    LOCAL = "local"
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


def _host(url: str) -> str | None:
    return urlsplit(url).hostname


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
    # The API origin, not the CMS UI at boost.fordona.io.
    boost_base_url: AnyHttpUrl = AnyHttpUrl("https://boost-api.fordona.io")
    boost_auth_mode: BoostAuthMode = BoostAuthMode.FORWARD_LEARNER_TOKEN
    boost_delivery_token: SecretStr = SecretStr("")
    # Fallback asset URL prefix, used only when a delivery item has no
    # ``assetBaseUrl`` of its own. Defaults to ``{BOOST_BASE_URL}/assets``.
    boost_asset_base_url: AnyHttpUrl | None = None
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
        if self.boost_auth_mode is BoostAuthMode.SERVICE_TOKEN:
            if not self.boost_delivery_token.get_secret_value():
                raise ValueError(
                    "BOOST_DELIVERY_TOKEN is required when BOOST_AUTH_MODE=service_token"
                )
        elif not self.auth_enabled:
            raise ValueError(
                "BOOST_AUTH_MODE=forward_learner_token needs AUTH_ENABLED=true: "
                "there is no learner token to forward otherwise"
            )
        return self

    @property
    def effective_log_format(self) -> str:
        if self.log_format:
            return self.log_format
        return "console" if self.app_env is Environment.LOCAL else "json"

    @property
    def access_boundary_warnings(self) -> list[str]:
        """Settings that leave the bridge short of being the theory app's access boundary.

        Both are allowed (existing deployments keep working), but each means a learner's
        token can read Boost's published question bank without going through the bridge,
        bypassing the subscription check the bridge exists to enforce. The target setup is
        ``BOOST_AUTH_MODE=service_token`` with ``KINDE_AUDIENCE`` set to the Fordona API
        audience that fordona-engine also accepts.
        """
        warnings: list[str] = []
        if self.boost_auth_mode is BoostAuthMode.FORWARD_LEARNER_TOKEN:
            warnings.append(
                "BOOST_AUTH_MODE=forward_learner_token: learners need Boost-audience tokens, "
                "which also work against Boost directly; use service_token"
            )
        boost_host = self.boost_base_url.host
        if any(_host(audience) == boost_host for audience in self.kinde_audience):
            warnings.append(
                "KINDE_AUDIENCE includes Boost's own audience: a token accepted here is "
                "accepted by Boost too; use the Fordona API audience"
            )
        return warnings

    @property
    def asset_base_url(self) -> str:
        """Prefix that an asset id is appended to (``{prefix}/{assetId}``)."""
        if self.boost_asset_base_url is not None:
            return str(self.boost_asset_base_url).rstrip("/")
        return f"{str(self.boost_base_url).rstrip('/')}/assets"


@lru_cache
def get_settings() -> Settings:
    return Settings()
