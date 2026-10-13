"""Request-scoped context shared by logging, error rendering and the Boost client."""

from contextvars import ContextVar

CORRELATION_ID_HEADER = "X-Correlation-ID"

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def get_correlation_id() -> str | None:
    return correlation_id_var.get()
