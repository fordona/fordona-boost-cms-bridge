"""§13.2 #7, §13.4: a module's topic vocabulary.

Derived, not authored: the stub injects ``topicKey = lesson-{lessonId}`` on every
question (plan §4.5), so the vocabulary is one topic per lesson that has a
published template in the module — the same set the injection draws from.
"""

from typing import Annotated

from fastapi import APIRouter, Query

from boost_stub.deps import DeliveryToken, Services
from boost_stub.transforms import topic_vocabulary

router = APIRouter(prefix="/delivery/topics", tags=["topics"])


@router.get("")
async def list_topics(
    services: Services,
    _: DeliveryToken,
    module_id: Annotated[str, Query(alias="moduleId")],
) -> dict[str, object]:
    lesson_ids = services.data.current.templates_by_module.get(module_id, [])
    return {"items": topic_vocabulary(module_id, [t["lessonId"] for t in lesson_ids])}
