# fordona-boost-cms-bridge

The Theory content API for the Fordona Theory App. It reads published **modules**, **lessons** (the app calls them "chapters") and **questions** from the Boost CMS (`boost.fordona.io`) and serves them to the frontend. It handles authentication, caching, failure handling and a stable, documented contract.

The design, decisions and open risks are in **[docs/design.md](docs/design.md)**. Read it before changing behaviour.

**Stack:** Python 3.12 · FastAPI · httpx (async) · Redis · PostgreSQL (SQLAlchemy 2 async + Alembic) · structlog · uv

## Layout

```
src/boost_bridge/
  main.py            app factory + lifespan
  container.py       composition root: builds clients, cache, DB, verifier
  api/               routers, dependencies, OpenAPI error docs
  services/          use cases, upstream→API mappers, read-through cache, sequencer extension point
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
cp .env.example .env            # then fill in BOOST_DELIVERY_TOKEN and the KINDE_* values
uv sync
docker compose up -d postgres redis
uv run alembic upgrade head
uv run uvicorn boost_bridge.main:app --reload
```

- Interactive docs are at http://localhost:8000/docs; the readiness probe is at http://localhost:8000/health/ready.
- To try it without Kinde, set `AUTH_ENABLED=false`. This is only allowed with `APP_ENV=local`; in any other environment the service refuses to start.
- To run the whole stack in containers instead: `docker compose --profile app up --build`.

### Example

```bash
curl -H "Authorization: Bearer $TOKEN" "http://localhost:8000/v1/modules?locale=en-GB"
curl -H "Authorization: Bearer $TOKEN" "http://localhost:8000/v1/lessons/10/questions"
```

## API at a glance

| Route | Purpose |
|---|---|
| `GET /v1/modules` · `/v1/modules/{moduleId}` · `/v1/modules/{moduleId}/lessons` | Theory modules and their lessons |
| `GET /v1/lessons` · `/v1/lessons/{lessonId}` | Lessons (chapters) with HTML content and resources |
| `GET /v1/lessons/{lessonId}/questions` | The lesson's full question set, ordered by the sequencer |
| `GET /v1/questions` · `/v1/questions/{questionId}` · `/v1/questions/{questionId}/revisions/{version}` | Questions (answer-free) |
| `GET /health/live` · `/health/ready` | Probes (no auth) |

Conventions:

- **Locale.** Set it with `?locale=sv-SE|en-GB` or the `Accept-Language` header. The default is `sv-SE`. The locale that was served comes back in `Content-Language`.
- **Errors** use RFC 7807 `application/problem+json`, with `errorCode` and `correlationId`.
- **`X-Content-Stale: true`** means Boost was unavailable and the response came from the last-known-good copy.
- **Correlation.** Send `X-Correlation-ID` to trace a request through to Boost. One is generated if you don't send it.

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
- **Configuration** is all environment variables, documented in `.env.example`. Store `BOOST_DELIVERY_TOKEN` as a secret.

Dependencies are pinned in `uv.lock`, the only lockfile; there is no `requirements.txt`. If a platform needs one, generate it with `uv export --no-dev --format requirements-txt`.

## Status

This is Phase 1: content delivery only. The models of Boost's delivery payloads are **inferred**, because Boost's OpenAPI document leaves those responses untyped. They still need to be checked against a real payload. See the risks table in [docs/design.md §12](docs/design.md#12-risks-and-open-questions).
