"""AssetUrlResolver / UrlSigner: signing, expiry, free-unit bypass (Plan §9.5, P6.T4)."""

import pytest

from boost_bridge.services.media import AssetUrlResolver, HmacUrlSigner, PlainUrlSigner

BASE = "https://media.test"
KEY = b"super-secret-signing-key"


class FixedClock:
    def __init__(self, value: float) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


def test_plain_signer_appends_no_query_params() -> None:
    signer = PlainUrlSigner(BASE)
    assert signer.sign("/i/42/960.webp") == f"{BASE}/i/42/960.webp"


def test_hmac_signer_appends_exp_and_sig() -> None:
    signer = HmacUrlSigner(BASE, KEY, ttl_seconds=7200, now=FixedClock(1_800_000_000.0))

    url = signer.sign("/i/42/960.webp")

    assert url.startswith(f"{BASE}/i/42/960.webp?exp=1800007200&sig=")


def test_hmac_signature_is_verifiable_with_the_same_key() -> None:
    signer = HmacUrlSigner(BASE, KEY, ttl_seconds=7200, now=FixedClock(1_800_000_000.0))
    url = signer.sign("/i/42/960.webp")
    exp = int(url.split("exp=")[1].split("&")[0])
    sig = url.split("sig=")[1]

    assert signer.verify("/i/42/960.webp", exp=exp, sig=sig) is True


def test_hmac_signature_fails_verification_with_a_different_key() -> None:
    signer = HmacUrlSigner(BASE, KEY, ttl_seconds=7200, now=FixedClock(1_800_000_000.0))
    other = HmacUrlSigner(
        BASE, b"a-different-key", ttl_seconds=7200, now=FixedClock(1_800_000_000.0)
    )
    url = signer.sign("/i/42/960.webp")
    exp = int(url.split("exp=")[1].split("&")[0])
    sig = url.split("sig=")[1]

    assert other.verify("/i/42/960.webp", exp=exp, sig=sig) is False


def test_hmac_signature_fails_verification_for_a_different_path() -> None:
    signer = HmacUrlSigner(BASE, KEY, ttl_seconds=7200, now=FixedClock(1_800_000_000.0))
    url = signer.sign("/i/42/960.webp")
    exp = int(url.split("exp=")[1].split("&")[0])
    sig = url.split("sig=")[1]

    assert signer.verify("/i/99/960.webp", exp=exp, sig=sig) is False


def test_expiry_reflects_the_configured_ttl() -> None:
    now = FixedClock(1_000_000_000.0)
    signer = HmacUrlSigner(BASE, KEY, ttl_seconds=120, now=now)

    url = signer.sign("/v/1/master.m3u8")

    assert "exp=1000000120" in url


@pytest.fixture
def resolver() -> AssetUrlResolver:
    plain = PlainUrlSigner(BASE)
    signed = HmacUrlSigner(BASE, KEY, ttl_seconds=7200, now=FixedClock(1_800_000_000.0))
    return AssetUrlResolver(frozenset({"1"}), plain, signed)


def test_free_unit_gets_plain_url(resolver: AssetUrlResolver) -> None:
    url = resolver.image_url("42", unit_id="1")
    assert url == f"{BASE}/i/42/960.webp"


def test_non_free_unit_gets_a_signed_url(resolver: AssetUrlResolver) -> None:
    url = resolver.image_url("42", unit_id="2")
    assert "sig=" in url
    assert "exp=" in url


def test_unknown_unit_is_treated_as_not_free(resolver: AssetUrlResolver) -> None:
    url = resolver.image_url("42", unit_id=None)
    assert "sig=" in url


def test_image_srcset_has_one_url_per_configured_width(resolver: AssetUrlResolver) -> None:
    srcset = resolver.image_srcset("42", unit_id="2")
    assert len(srcset) == 3
    assert all("sig=" in url for url in srcset)


def test_hls_url_points_at_a_master_playlist(resolver: AssetUrlResolver) -> None:
    url = resolver.hls_url("77", unit_id="2")
    assert "/v/77/master.m3u8" in url
