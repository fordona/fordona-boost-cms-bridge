"""Log rendering never leaks secrets."""

import io
import json
import logging
from collections.abc import Iterator

import pytest
import structlog

from fordona_connect.core.logging import configure_logging, get_logger

SECRET = "internal-token-value"


@pytest.fixture
def json_output() -> Iterator[io.StringIO]:
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    configure_logging(fmt="json")
    buffer = io.StringIO()
    handler = root.handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    handler.setStream(buffer)
    yield buffer
    structlog.reset_defaults()
    root.handlers[:] = handlers
    root.setLevel(level)


def fail_with_a_secret_local() -> None:
    headers = {"X-Fordona-Internal-Token": SECRET}
    raise RuntimeError(f"request failed with {len(headers)} header")


def test_tracebacks_do_not_include_local_variables(
    json_output: io.StringIO,
) -> None:
    log = get_logger("tests.logging")
    try:
        fail_with_a_secret_local()
    except RuntimeError:
        log.exception("call_failed")

    output = json_output.getvalue()
    record = json.loads(output.strip().splitlines()[-1])
    assert record["event"] == "call_failed"
    assert record["exception"][0]["exc_type"] == "RuntimeError"
    assert SECRET not in output
