"""§13.2 #6 and §13.4: grading revisions, batch, all locales.

Today's Boost grading endpoint (design doc §2: ``/v1/grading/questions/{id}/
revisions/{version}``) is presumed to answer one locale at a time, like
delivery. The stub therefore calls it once **per configured locale** for each
real ref and assembles the §13.4 multi-locale ``explanation`` map; a locale
missing from the result stays missing (visible content gaps are a sign to fix
Boost, not to paper over).
"""

from typing import Annotated, Any

from fastapi import APIRouter, Query

from boost_stub.config import SUPPORTED_LOCALES
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
    for locale in SUPPORTED_LOCALES:
        try:
            results = await services.upstream.get_many(paths, token, {"locale": locale})
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
            entry = by_ref.setdefault(
                (question_id, version),
                {
                    "id": question_id,
                    "version": version,
                    "correctOptionId": result.get("correctOptionId"),
                    "explanation": {},
                },
            )
            entry["explanation"][locale] = explanation_blocks(
                result.get("explanation"), source=f"grading:{question_id}:{locale}"
            )
    return by_ref


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
