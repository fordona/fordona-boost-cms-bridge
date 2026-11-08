"""The Boost stub: serves the §13 contract over today's Boost (plan §4.5).

A separate deployable, dev and staging only. It never imports ``fordona_connect``,
and ``fordona_connect`` never imports it (enforced by import-linter, see
``pyproject.toml``) — the two share nothing but the HTTP contract.
"""

__version__ = "0.1.0"
