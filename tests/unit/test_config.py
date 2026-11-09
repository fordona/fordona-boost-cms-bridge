import pytest
from pydantic import ValidationError

from fordona_connect.core.config import BoostAuthMode, Environment, Settings

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


def test_driverless_database_url_uses_asyncpg() -> None:
    settings = _settings(**_AUTH, database_url="postgresql://u:p@db:5432/fordona")
    assert settings.database_url == "postgresql+asyncpg://u:p@db:5432/fordona"


def test_unsupported_database_driver_is_refused_at_startup() -> None:
    with pytest.raises(ValidationError, match="asyncpg"):
        _settings(**_AUTH, database_url="postgresql+psycopg://u:p@db:5432/fordona")


def test_auth_cannot_be_disabled_outside_local() -> None:
    with pytest.raises(ValidationError, match="only permitted when APP_ENV=local"):
        _settings(
            app_env="prod",
            auth_enabled=False,
            boost_auth_mode="service_token",
            boost_delivery_token="t",
        )


def test_auth_disabled_is_allowed_locally() -> None:
    settings = _settings(
        app_env="local",
        auth_enabled=False,
        boost_auth_mode="service_token",
        boost_delivery_token="t",
    )
    assert settings.app_env is Environment.LOCAL


def test_kinde_settings_required_when_auth_enabled() -> None:
    with pytest.raises(ValidationError, match="KINDE_ISSUER_URI"):
        _settings(auth_enabled=True)


def test_service_token_mode_requires_delivery_token() -> None:
    with pytest.raises(ValidationError, match="BOOST_DELIVERY_TOKEN"):
        _settings(**_AUTH, boost_auth_mode="service_token")


def test_forward_mode_is_default_and_needs_no_delivery_token() -> None:
    settings = _settings(**_AUTH, app_env="prod", engine_internal_token="t", media_signing_key="t")
    assert settings.boost_auth_mode is BoostAuthMode.FORWARD_LEARNER_TOKEN


def test_forward_mode_requires_auth() -> None:
    with pytest.raises(ValidationError, match="forward_learner_token needs AUTH_ENABLED"):
        _settings(auth_enabled=False)


def test_hard_ttl_must_not_be_below_soft_ttl() -> None:
    with pytest.raises(ValidationError, match="CACHE_HARD_TTL_SECONDS"):
        _settings(**_AUTH, cache_soft_ttl_seconds=600, cache_hard_ttl_seconds=60)


def test_unknown_default_locale_rejected() -> None:
    with pytest.raises(ValidationError, match="DEFAULT_LOCALE"):
        _settings(**_AUTH, default_locale="de-DE")


def test_log_format_defaults_by_environment() -> None:
    assert _settings(**_AUTH).effective_log_format == "console"
    assert (
        _settings(
            **_AUTH,
            app_env="prod",
            boost_delivery_token="t",
            engine_internal_token="t",
            media_signing_key="t",
        ).effective_log_format
        == "json"
    )


def test_asset_base_url_fallback() -> None:
    settings = _settings(
        **_AUTH,
        boost_base_url="http://boost.internal:8082",
        boost_asset_base_url="https://cdn.fordona.io/assets/",
    )
    assert settings.asset_base_url == "https://cdn.fordona.io/assets"
    assert _settings(**_AUTH).asset_base_url == "https://boost-api.fordona.io/assets"


def test_secret_is_not_rendered() -> None:
    settings = _settings(**_AUTH, boost_delivery_token="super-secret")
    assert "super-secret" not in repr(settings)


def test_boundary_warnings_flag_forwarding_and_boost_audience() -> None:
    settings = _settings(
        kinde_issuer_uri="https://tenant.kinde.com",
        kinde_jwks_uri="https://tenant.kinde.com/.well-known/jwks",
        kinde_audience="https://boost-api.fordona.io/",
    )
    assert len(settings.access_boundary_warnings) == 2


def test_no_boundary_warnings_for_service_token_and_fordona_audience() -> None:
    settings = _settings(
        kinde_issuer_uri="https://tenant.kinde.com",
        kinde_jwks_uri="https://tenant.kinde.com/.well-known/jwks",
        kinde_audience="https://api.fordona.io",
        boost_auth_mode=BoostAuthMode.SERVICE_TOKEN,
        boost_delivery_token="t",
    )
    assert settings.access_boundary_warnings == []


def test_engine_token_required_outside_local() -> None:
    with pytest.raises(ValidationError, match="ENGINE_INTERNAL_TOKEN"):
        _settings(
            **_AUTH,
            app_env="prod",
            boost_delivery_token="t",
            boost_auth_mode="service_token",
            media_signing_key="t",
        )


def test_engine_token_not_required_locally() -> None:
    settings = _settings(**_AUTH, app_env="local")
    assert settings.engine_internal_token.get_secret_value() == ""


def test_media_signing_key_required_outside_local() -> None:
    with pytest.raises(ValidationError, match="MEDIA_SIGNING_KEY"):
        _settings(
            **_AUTH,
            app_env="prod",
            boost_delivery_token="t",
            boost_auth_mode="service_token",
            engine_internal_token="t",
        )


def test_engine_token_secret_is_not_rendered() -> None:
    settings = _settings(**_AUTH, engine_internal_token="super-secret-engine-token")
    assert "super-secret-engine-token" not in repr(settings)


def test_media_free_unit_ids_split_as_csv() -> None:
    settings = _settings(**_AUTH, media_free_unit_ids="1, 2, 3")
    assert settings.media_free_unit_ids == ["1", "2", "3"]


_OUTSIDE_LOCAL = {
    **_AUTH,
    "app_env": "staging",
    "boost_delivery_token": "t",
    "boost_auth_mode": "service_token",
    "engine_internal_token": "t",
    "media_signing_key": "t",
    "content_sync_interval_seconds": 60,
}


def test_content_sync_needs_the_grading_token_outside_local() -> None:
    with pytest.raises(ValidationError, match="BOOST_GRADING_TOKEN"):
        _settings(**_OUTSIDE_LOCAL)


def test_content_sync_needs_a_service_token_outside_local() -> None:
    with pytest.raises(ValidationError, match="service_token"):
        _settings(
            **{**_OUTSIDE_LOCAL, "boost_auth_mode": "forward_learner_token"},
            boost_grading_token="g",
        )


def test_content_sync_can_be_turned_off_without_a_grading_token() -> None:
    settings = _settings(**{**_OUTSIDE_LOCAL, "content_sync_interval_seconds": 0})
    assert settings.boost_grading_token.get_secret_value() == ""


def test_grading_token_is_not_rendered() -> None:
    settings = _settings(**_OUTSIDE_LOCAL, boost_grading_token="super-secret-grading")
    assert "super-secret-grading" not in repr(settings)
