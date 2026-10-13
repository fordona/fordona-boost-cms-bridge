import pytest
from pydantic import ValidationError

from boost_bridge.core.config import Environment, Settings

_AUTH = {
    "kinde_issuer_uri": "https://tenant.kinde.com",
    "kinde_jwks_uri": "https://tenant.kinde.com/.well-known/jwks",
    "kinde_audience": "aud-a, aud-b",
}


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def test_csv_lists_are_split() -> None:
    settings = _settings(**_AUTH, cors_allowed_origins="http://a, http://b,")
    assert settings.kinde_audience == ["aud-a", "aud-b"]
    assert settings.cors_allowed_origins == ["http://a", "http://b"]


def test_auth_cannot_be_disabled_outside_local() -> None:
    with pytest.raises(ValidationError, match="only permitted when APP_ENV=local"):
        _settings(app_env="prod", auth_enabled=False, boost_delivery_token="t")


def test_auth_disabled_is_allowed_locally() -> None:
    settings = _settings(app_env="local", auth_enabled=False)
    assert settings.app_env is Environment.LOCAL


def test_kinde_settings_required_when_auth_enabled() -> None:
    with pytest.raises(ValidationError, match="KINDE_ISSUER_URI"):
        _settings(auth_enabled=True)


def test_delivery_token_required_outside_local() -> None:
    with pytest.raises(ValidationError, match="BOOST_DELIVERY_TOKEN"):
        _settings(**_AUTH, app_env="staging")


def test_hard_ttl_must_not_be_below_soft_ttl() -> None:
    with pytest.raises(ValidationError, match="CACHE_HARD_TTL_SECONDS"):
        _settings(**_AUTH, cache_soft_ttl_seconds=600, cache_hard_ttl_seconds=60)


def test_unknown_default_locale_rejected() -> None:
    with pytest.raises(ValidationError, match="DEFAULT_LOCALE"):
        _settings(**_AUTH, default_locale="de-DE")


def test_log_format_defaults_by_environment() -> None:
    assert _settings(**_AUTH).effective_log_format == "console"
    assert (
        _settings(**_AUTH, app_env="prod", boost_delivery_token="t").effective_log_format == "json"
    )


def test_asset_base_url_prefers_public_url() -> None:
    settings = _settings(
        **_AUTH,
        boost_base_url="http://boost.internal:8082",
        boost_public_base_url="https://boost.fordona.io/",
    )
    assert settings.asset_base_url == "https://boost.fordona.io"
    assert _settings(**_AUTH).asset_base_url == "https://boost.fordona.io"


def test_secret_is_not_rendered() -> None:
    settings = _settings(**_AUTH, boost_delivery_token="super-secret")
    assert "super-secret" not in repr(settings)
