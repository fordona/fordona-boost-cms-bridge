"""Runs the real §13 contract suite (P2.T1) against a live instance of the stub
(P2.T3), end to end over real HTTP — the acceptance check both tasks name.

Two real servers, each in its own thread: a small stand-in for Boost
(``fake_boost.py``, canned data from ``fixture_data.py``), and the stub app
pointed at it. The contract suite runs as a subprocess so its own pytest
session (and ``CONTRACT_*`` environment) never touches this one.

``test_expired_cursor_is_410`` is deselected: it needs an operator-supplied
cursor that is expired *while the feed's own history from 0 stays valid*,
which a single short-lived test server cannot produce (a real purge old enough
to expire a cursor would also purge the history the other feed tests read from
0). ``ChangeTracker``'s cursor-expiry logic has its own direct unit test
(``test_changes.py``).
"""

import os
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import uvicorn
from scripts.stub_data.generator import generate, render

from boost_stub.config import StubSettings
from boost_stub.main import create_app
from tests.unit.boost_stub import fixture_data
from tests.unit.boost_stub.fake_boost import DELIVERY_TOKEN, GRADING_TOKEN, build_fake_boost

REPO_ROOT = Path(__file__).resolve().parents[3]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _serve(app: object, port: int) -> uvicorn.Server:
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")  # type: ignore[arg-type]
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return server


def _wait_until_up(port: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            httpx.get(f"http://127.0.0.1:{port}/openapi.json", timeout=1.0)
            return
        except httpx.TransportError:
            time.sleep(0.1)
    pytest.fail(f"server on port {port} never came up")


def _stop(server: uvicorn.Server) -> None:
    server.should_exit = True


@pytest.fixture
def live_stub(tmp_path: Path) -> Iterator[int]:
    fake_boost_app = build_fake_boost(
        fixture_data.modules(),
        fixture_data.lessons(),
        fixture_data.questions(),
        fixture_data.grading(),
    )
    fake_boost_port = _free_port()
    fake_boost_server = _serve(fake_boost_app, fake_boost_port)
    _wait_until_up(fake_boost_port)

    output = generate(fixture_data.LESSONS, fixture_data.QUESTIONS)
    (tmp_path / "templates.json").write_bytes(render(output.templates))
    (tmp_path / "synthetic.json").write_bytes(render(output.synthetic))

    settings = StubSettings(
        stub_upstream_boost_url=f"http://127.0.0.1:{fake_boost_port}",
        stub_data_dir=tmp_path,
        stub_sqlite_path=str(tmp_path / "changes.sqlite3"),
        stub_poll_seconds=0.3,
        stub_visibility_lag_seconds=0.1,
        stub_poll_token=DELIVERY_TOKEN,
    )
    stub_app = create_app(settings)
    stub_port = _free_port()
    stub_server = _serve(stub_app, stub_port)
    _wait_until_up(stub_port)

    # Let at least one poll cycle (plus its visibility lag) land so the change
    # feed has content before the contract suite reads it.
    time.sleep(1.0)

    yield stub_port

    _stop(stub_server)
    _stop(fake_boost_server)


def test_contract_suite_is_green_against_the_stub(live_stub: int) -> None:
    env = {
        "CONTRACT_BOOST_BASE_URL": f"http://127.0.0.1:{live_stub}",
        "CONTRACT_DELIVERY_TOKEN": DELIVERY_TOKEN,
        "CONTRACT_GRADING_TOKEN": GRADING_TOKEN,
        "CONTRACT_LOCALES": "sv-SE,en-GB",
    }

    full_env = {**os.environ, **env}

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/contract/boost_content_v1",
            "-q",
            "-m",
            "contract",
            "-k",
            "not expired_cursor",
            "-p",
            "no:cacheprovider",
        ],
        cwd=REPO_ROOT,
        env=full_env,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, (
        f"contract suite failed against the live stub\n--- stdout ---\n{result.stdout}"
        f"\n--- stderr ---\n{result.stderr[-4000:]}"
    )
    assert "error" not in result.stdout.lower()
