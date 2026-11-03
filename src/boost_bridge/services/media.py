"""Asset id → CDN URL (Plan §4.6, §9.5, P6.T4).

Blocks carry asset ids, never URLs (§4.6) — resolving one to a URL, and
deciding whether it needs a signature, is this service's job alone. A unit
in ``MEDIA_FREE_UNIT_IDS`` gets plain, long-cached URLs; everything else is
signed per response and never cached — not that anything here *could* cache
one: a signed URL only ever exists in a response this service just built,
never in Redis (the body cache, P6.T3, holds Boost's raw JSON with asset ids
only, never a resolved URL of any kind).

``UrlSigner`` is the one seam O-10 (who hosts/processes media — Boost itself,
or Cloudflare R2 + Stream) is expected to touch: whichever way that decision
goes, ``AssetUrlResolver``'s own interface, the free-unit gating, and every
block mapper that calls it (``services/blocks.py``) stay exactly the same —
only the ``UrlSigner`` implementation ``build_asset_url_resolver`` wires in
would change.

The actual path layout below (``/i/{id}/{width}.webp``, ``/v/{id}/master
.m3u8``, …) is this service's own placeholder, not a contract from the plan —
the real CDN layout is itself part of the still-open O-10 decision. Flagged
here, the same way this codebase already flags other not-yet-confirmed
upstream shapes, rather than presented as settled.
"""

import hashlib
import hmac
import time
from collections.abc import Callable
from typing import Protocol

from boost_bridge.core.config import Settings
from boost_bridge.core.logging import get_logger

log = get_logger(__name__)

_DEFAULT_IMAGE_WIDTHS: tuple[int, ...] = (480, 960, 1440)
_PRIMARY_IMAGE_WIDTH = 960


class UrlSigner(Protocol):
    def sign(self, path: str) -> str:
        """Returns the full URL for ``path`` (already asset-specific), with whatever
        this signer wants to append — a signature and expiry, or nothing.
        """
        ...


class PlainUrlSigner:
    """No signature at all — the free-unit case, or local dev with no signing key configured."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    def sign(self, path: str) -> str:
        return f"{self._base_url}{path}"


class HmacUrlSigner:
    """HMAC-SHA256 over ``path:expiry`` (Plan §9.5: TTL 2 h; an expired URL 403s at
    the CDN and the app re-fetches the lesson/attempt to get fresh ones).
    """

    def __init__(
        self,
        base_url: str,
        signing_key: bytes,
        *,
        ttl_seconds: int,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._signing_key = signing_key
        self._ttl_seconds = ttl_seconds
        self._now = now

    def sign(self, path: str) -> str:
        expiry = int(self._now()) + self._ttl_seconds
        signature = self._digest(path, expiry)
        return f"{self._base_url}{path}?exp={expiry}&sig={signature}"

    def verify(self, path: str, *, exp: int, sig: str) -> bool:
        """For tests ("the signature... verifiable with the key") — not used at runtime."""
        return hmac.compare_digest(self._digest(path, exp), sig)

    def _digest(self, path: str, expiry: int) -> str:
        message = f"{path}:{expiry}".encode()
        return hmac.new(self._signing_key, message, hashlib.sha256).hexdigest()


class AssetUrlResolver:
    def __init__(
        self, free_unit_ids: frozenset[str], plain_signer: UrlSigner, signed_signer: UrlSigner
    ) -> None:
        self._free_unit_ids = free_unit_ids
        self._plain_signer = plain_signer
        self._signed_signer = signed_signer

    def is_free_unit(self, unit_id: str | None) -> bool:
        return unit_id is not None and unit_id in self._free_unit_ids

    def _signer_for(self, unit_id: str | None) -> UrlSigner:
        return self._plain_signer if self.is_free_unit(unit_id) else self._signed_signer

    def image_url(
        self, asset_id: str, *, width: int = _PRIMARY_IMAGE_WIDTH, unit_id: str | None
    ) -> str:
        return self._signer_for(unit_id).sign(f"/i/{asset_id}/{width}.webp")

    def image_srcset(
        self, asset_id: str, *, unit_id: str | None, widths: tuple[int, ...] = _DEFAULT_IMAGE_WIDTHS
    ) -> list[str]:
        return [self.image_url(asset_id, width=w, unit_id=unit_id) for w in widths]

    def hls_url(self, asset_id: str, *, unit_id: str | None) -> str:
        return self._signer_for(unit_id).sign(f"/v/{asset_id}/master.m3u8")

    def poster_url(self, asset_id: str, *, unit_id: str | None) -> str:
        return self._signer_for(unit_id).sign(f"/i/{asset_id}/poster.jpg")

    def lottie_url(self, asset_id: str, *, unit_id: str | None) -> str:
        return self._signer_for(unit_id).sign(f"/a/{asset_id}/animation.json")

    def video_loop_url(self, asset_id: str, *, unit_id: str | None) -> str:
        return self._signer_for(unit_id).sign(f"/v/{asset_id}/loop.mp4")

    def caption_url(self, file_id: str, *, unit_id: str | None) -> str:
        return self._signer_for(unit_id).sign(f"/c/{file_id}.vtt")


def build_asset_url_resolver(
    settings: Settings, *, now: Callable[[], float] = time.time
) -> AssetUrlResolver:
    base_url = str(settings.media_cdn_base_url)
    plain_signer: UrlSigner = PlainUrlSigner(base_url)
    signing_key = settings.media_signing_key.get_secret_value()
    signed_signer: UrlSigner = (
        HmacUrlSigner(
            base_url,
            signing_key.encode(),
            ttl_seconds=settings.media_signed_url_ttl_seconds,
            now=now,
        )
        if signing_key
        # Local dev only — Settings refuses a missing MEDIA_SIGNING_KEY outside
        # APP_ENV=local, so this fallback can never be reached in a real deployment.
        else plain_signer
    )
    if not signing_key:
        log.warning("media_signing_key_unset_using_plain_urls")
    return AssetUrlResolver(frozenset(settings.media_free_unit_ids), plain_signer, signed_signer)
