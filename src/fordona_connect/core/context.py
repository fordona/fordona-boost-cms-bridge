"""Request-scoped context shared by logging, error rendering and the Boost client."""

from contextvars import ContextVar

CORRELATION_ID_HEADER = "X-Correlation-ID"

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def get_correlation_id() -> str | None:
    return correlation_id_var.get()


# The caller's verified Kinde access token, set by the auth dependency. The Boost
# client forwards it upstream when BOOST_AUTH_MODE=forward_learner_token. It lives
# in a contextvar so it reaches the client (and any background refresh task,
# which copies the context of the request that started it) without threading a
# secret through every service signature. It is never logged.
learner_token_var: ContextVar[str | None] = ContextVar("learner_token", default=None)
