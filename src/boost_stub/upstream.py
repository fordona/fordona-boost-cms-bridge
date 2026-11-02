"""A thin client for today's Boost (design doc §2), used only to build the stub.

Forwards the caller's own bearer token **unchanged** on every call (plan §4.5:
"so token scopes stay real: the BFF's delivery token can't read grading through
the stub any more than through Boost"). No retries, no caching: the stub polls
and fans out on its own schedule, and the engine/BFF caches already absorb the
request rate (plan §4.5 "Expected load").
"""

import asyncio
from collections.abc import Iterable, Sequence
from typing import Any

import httpx

from boost_stub.logging import get_logger

log = get_logger(__name__)

PAGE_SIZE = 250  # Boost's documented maximum


class UpstreamError(RuntimeError):
    """Today's Boost returned something the stub cannot proxy."""

    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        super().__init__(
            f"{response.request.method} {response.request.url} -> {response.status_code}"
        )


class UpstreamClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def get(
        self, path: str, token: str, params: dict[str, Any] | None = None
    ) -> httpx.Response:
        return await self._http.get(
            path, params=params, headers={"Authorization": f"Bearer {token}"}
        )

    async def get_json(
        self, path: str, token: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        response = await self.get(path, token, params)
        if response.status_code != 200:
            raise UpstreamError(response)
        body: dict[str, Any] = response.json()
        return body

    async def list_all(self, path: str, token: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Walks every page of a Boost list endpoint (used for the change poll)."""
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            body = await self.get_json(path, token, {**params, "page": page, "pageSize": PAGE_SIZE})
            page_items = body.get("items", [])
            items.extend(page_items)
            if not page_items or page * PAGE_SIZE >= int(body.get("total", 0)):
                return items
            page += 1

    async def get_many(
        self, paths: Iterable[str], token: str, params: dict[str, Any] | None = None
    ) -> dict[str, dict[str, Any] | None]:
        """Fans a batch out to Boost's single-item endpoints in parallel (plan §4.5).

        ``None`` for a path that 404s; any other failure propagates.
        """

        async def one(path: str) -> tuple[str, dict[str, Any] | None]:
            response = await self.get(path, token, params)
            if response.status_code == 404:
                return path, None
            if response.status_code != 200:
                raise UpstreamError(response)
            return path, response.json()

        results = await asyncio.gather(*(one(path) for path in paths))
        return dict(results)


def chunked(refs: Sequence[tuple[str, str]], size: int) -> Iterable[Sequence[tuple[str, str]]]:
    for start in range(0, len(refs), size):
        yield refs[start : start + size]
