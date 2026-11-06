"""The stub holds no identity of its own: a token's scope is whatever Boost says it is.

"The stub forwards the caller's bearer token to Boost unchanged, so token scopes
stay real" (plan §4.5). That is natural for an endpoint the stub already proxies
per request (a real question's revision, a real grading lookup). For an
endpoint the stub answers **without** calling Boost (the change feed, the
locally-generated templates, topics, and any all-synthetic batch), nothing
would otherwise check the token at all. So every stub endpoint, local or
proxied, **probes** Boost once per token: a cheap delivery or grading call,
cached briefly so a steady stream of requests from the same caller costs one
extra Boost call per cache window, not one per request.
"""

from dataclasses import dataclass
from hashlib import sha256

from fastapi import Header
from fastapi.exceptions import HTTPException

from boost_stub.upstream import UpstreamClient

PROBE_CACHE_SECONDS = 30.0
# A reserved id that can never be a real question: a grading-scoped token gets
# 404 (not found, but authorized); any other token gets 401/403.
_GRADING_PROBE_ID = "900000000"


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail={
            "status": 401,
            "code": "UNAUTHORIZED",
            "detail": "A valid Boost bearer token is required.",
            "requestId": None,
            "errors": None,
        },
        headers={"WWW-Authenticate": "Bearer"},
    )


def bearer_token(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _unauthorized()
    token = authorization[len("bearer ") :].strip()
    if not token:
        raise _unauthorized()
    return token


@dataclass(slots=True)
class TokenProbeCache:
    """Caches a positive probe result for ``PROBE_CACHE_SECONDS``; never caches a failure,
    so a token that starts working (e.g. after a Boost-side fix) is picked up immediately."""

    _ok_until: dict[str, float]

    def __init__(self) -> None:
        self._ok_until = {}

    @staticmethod
    def _key(scope: str, token: str) -> str:
        return f"{scope}:{sha256(token.encode()).hexdigest()}"

    def is_fresh(self, scope: str, token: str, now: float) -> bool:
        return self._ok_until.get(self._key(scope, token), 0.0) > now

    def mark_ok(self, scope: str, token: str, now: float) -> None:
        self._ok_until[self._key(scope, token)] = now + PROBE_CACHE_SECONDS


async def require_delivery_scope(
    upstream: UpstreamClient, cache: TokenProbeCache, token: str, *, now: float
) -> None:
    if cache.is_fresh("delivery", token, now):
        return
    response = await upstream.get("/v1/delivery/modules", token, {"page": 1, "pageSize": 1})
    if response.status_code != 200:
        raise _unauthorized()
    cache.mark_ok("delivery", token, now)


async def require_grading_scope(
    upstream: UpstreamClient, cache: TokenProbeCache, token: str, *, now: float
) -> None:
    if cache.is_fresh("grading", token, now):
        return
    response = await upstream.get(f"/v1/grading/questions/{_GRADING_PROBE_ID}/revisions/1", token)
    if response.status_code not in (200, 404):
        raise _unauthorized()
    cache.mark_ok("grading", token, now)
