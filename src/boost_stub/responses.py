"""RFC-7807-ish errors (Boost's own shape, §13.1) and cache headers (§13.5)."""

import hashlib
import json
from typing import Any

from fastapi import Request
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse, Response


def boost_problem(status: int, code: str, detail: str, request_id: str = "stub-0") -> HTTPException:
    """Boost's error envelope: ``{ status, code, detail, requestId, errors }``."""
    return HTTPException(
        status_code=status,
        detail={
            "status": status,
            "code": code,
            "detail": detail,
            "requestId": request_id,
            "errors": None,
        },
    )


def etag_for(body: Any) -> str:
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
    return f'"{digest[:32]}"'


def list_response(request: Request, body: dict[str, Any]) -> Response:
    """List endpoints: ``ETag``; a matching ``If-None-Match`` is a 304 (§13.5)."""
    etag = etag_for(body)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return JSONResponse(body, headers={"ETag": etag})


def immutable_response(body: dict[str, Any]) -> JSONResponse:
    """Revision endpoints: ``Cache-Control: public, max-age=31536000, immutable`` (§13.5)."""
    return JSONResponse(
        body,
        headers={
            "ETag": etag_for(body),
            "Cache-Control": "public, max-age=31536000, immutable",
        },
    )
