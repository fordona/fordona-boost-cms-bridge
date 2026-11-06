"""Engine-originated errors.

Unlike Boost's client (whose failures the BFF classifies into its own generic
messages — ``BoostNotFound``/``BoostUnavailable``/...), an engine failure
usually already carries the exact RFC 7807 body the end client should see:
the engine's own ``GlobalExceptionHandler`` renders the identical shape this
service's ``core/errors.py`` does. Plan §7.4: "engine errors are passed
through unchanged (status, errorCode, detail, correlationId)." The
``correlationId`` matches by construction — the same id this service
generated for the request is the one forwarded to the engine on this call —
so only ``status``/``errorCode``/``detail``/``type`` need copying here.

A connection failure, a timeout, or a body with no RFC 7807 shape to pass
through (e.g. a raw 403 from the engine's own internal-token filter, which
runs before Spring's exception handling ever sees the request) is not this
error: it falls back to the existing ``Upstream*Error`` hierarchy in
``core/errors``, the same one Boost failures resolve to.
"""

from boost_bridge.core.errors import AppError

_TYPE_BASE_PREFIX = "https://fordona.io/errors/"


def _strip_type_base(type_path: str) -> str:
    """fordona-engine renders the same ``https://fordona.io/errors/{path}`` base
    this service's own ``problem_body`` does (``core/errors._TYPE_BASE``), so
    stripping it back to a bare path lets the passthrough render through the
    same ``problem_body`` helper without double-prefixing.
    """
    if type_path.startswith(_TYPE_BASE_PREFIX):
        return type_path[len(_TYPE_BASE_PREFIX) :]
    return type_path


class EnginePassthroughError(AppError):
    """An engine RFC 7807 error, rendered with the engine's own fields unchanged."""

    def __init__(self, *, status: int, error_code: str, detail: str, type_path: str) -> None:
        self.status_code = status
        self.error_code = error_code
        self.type_path = _strip_type_base(type_path) if type_path else "engine/error"
        super().__init__(detail)
