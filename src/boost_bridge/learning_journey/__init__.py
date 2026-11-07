"""Personalized Learning Journey — a temporary, BFF-only stand-in.

Serves a fixed mock dataset (10 milestones, 39 challenges, 381 questions) entirely
from this BFF's own Postgres: no calls to fordona-engine, no calls to Boost. Approved
as a stopgap while the Boost/engine/mobile content-model mismatch is resolved — see
``learning_journey_api_spec_v1.md`` for the full contract this package implements.

Deliberately isolated from the rest of this codebase's conventions: its own response
envelope (``{"success": ..., "data"/"error": ...}``, snake_case fields) and its own
error hierarchy, so the whole package (routes, schemas, errors, migrations) can be
deleted as a unit once real content replaces it.
"""
