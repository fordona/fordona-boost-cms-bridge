"""Classified Boost failures.

The client never raises raw httpx errors. Every failure ends up as one of these
four kinds, because each one calls for a different reaction:

- ``BoostNotFound``: the content does not exist or is unpublished. Purge any copy.
- ``BoostUnavailable`` / ``BoostTimeout``: a transient problem. Serve the snapshot if we have one.
- ``BoostMisconfigured``: Boost rejected *our* credential or request. This is our bug,
  so it is alerted on and never blamed on the learner.
"""


class BoostError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: str | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.request_id = request_id


class BoostNotFound(BoostError):  # noqa: N818 - domain name reads better than *Error
    pass


class BoostMisconfigured(BoostError):  # noqa: N818
    pass


class BoostUnavailable(BoostError):  # noqa: N818
    def __init__(
        self,
        message: str,
        *,
        retry_after: float | None = None,
        status: int | None = None,
        code: str | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message, status=status, code=code, request_id=request_id)
        self.retry_after = retry_after


class BoostTimeout(BoostError):  # noqa: N818
    pass
