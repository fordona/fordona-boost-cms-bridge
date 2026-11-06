"""Generate the Boost stub's question templates and synthetic questions (plan §4.5).

Run by hand; commit the output:

    BOOST_DELIVERY_TOKEN=... uv run python -m scripts.generate_stub_templates

Environment:

* ``BOOST_BASE_URL``: Boost's API origin (default ``https://boost-api.fordona.io``).
* ``BOOST_DELIVERY_TOKEN``: a Boost **delivery** service token (required; never a
  ``bst_`` token, which cannot call delivery routes).

Writes ``stub-data/templates.json`` and ``stub-data/synthetic.json``. Both
previous files are read first, so ids stay stable, versions bump only for what
changed, and a re-run on unchanged Boost data produces no diff.
"""

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from scripts.stub_data import boost_source
from scripts.stub_data.generator import Lesson, Output, Question, generate, render

DATA_DIR = Path(__file__).resolve().parent.parent / "stub-data"
TEMPLATES_FILE = "templates.json"
SYNTHETIC_FILE = "synthetic.json"

Source = Callable[[], tuple[list[Lesson], list[Question]]]


def _read(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return document


def run(source: Source, data_dir: Path) -> Output:
    lessons, questions = source()
    output = generate(
        lessons,
        questions,
        previous_templates=_read(data_dir / TEMPLATES_FILE),
        previous_synthetic=_read(data_dir / SYNTHETIC_FILE),
    )
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / TEMPLATES_FILE).write_bytes(render(output.templates))
    (data_dir / SYNTHETIC_FILE).write_bytes(render(output.synthetic))
    return output


def _boost_source() -> tuple[list[Lesson], list[Question]]:
    token = os.environ.get("BOOST_DELIVERY_TOKEN", "").strip()
    if not token:
        raise SystemExit("BOOST_DELIVERY_TOKEN is required (a Boost delivery service token)")
    base_url = os.environ.get("BOOST_BASE_URL", "https://boost-api.fordona.io").rstrip("/")
    with httpx.Client(
        base_url=base_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=httpx.Timeout(30.0),
    ) as http:
        return boost_source.fetch(http)


def _print_report(output: Output) -> None:
    report = output.report
    state = "changed" if report.changed else "unchanged"
    print(f"generation {output.templates['generation']} ({state})")
    print(f"lessons: {report.lessons}, templates: {report.templates}")
    print(f"topped-up lessons: {len(report.topped_up_lessons)} {report.topped_up_lessons}")
    print(f"skipped questions: {len(report.skipped_questions)}")
    for line in report.skipped_questions:
        print(f"  - {line}")
    if report.missing_block_types:
        print(
            "WARNING: synthetic.json does not demonstrate: "
            + ", ".join(report.missing_block_types)
            + " (no lesson needed a top-up)",
            file=sys.stderr,
        )


def main() -> None:
    _print_report(run(_boost_source, DATA_DIR))


if __name__ == "__main__":
    main()
