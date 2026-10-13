import pytest

from boost_bridge.core.locale import UnsupportedLocaleError, match_locale, resolve_locale


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("sv-SE", "sv-SE"),
        ("SV-se", "sv-SE"),
        ("sv", "sv-SE"),
        ("en", "en-GB"),
        ("en-US", "en-GB"),
        ("en-GB", "en-GB"),
        ("fr-FR", None),
        ("", None),
    ],
)
def test_match_locale(tag: str, expected: str | None) -> None:
    assert match_locale(tag) == expected


def test_explicit_locale_wins_over_header() -> None:
    assert resolve_locale("en-GB", "sv-SE,sv;q=0.9", "sv-SE") == "en-GB"


def test_explicit_unsupported_locale_is_an_error() -> None:
    with pytest.raises(UnsupportedLocaleError):
        resolve_locale("de-DE", None, "sv-SE")


def test_accept_language_respects_q_values() -> None:
    assert resolve_locale(None, "fr;q=1.0, en;q=0.8, sv;q=0.9", "sv-SE") == "sv-SE"
    assert resolve_locale(None, "sv;q=0.2, en-US", "sv-SE") == "en-GB"


def test_accept_language_skips_unsupported_and_zero_quality() -> None:
    assert resolve_locale(None, "de, en;q=0", "sv-SE") == "sv-SE"
    assert resolve_locale(None, "*, en", "sv-SE") == "en-GB"


def test_malformed_accept_language_falls_back_to_default() -> None:
    assert resolve_locale(None, ";;;q=abc,,", "en-GB") == "en-GB"


def test_default_when_nothing_given() -> None:
    assert resolve_locale(None, None, "sv-SE") == "sv-SE"
