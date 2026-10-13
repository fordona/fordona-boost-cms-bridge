"""Kinde access-token verification.

The bridge reads Boost with a single service credential and caches content
shared across users, so this check is the only access control on the content
(design doc §8).

Rules:

* **RS256 only.** ``HS256`` and ``none`` are rejected before any key is looked
  up, which closes the algorithm-confusion hole.
* ``iss`` must match exactly, ``aud`` must contain a configured audience, and
  ``exp``/``nbf`` are checked with 30s leeway. ``sub``, ``exp`` and ``iat`` are required.
* The JWKS is fetched asynchronously and cached. An unknown ``kid`` triggers at
  most one refetch per ``min_refresh_interval``, so forged ``kid`` values cannot
  be used to flood Kinde.
* If the JWKS cannot be fetched and nothing is cached, the request fails with
  503, not 401. A learner whose token is fine must not be told to sign in again.
"""

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx
import jwt

from boost_bridge.core.clock import Clock, SystemClock
from boost_bridge.core.errors import UnauthorizedError, UpstreamUnavailableError
from boost_bridge.core.logging import get_logger

log = get_logger(__name__)

_ALGORITHM = "RS256"
_INVALID_TOKEN_DETAIL = "The access token is invalid or expired."  # noqa: S105 - message, not a secret


@dataclass(frozen=True, slots=True)
class Learner:
    """The authenticated caller. ``sub`` is the Kinde subject, a stable learner key."""

    sub: str
    claims: Mapping[str, Any] = field(default_factory=dict)


class JwksCache:
    def __init__(
        self,
        http: httpx.AsyncClient,
        jwks_uri: str,
        *,
        ttl_seconds: float = 600,
        min_refresh_interval_seconds: float = 60,
        clock: Clock | None = None,
    ) -> None:
        self._http = http
        self._uri = jwks_uri
        self._ttl = ttl_seconds
        self._min_refresh = min_refresh_interval_seconds
        self._clock = clock or SystemClock()
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at: float | None = None
        self._lock = asyncio.Lock()

    async def get_key(self, kid: str) -> jwt.PyJWK:
        if self._expired():
            await self._refresh(reason="ttl")
        key = self._keys.get(kid)
        if key is None and self._may_refetch():
            # The key may have been rotated since our last fetch.
            await self._refresh(reason="unknown_kid")
            key = self._keys.get(kid)
        if key is None:
            raise UnauthorizedError(_INVALID_TOKEN_DETAIL)
        return key

    def _expired(self) -> bool:
        return self._fetched_at is None or self._clock.now() - self._fetched_at >= self._ttl

    def _may_refetch(self) -> bool:
        return self._fetched_at is None or self._clock.now() - self._fetched_at >= self._min_refresh

    async def _refresh(self, *, reason: str) -> None:
        async with self._lock:
            fetched_at = self._fetched_at
            # Another coroutine may have refreshed while we waited for the lock.
            if fetched_at is not None and self._clock.now() - fetched_at < self._min_refresh:
                return
            try:
                response = await self._http.get(self._uri)
                response.raise_for_status()
                self._keys = _parse_jwks(response.json())
                self._fetched_at = self._clock.now()
                log.info("jwks_refreshed", reason=reason, keys=len(self._keys))
            except (httpx.HTTPError, ValueError, jwt.PyJWKSetError) as exc:
                log.warning("jwks_refresh_failed", reason=reason, error=repr(exc))
                if not self._keys:
                    raise UpstreamUnavailableError(
                        "Sign-in verification is temporarily unavailable."
                    ) from exc
                # Keep the keys we have, and do not hammer Kinde while it is down.
                self._fetched_at = self._clock.now()


def _parse_jwks(document: Any) -> dict[str, jwt.PyJWK]:
    keys: dict[str, jwt.PyJWK] = {}
    for raw in document.get("keys", []) if isinstance(document, dict) else []:
        if raw.get("kty") != "RSA" or raw.get("use", "sig") != "sig" or "kid" not in raw:
            continue
        try:
            keys[raw["kid"]] = jwt.PyJWK(raw, algorithm=_ALGORITHM)
        except jwt.PyJWTError:
            log.warning("jwks_key_skipped", kid=raw.get("kid"))
    if not keys:
        raise jwt.PyJWKSetError("JWKS contains no usable RSA signing keys")
    return keys


class TokenVerifier:
    def __init__(
        self,
        jwks: JwksCache,
        *,
        issuer: str,
        audiences: Sequence[str],
        leeway_seconds: int = 30,
    ) -> None:
        self._jwks = jwks
        self._issuer = issuer
        self._audiences = list(audiences)
        self._leeway = leeway_seconds

    async def verify(self, token: str) -> Learner:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError:
            raise UnauthorizedError(_INVALID_TOKEN_DETAIL) from None

        if header.get("alg") != _ALGORITHM:
            log.info("token_rejected", reason="algorithm", alg=header.get("alg"))
            raise UnauthorizedError(_INVALID_TOKEN_DETAIL)
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            log.info("token_rejected", reason="missing_kid")
            raise UnauthorizedError(_INVALID_TOKEN_DETAIL)

        key = await self._jwks.get_key(kid)
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key=key.key,
                algorithms=[_ALGORITHM],
                audience=self._audiences,
                issuer=self._issuer,
                leeway=self._leeway,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.PyJWTError as exc:
            # Log the reason class only, never the token.
            log.info("token_rejected", reason=type(exc).__name__)
            raise UnauthorizedError(_INVALID_TOKEN_DETAIL) from None

        sub = claims.get("sub")
        if not isinstance(sub, str) or not sub:
            raise UnauthorizedError(_INVALID_TOKEN_DETAIL)
        return Learner(sub=sub, claims=claims)
