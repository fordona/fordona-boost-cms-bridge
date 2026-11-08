"""The runtime Docker image, built for real.

Needs a running Docker daemon; skips itself otherwise, like the rest of this
repo's Docker-backed tests.
"""

import subprocess
from pathlib import Path

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
    # No --target: the runtime stage is the Dockerfile's last, so a plain build
    # (which is what Dokploy runs) must produce it.
    result = _run("docker", "build", "-t", tag, ".")
    assert result.returncode == 0, result.stdout + result.stderr
    return tag


def test_runtime_image_contains_fordona_connect(runtime_image: str) -> None:
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
