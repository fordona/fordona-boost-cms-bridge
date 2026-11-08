"""Configuration and data discovery for the Boost content API v1 contract (plan §13).

The suite is a black-box check of a running server: the Boost stub in dev/CI,
Boost staging for the Boost owner's acceptance (§13.6). It never imports
``fordona_connect`` or ``boost_stub``, so it judges the server against the contract,
not against our own models.

Environment:

* ``CONTRACT_BOOST_BASE_URL``: the server under test. **Unset → the whole suite
  is skipped.**
* ``CONTRACT_DELIVERY_TOKEN`` / ``CONTRACT_GRADING_TOKEN``: required once a base
  URL is set. A half-configured run is refused rather than left to look green.
* ``CONTRACT_EXPIRED_CURSOR``: a cursor the server must reject with 410
  ``CURSOR_EXPIRED``. A black-box test cannot age a cursor by 30 days, so the
  operator of the server under test supplies one.
* ``CONTRACT_LOCALES``: the locales every grading explanation must carry
  (default ``sv-SE,en-GB``).

"Fails cleanly": nothing here performs I/O at fixture setup. Every request runs
inside a test, and a transport error or an unexpected response becomes a test
**failure** with a readable message, never a collection or setup error.
"""

import os
from collections.abc import Iterator

import httpx
import pytest

from tests.contract.boost_content_v1.support import (
    ContractClient,
    ContractConfig,
    Discovery,
    load_config,
)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    here = os.path.dirname(__file__)
    ours = [item for item in items if str(item.fspath).startswith(here)]
    for item in ours:
        item.add_marker(pytest.mark.contract)
    if ours and load_config() is None:
        skip = pytest.mark.skip(reason="CONTRACT_BOOST_BASE_URL is not set")
        for item in ours:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def contract_config() -> ContractConfig:
    config = load_config()
    assert config is not None  # collection skips every test when unset
    return config


@pytest.fixture(scope="session")
def client(contract_config: ContractConfig) -> Iterator[ContractClient]:
    with httpx.Client(
        base_url=contract_config.base_url, timeout=httpx.Timeout(15.0), follow_redirects=False
    ) as http:
        yield ContractClient(http, contract_config)


@pytest.fixture(scope="session")
def discovery(client: ContractClient) -> Discovery:
    return Discovery(client)
