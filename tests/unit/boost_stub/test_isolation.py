"""Fast, Docker-free checks of the ``fordona_connect``/``boost_stub`` split (plan §4.5).

The real "does `docker build --target runtime` contain no boost_stub files"
check needs a Docker build; that's `tests/integration/test_docker_stages.py`
(marked ``integration``, like the rest of this repo's Docker-backed tests).
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_import_linter_contract_holds() -> None:
    # `lint-imports` is a console script (import-linter has no `-m` entry
    # point); it lives next to the interpreter running this test, in the same
    # venv, so it sees exactly the packages this test run sees.
    script = Path(sys.executable).parent / (
        "lint-imports.exe" if sys.platform == "win32" else "lint-imports"
    )
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell, test-only
        [str(script), "--config", "pyproject.toml"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_boost_stub_is_excluded_from_the_project_wheel() -> None:
    import tomllib

    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    packages = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    assert "src/boost_stub" not in packages
    assert "src/fordona_connect" in packages
