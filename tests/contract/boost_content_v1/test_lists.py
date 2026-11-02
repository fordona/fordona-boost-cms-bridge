"""§13.2 (existing lists) and §13.5: the multi-value ``id=`` filter and list ETags."""

import pytest

from tests.contract.boost_content_v1.assertions import assert_page
from tests.contract.boost_content_v1.support import DEFAULT_LOCALE, ContractClient, describe

LISTS = [
    "/v1/delivery/modules",
    "/v1/delivery/lessons",
    "/v1/delivery/questions",
    "/v1/delivery/question-templates",
]
FILTERABLE = LISTS[:3]


def _first_ids(client: ContractClient, path: str, count: int) -> list[str]:
    items = assert_page(
        client.get_json(path, {"page": 1, "pageSize": count, "locale": DEFAULT_LOCALE})
    )
    assert len(items) >= count, f"precondition: {path} has fewer than {count} items"
    return [str(item["id"]) for item in items[:count]]


@pytest.mark.parametrize("path", FILTERABLE)
def test_multi_value_id_filter_returns_exactly_those_ids(client: ContractClient, path: str) -> None:
    ids = _first_ids(client, path, 2)

    body = client.get_json(path, {"id": ",".join(reversed(ids)), "locale": DEFAULT_LOCALE})

    items = assert_page(body)
    assert sorted(str(i["id"]) for i in items) == sorted(ids)
    assert body["total"] == len(ids)


@pytest.mark.parametrize("path", LISTS)
def test_list_sends_an_etag(client: ContractClient, path: str) -> None:
    response = client.get(path, {"page": 1, "pageSize": 5, "locale": DEFAULT_LOCALE})

    assert response.status_code == 200, describe(response)
    assert response.headers.get("ETag"), f"{path} sent no ETag"


@pytest.mark.parametrize("path", LISTS)
def test_list_revalidates_with_304(client: ContractClient, path: str) -> None:
    params: dict[str, str | int] = {"page": 1, "pageSize": 5, "locale": DEFAULT_LOCALE}
    first = client.get(path, params)
    assert first.status_code == 200, describe(first)
    etag = first.headers.get("ETag")
    assert etag, f"{path} sent no ETag"

    second = client.get(path, params, headers={"If-None-Match": etag})

    assert second.status_code == 304, describe(second)
