"""§13.2 #6 and §13.4: grading revisions, batch, all locales.

**Corrected 2026-11-06, confirmed against a live boost-api-dev.fordona.dev response:** this
endpoint is a single call with no ``locale`` parameter at all, returning every locale's
explanation in one response (``shared.correctOptionId`` plus ``translations.{locale}.explanation``)
— not "one locale at a time" as this file previously assumed. That wrong assumption meant this
code called upstream once per configured locale and read the result from flat
``correctOptionId``/``explanation`` fields that don't exist in the real response; both are fixed
in the same pass as fordona-engine's matching ``BoostGradingRevision`` fix.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Query

from boost_stub.data import synthetic_grading_item
from boost_stub.deps import GradingToken, Services
from boost_stub.responses import boost_problem
from boost_stub.routes.content import parse_refs
from boost_stub.transforms import explanation_blocks
from boost_stub.upstream import UpstreamError

router = APIRouter(prefix="/grading", tags=["grading"])


async def _real_items(
    services: Services, token: str, refs: list[tuple[str, str]]
) -> dict[tuple[str, str], dict[str, Any]]:
    by_ref: dict[tuple[str, str], dict[str, Any]] = {}
    paths = [f"/v1/grading/questions/{qid}/revisions/{version}" for qid, version in refs]
    try:
        results = await services.upstream.get_many(paths, token)
    except UpstreamError as exc:
        if exc.response.status_code in (401, 403):
            raise boost_problem(
                exc.response.status_code, "UNAUTHORIZED", "Grading token rejected"
            ) from exc
        raise
    for (question_id, version), path in zip(refs, paths, strict=True):
        result = results[path]
        if result is None:
            continue
        shared = result.get("shared") or {}
        translations_out: dict[str, Any] = {}
        for locale, translation in (result.get("translations") or {}).items():
            translations_out[locale] = {
                "explanation": explanation_blocks(
                    (translation or {}).get("explanation"), source=f"grading:{question_id}:{locale}"
                )
            }
        by_ref[(question_id, version)] = {
            "id": question_id,
            "version": version,
            "shared": {"correctOptionId": shared.get("correctOptionId")},
            "translations": translations_out,
        }
    return by_ref


# --- questions: singular grading revision (what fordona-engine's BoostContentClient actually
# calls — the batch endpoint below is a dead route, kept only because real Boost's own batch
# route 404s the same way; confirmed 2026-11-05, see BoostContentClient's own Javadoc) ---


@router.get("/questions/{question_id}/revisions/{version}")
async def grading_revision(
    question_id: str, version: str, services: Services, token: GradingToken
) -> dict[str, Any]:
    synthetic = services.data.current.synthetic_questions.get(question_id)
    if synthetic is not None:
        if synthetic["version"] != version:
            raise boost_problem(
                404, "QUESTION_NOT_FOUND", f"Question {question_id}:{version} not found"
            )
        return synthetic_grading_item(synthetic)

    by_ref = await _real_items(services, token, [(question_id, version)])
    entry = by_ref.get((question_id, version))
    if entry is None:
        raise boost_problem(
            404, "QUESTION_NOT_FOUND", f"Question {question_id}:{version} not found"
        )
    return entry


@router.get("/questions/revisions")
async def grading_revisions_batch(
    services: Services, token: GradingToken, refs: Annotated[str, Query()]
) -> dict[str, Any]:
    parsed = parse_refs(refs)
    items: list[dict[str, Any]] = []
    missing: list[str] = []
    real_refs: list[tuple[str, str]] = []

    for question_id, version in parsed:
        synthetic = services.data.current.synthetic_questions.get(question_id)
        if synthetic is None:
            real_refs.append((question_id, version))
        elif synthetic["version"] == version:
            items.append(synthetic_grading_item(synthetic))
        else:
            missing.append(f"{question_id}:{version}")

    if real_refs:
        by_ref = await _real_items(services, token, real_refs)
        for ref in real_refs:
            if ref in by_ref:
                items.append(by_ref[ref])
            else:
                missing.append(f"{ref[0]}:{ref[1]}")

    return {"items": items, "missing": missing}
