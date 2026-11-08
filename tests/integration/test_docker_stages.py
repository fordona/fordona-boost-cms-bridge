"""The runtime/boost-stub Docker stage split, built for real (plan §4.5, P2.T3).

Needs a running Docker daemon; skips itself otherwise, like the rest of this
repo's Docker-backed tests.
"""

import subprocess
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]


def _docker_available() -> bool:
    try:
        import docker

        docker.from_env().ping()
    except Exception:
        return False
    return True


def _run(*args: str, timeout: float = 300) -> subprocess.CompletedProcess[str]:
    # Docker's build output includes non-ASCII box-drawing characters that the
    # default locale codec (cp1252 on Windows) cannot decode.
    return subprocess.run(  # noqa: S603 - fixed argv, no shell, test-only
        args,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


@pytest.fixture(scope="module")
def runtime_image() -> str:
    if not _docker_available():
        pytest.skip("Docker is not available")
    tag = "fordona-connect-test:runtime"
    result = _run("docker", "build", "--target", "runtime", "-t", tag, ".")
    assert result.returncode == 0, result.stdout + result.stderr
    return tag


@pytest.fixture(scope="module")
def boost_stub_image() -> str:
    if not _docker_available():
        pytest.skip("Docker is not available")
    tag = "fordona-connect-test:boost-stub"
    result = _run("docker", "build", "--target", "boost-stub", "-t", tag, ".")
    assert result.returncode == 0, result.stdout + result.stderr
    return tag


def test_runtime_image_contains_no_boost_stub_files(runtime_image: str) -> None:
    # The container's own (non-root) user can't read every directory under
    # `/` (e.g. /root, /var/cache/apt): `find` exits non-zero for those
    # "Permission denied" lines, which is expected and not what this checks.
    # What matters is that no matching path was printed at all.
    result = _run(
        "docker",
        "run",
        "--rm",
        "--entrypoint",
        "find",
        runtime_image,
        "/",
        "-iname",
        "*boost_stub*",
    )
    assert result.stdout.strip() == "", f"boost_stub files found in runtime image:\n{result.stdout}"


def test_runtime_image_still_contains_fordona_connect(runtime_image: str) -> None:
    result = _run(
        "docker",
        "run",
        "--rm",
        "--entrypoint",
        "python",
        runtime_image,
        "-c",
        "import fordona_connect; print('ok')",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ok" in result.stdout


def test_boost_stub_image_runs_and_serves(boost_stub_image: str) -> None:
    container = "fordona-boost-stub-test"
    _run("docker", "rm", "-f", container)
    try:
        up = _run(
            "docker",
            "run",
            "-d",
            "--name",
            container,
            "-p",
            "18099:8080",
            "-e",
            "STUB_UPSTREAM_BOOST_URL=http://127.0.0.1:1",
            boost_stub_image,
        )
        assert up.returncode == 0, up.stdout + up.stderr

        response = None
        for _ in range(30):
            try:
                response = httpx.get("http://127.0.0.1:18099/openapi.json", timeout=1.0)
                break
            except httpx.TransportError:
                import time

                time.sleep(1.0)
        logs = _run("docker", "logs", container).stdout
        assert response is not None, logs
        assert response.status_code == 200, logs
    finally:
        _run("docker", "rm", "-f", container)
