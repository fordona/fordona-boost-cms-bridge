"""FastAPI dependency providers."""

import time
from typing import Annotated

from fastapi import Depends, Query, Request

from boost_stub.auth import bearer_token, require_delivery_scope, require_grading_scope
from boost_stub.container import StubServices


def get_services(request: Request) -> StubServices:
    services: StubServices = request.app.state.services
    return services


async def delivery_token(
    services: Annotated[StubServices, Depends(get_services)],
    token: Annotated[str, Depends(bearer_token)],
) -> str:
    await require_delivery_scope(services.upstream, services.probe_cache, token, now=time.time())
    return token


async def grading_token(
    services: Annotated[StubServices, Depends(get_services)],
    token: Annotated[str, Depends(bearer_token)],
) -> str:
    await require_grading_scope(services.upstream, services.probe_cache, token, now=time.time())
    return token


Services = Annotated[StubServices, Depends(get_services)]
DeliveryToken = Annotated[str, Depends(delivery_token)]
GradingToken = Annotated[str, Depends(grading_token)]
LocaleParam = Annotated[str, Query(description="Content locale.")]
