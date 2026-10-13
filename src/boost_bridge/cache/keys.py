"""Cache keys for Boost requests.

``bridge:{schema}:{resource}:{locale}:{digest}``. Bumping ``CACHE_SCHEMA_VERSION``
invalidates every entry on deploy without a manual flush. Use it when the
*cached* representation changes. A mapper or response-schema change does not
need it, because payloads are re-mapped on every read.
"""

import hashlib
import json
from typing import Any

from boost_bridge.clients.boost.client import BoostRequest

CACHE_SCHEMA_VERSION = "v1"


def cache_key(request: BoostRequest[Any]) -> str:
    material = json.dumps(
        [request.path, request.locale, list(request.params)], separators=(",", ":")
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]
    return f"bridge:{CACHE_SCHEMA_VERSION}:{request.resource}:{request.locale}:{digest}"


def refresh_lock_key(key: str) -> str:
    return f"{key}:refresh-lock"
