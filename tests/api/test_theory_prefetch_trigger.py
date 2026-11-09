"""End-to-end wiring: a home response's learningPathEtag triggers a background
prefetch when CONTENT_PREFETCH_ON_RELEASE=true (Plan §9.1/§9.4, P6.T7), and
does nothing at all when it's off (the default).
"""

import asyncio

import respx

from tests.conftest import BOOST, Harness
from tests.factories import home_payload, lesson_payload, page_payload


@respx.mock
async def test_prefetch_disabled_by_default_makes_no_catalogue_calls(harness: Harness) -> None:
    harness.theory.set("get_home", home_payload())
    lessons_route = harness.boost.get(f"{BOOST}/v1/delivery/lessons")

    response = await harness.client.get("/v1/home", headers=harness.auth())
    await asyncio.sleep(0.05)

    assert response.status_code == 200
    assert lessons_route.call_count == 0


@respx.mock
async def test_prefetch_enabled_warms_the_catalogue_once_per_release(
    harness_factory: object,
) -> None:
    async with harness_factory(  # type: ignore[operator]
        content_prefetch_on_release=True, content_prefetch_batch_delay_seconds=0
    ) as harness:
        harness: Harness
        harness.theory.set("get_home", home_payload())
        lessons_route = harness.boost.get(f"{BOOST}/v1/delivery/lessons").respond(
            json=page_payload([lesson_payload(lesson_id="10")], page_size=250)
        )
        harness.boost.get(f"{BOOST}/v1/delivery/lessons/10/revisions/2").respond(
            json=lesson_payload(lesson_id="10")
        )
        harness.boost.get(f"{BOOST}/v1/delivery/questions").respond(
            json=page_payload([], page_size=250)
        )

        first = await harness.client.get("/v1/home", headers=harness.auth())
        await asyncio.sleep(0.1)
        second = await harness.client.get("/v1/home", headers=harness.auth())
        await asyncio.sleep(0.1)

        assert first.status_code == 200
        assert second.status_code == 200
        # Once per locale (sv-SE, en-GB) on the *first* request only — the second
        # request sees the same release id, already claimed.
        assert lessons_route.call_count == 2
