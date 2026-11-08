"""The stub's own settings. Independent of ``fordona_connect.core.config``."""

from functools import lru_cache
from pathlib import Path

from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "stub-data"

SUPPORTED_LOCALES: tuple[str, ...] = ("sv-SE", "en-GB")
MAX_BATCH_REFS = 100


class StubSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)

    stub_upstream_boost_url: AnyHttpUrl
    stub_data_dir: Path = _DEFAULT_DATA_DIR
    stub_sqlite_path: str = "stub-changes.sqlite3"
    stub_poll_seconds: float = Field(default=60.0, gt=0)
    # §13.3: "the simplest correct implementation returns only rows created more
    # than 5 seconds ago" (commit-order safety).
    stub_visibility_lag_seconds: float = Field(default=5.0, ge=0)
    # §13.3: "at least 30 days". Configurable so tests can exercise CURSOR_EXPIRED
    # without waiting 30 days.
    stub_retention_seconds: float = Field(default=30 * 24 * 3600, gt=0)
    stub_upstream_timeout_seconds: float = Field(default=10.0, gt=0)
    # A Boost delivery token for the stub's own background poll (plan §4.5's
    # "it lists today's Boost every 60 s"). Distinct from a caller's own token,
    # which is forwarded unchanged per request and never stored. Empty disables
    # polling (the stub still serves whatever it has loaded).
    stub_poll_token: SecretStr = SecretStr("")


@lru_cache
def get_stub_settings() -> StubSettings:
    return StubSettings()
