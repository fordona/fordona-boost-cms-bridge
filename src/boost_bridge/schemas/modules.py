from datetime import datetime

from pydantic import Field

from boost_bridge.schemas.common import ContentId, Localized


class Module(Localized):
    id: ContentId
    version: str | None
    title: str | None
    slug: str | None
    description: str | None
    icon_url: str | None
    cover_image_url: str | None
    updated_at: datetime | None = Field(default=None)
