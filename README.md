# fordona-boost-cms-bridge

The backend for frontend (BFF) of the Fordona Theory App, being rebuilt for the theory first shipment. It will compose fordona-engine's lesson, attempt and progress decisions with answer-free content from the Boost CMS (`boost-api.fordona.io`; [docs](https://boost.fordona.io/api-docs)).

The plan, the task tracker and the progress log are in **[docs/](docs/)** (`fordona-theory-first-shipment-architecture.md`, `BFF_IMPLEMENTATION_PROGRESS.md`, `PROGRESS__STATUS.md`). `docs/design.md` describes the earlier Phase 1 design and is outdated. Developer conventions are in [CLAUDE.md](CLAUDE.md).

**Stack:** Python 3.12 · FastAPI · httpx (async) · Redis · PostgreSQL (SQLAlchemy 2 async + Alembic) · structlog · uv

## Layout

```
src/boost_bridge/
  main.py            app factory + lifespan
  container.py       composition root: builds clients, cache, DB, verifier
  api/               routers, dependencies, OpenAPI error docs
  services/          read-through content cache (rewired by the public API in P6)
  clients/boost/     typed async Boost delivery client
  cache/             fail-open Redis wrapper, cache keys
  db/                snapshot table, repository, engine
  schemas/           API (frontend) Pydantic models
  core/              config, logging, middleware, errors, auth, locale, clock
migrations/          Alembic
tests/               unit/ · api/ · integration/ (Docker)
```

## Running locally

Prerequisites: [uv](https://docs.astral.sh/uv/) and Docker (for Postgres and Redis).

```bash
cp .env.example .env            # Kinde + Boost values are pre-filled for the fordona tenant
uv sync
docker compose up -d postgres redis
uv run alembic upgrade head
uv run uvicorn boost_bridge.main:app --reload
```

- Interactive docs are at http://localhost:8000/docs; the readiness probe is at http://localhost:8000/health/ready.
- To try it without Kinde, set `AUTH_ENABLED=false`. This is only allowed with `APP_ENV=local`; in any other environment the service refuses to start.
- To run the whole stack in containers instead: `docker compose --profile app up --build`.

## API at a glance

| Route | Purpose |
|---|---|
| `GET /health/live` · `/health/ready` | Probes (no auth) |

That is the whole surface until the public theory API ships (plan §7.3, tracker P6). The Phase 1
catalogue routes (`/v1/modules*`, `/v1/lessons*`, `/v1/questions*`) were retired: they served the
whole question bank and paid theory with no entitlement or sequencing check (plan §15, R-8, R-11).

Conventions:

- **Locale.** Set it with `?locale=sv-SE|en-GB` or the `Accept-Language` header. The default is `sv-SE`. The locale that was served comes back in `Content-Language`.
- **Errors** use RFC 7807 `application/problem+json`, with `errorCode` and `correlationId`.
- **Correlation.** Send `X-Correlation-ID` to trace a request. One is generated if you don't send it.

## Verifying against live Boost

The delivery models still need checking against a real payload (design doc §12, risk 2). You need a Kinde access token for **Boost's audience** (`https://boost-api.fordona.io/`), for example from the Theory App's sign-in.

```bash
export TOKEN=...   # Boost-audience Kinde access token; never commit or paste it anywhere shared
curl -s -H "Authorization: Bearer $TOKEN" "https://boost-api.fordona.io/v1/delivery/lessons?locale=sv-SE&pageSize=1"
```

Compare the first response against `src/boost_bridge/clients/boost/models.py`. Check especially the form of `assetBaseUrl` and whether `availableLocales` and `updatedAt` are present.

## Tests and checks

```bash
uv run pytest                     # unit + API tests; integration tests auto-skip without Docker
uv run pytest -m integration      # Postgres repository tests (needs a running Docker daemon)
uv run pytest --cov=boost_bridge --cov-report=term-missing
uv run ruff check . && uv run ruff format --check . && uv run mypy src
```

The API tests run the real stack (routers → service → cache → Boost client → httpx). Only the edges are replaced: Boost and Kinde are mocked with respx, and Redis is fakeredis.

## Deployment (Railway)

- **Build** with the `Dockerfile`, which is multi-stage, uses `uv sync --frozen` and runs as a non-root user.
- **Pre-deploy command:** `alembic upgrade head`. Migrations never run at app start.
- **Healthcheck path:** `/health/ready`.
- **Scaling:** run one uvicorn worker per container and add replicas to scale.
- **Configuration** is all environment variables, documented in `.env.example`. By default (`BOOST_AUTH_MODE=forward_learner_token`) there is no Boost secret to manage. If you switch to `service_token`, store `BOOST_DELIVERY_TOKEN` as a secret.

Dependencies are pinned in `uv.lock`, the only lockfile; there is no `requirements.txt`. If a platform needs one, generate it with `uv export --no-dev --format requirements-txt`.

## Status

This is Phase 1: content delivery only. The models of Boost's delivery payloads are **inferred**, because Boost's OpenAPI document leaves those responses untyped. They still need to be checked against a real payload. See the risks table in [docs/design.md §12](docs/design.md#12-risks-and-open-questions).
