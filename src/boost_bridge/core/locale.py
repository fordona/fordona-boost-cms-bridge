"""Resolve the content locale for a request.

Order: explicit ``?locale=`` → ``Accept-Language`` (matched on primary subtag) →
configured default. Boost serves an exact locale without fallback, so the result
is always one of the locales Boost knows.
"""

from boost_bridge.core.config import SUPPORTED_LOCALES


class UnsupportedLocaleError(ValueError):
    def __init__(self, requested: str) -> None:
        super().__init__(f"Unsupported locale {requested!r}; expected one of {SUPPORTED_LOCALES}")
        self.requested = requested


_BY_PRIMARY_SUBTAG: dict[str, str] = {loc.split("-")[0].lower(): loc for loc in SUPPORTED_LOCALES}


def _parse_accept_language(header: str) -> list[str]:
    """Return language tags ordered by q-value (highest first), stable for ties."""
    weighted: list[tuple[float, int, str]] = []
    for index, part in enumerate(header.split(",")):
        tag, _, params = part.strip().partition(";")
        tag = tag.strip()
        if not tag or tag == "*":
            continue
        quality = 1.0
        for param in params.split(";"):
            key, _, value = param.strip().partition("=")
            if key == "q":
                try:
                    quality = float(value)
                except ValueError:
                    quality = 0.0
        if quality > 0:
            weighted.append((-quality, index, tag))
    return [tag for _, _, tag in sorted(weighted)]


def match_locale(tag: str) -> str | None:
    exact = {loc.lower(): loc for loc in SUPPORTED_LOCALES}
    lowered = tag.strip().lower()
    if lowered in exact:
        return exact[lowered]
    return _BY_PRIMARY_SUBTAG.get(lowered.split("-")[0])


def resolve_locale(explicit: str | None, accept_language: str | None, default: str) -> str:
    if explicit:
        matched = match_locale(explicit)
        if matched is None:
            # An explicit choice the client cannot get is an input error, not a
            # cue to silently serve another language.
            raise UnsupportedLocaleError(explicit)
        return matched
    if accept_language:
        for tag in _parse_accept_language(accept_language):
            matched = match_locale(tag)
            if matched:
                return matched
    return default
