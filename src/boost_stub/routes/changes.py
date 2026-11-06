"""§13.2 #1, §13.3: the change feed, served from the stub's own SQLite tracker."""

import time
from typing import Annotated

from fastapi import APIRouter, Query, Response

from boost_stub.changes import CursorExpiredError
from boost_stub.deps import DeliveryToken, Services
from boost_stub.responses import boost_problem

router = APIRouter(prefix="/delivery", tags=["changes"])


@router.get("/changes")
async def changes(
    services: Services,
    _: DeliveryToken,
    response: Response,
    after: Annotated[str, Query()] = "0",
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
) -> dict[str, object]:
    try:
        after_seq = int(after)
    except ValueError as exc:
        raise boost_problem(422, "INVALID_CURSOR", "after must be a decimal integer") from exc
    if after_seq < 0:
        raise boost_problem(422, "INVALID_CURSOR", "after must not be negative")

    try:
        page = services.tracker.feed(
            after_seq,
            limit,
            now=time.time(),
            visibility_lag_seconds=services.settings.stub_visibility_lag_seconds,
        )
    except CursorExpiredError as exc:
        raise boost_problem(
            410, "CURSOR_EXPIRED", "The cursor is older than the retention window"
        ) from exc

    response.headers["Cache-Control"] = "no-store"
    return {
        "items": [
            {
                "seq": row.seq,
                "entityType": row.entity_type,
                "id": row.id,
                "version": row.version,
                "change": row.change,
                "publishedAt": row.published_at,
            }
            for row in page.items
        ],
        "nextCursor": page.next_cursor,
        "hasMore": page.has_more,
    }
