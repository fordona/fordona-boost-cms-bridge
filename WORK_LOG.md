# Work Log — Theory Content API (Phase 1)

This document records what was built in this repository, why, and where to find it. It is a
project history and orientation guide, not a replacement for **[docs/design.md](docs/design.md)**
(the authoritative design doc for Ticket 01) or **[README.md](README.md)** (how to run, test and
deploy). Read those two first; this file explains how the codebase got to its current shape and
every non-obvious decision behind it.

---

## 1. Origin and scope

Ashen (senior engineer) asked for a Python backend exposing the Theory App's content — modules,
lessons ("chapters") and questions — by reading them from **Boost**, Fordona's CMS, and serving a
stable API to the frontend. Two tickets:

- **Ticket 01** — a production-ready backend with a design document.
- **Ticket 02** — expose all of Boost's learner-facing content through it.

The architecture had to leave a clear extension point for Damith's AI recommendation engine
without implementing any recommendation logic in this phase.

**What this phase explicitly does not do:** grade answers, store learner progress/attempts, or run
any personalisation. Those remain fordona-engine's job today (see design doc §1 and the "Overlap
with fordona-engine" risk in §12).

---

## 2. Repository layout

```
fordona-boost-cms-bridge/
├── docs/design.md              Design document (Ticket 01 deliverable)
├── README.md                   How to run, test, deploy
├── WORK_LOG.md                 This file
├── pyproject.toml              Package metadata, dependencies, ruff/pytest/mypy/coverage config
├── uv.lock                     The only dependency lockfile (no requirements.txt — see §7)
├── .python-version              3.12
├── .env.example                 Every configuration variable, documented
├── .gitattributes               Normalises line endings (LF) across the repo
├── Dockerfile                   Multi-stage build, non-root runtime
├── docker-compose.yml           Local Postgres + Redis + migrate + app
├── .dockerignore
├── alembic.ini                  Alembic config (DATABASE_URL only — no Boost/Kinde needed to migrate)
├── migrations/
│   ├── env.py                   Async Alembic environment
│   ├── script.py.mako           Revision template
│   └── versions/0001_content_snapshot.py
├── src/boost_bridge/            Application package (src layout)
│   ├── main.py                  App factory (`create_app`), lifespan wiring
│   ├── container.py             Composition root: builds clients/cache/DB/verifier, owns lifecycle
│   ├── core/                    Cross-cutting concerns (see §4.1)
│   ├── clients/boost/           Typed async Boost delivery client (see §4.2)
│   ├── cache/                   Fail-open Redis wrapper + cache keys (see §4.3)
│   ├── db/                      Postgres snapshot table, repository, engine (see §4.4)
│   ├── services/                Use cases, mapping, cache orchestration, sequencer (see §4.5)
│   ├── schemas/                 Frontend-facing Pydantic models (see §4.6)
│   └── api/                     Routers, dependencies, OpenAPI error docs (see §4.7)
└── tests/
    ├── unit/                    Pure logic: config, locale, security, boost client, cache, container
    ├── api/                     Full-stack route tests (real routers → service → cache → client)
    ├── integration/             Against a real Postgres via testcontainers (needs Docker)
    ├── conftest.py              The `Harness` fixture: a running app with Boost/Kinde mocked
    ├── factories.py             Boost payload builders
    ├── fakes.py                 In-memory doubles (fetcher, snapshot store, clock)
    └── auth.py                  RSA keypair + JWT factory for auth tests
```

Everything under `.venv/`, `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`, `.idea/`, and `.env`
is local/generated and gitignored.

---

## 3. Architecture at a glance

```
Theory App ──(Kinde JWT, X-Correlation-ID)──▶ API routers
                                                   │ validate, resolve locale + learner
                                                   ▼
                                            ContentService ──▶ ContentSequencer (extension point)
                                                   │ map upstream → API schema (allowlist)
                                                   ▼
                                            ContentCache (read-through, SWR, single-flight)
                                            ├──▶ Redis (hot cache)
                                            ├──▶ BoostClient (async httpx, retries) ──▶ Boost delivery API
                                            └──▶ Postgres (last-known-good snapshot, used on Boost failure)
```

Dependencies point downward only: **routes → service → cache → (client, repository, redis)**. The
Boost client and the Postgres repository never import anything from the service layer or above.
This mirrors the layering convention used in `fordona-engine` (controller → service → store), which
is why the design doc frames it in those terms.

Full diagrams, the request-flow sequence and the cache/refresh state machine are in
**docs/design.md §3 and §5** — not duplicated here.

---

## 4. What each module does and why

### 4.1 `core/` — cross-cutting concerns

| File | Responsibility | Why it looks the way it does |
|---|---|---|
| `config.py` | `Settings` (pydantic-settings), `Environment`, `BoostAuthMode` | Fails fast on invalid combinations at startup rather than at the first request: `AUTH_ENABLED=false` is refused outside `APP_ENV=local`; `BOOST_AUTH_MODE=service_token` requires a token; `forward_learner_token` requires auth to be enabled (there would be no token to forward otherwise); `CACHE_HARD_TTL_SECONDS` must be ≥ soft TTL. |
| `clock.py` | `Clock` protocol + `SystemClock` | TTL logic (`ContentCache`, `JwksCache`) takes a clock as a dependency so tests can advance time deterministically instead of sleeping. |
| `context.py` | `correlation_id_var`, `learner_token_var` | Request-scoped state carried via `contextvars` rather than function parameters, so it reaches the Boost client, logger and any background refresh task without threading a value through every call. Both vars are reset at the start of every request by the middleware so nothing leaks between requests sharing an event loop. |
| `locale.py` | `resolve_locale`, `match_locale` | Implements explicit `?locale=` → `Accept-Language` (by q-value, primary-subtag match) → default `sv-SE`, matching the convention already used by fordona-engine. An explicit but unsupported locale is a 422, not a silent fallback — distinguishing "the client asked wrong" from "the client didn't ask." |
| `logging.py` | structlog configuration | Renders stdlib records (uvicorn, httpx, SQLAlchemy) through the same pipeline as structlog's own, so every log line — ours or a library's — carries `correlation_id`. JSON in deployed environments, console locally. Redacts `authorization`/`token`/`secret`-shaped keys defensively, in addition to never logging credentials deliberately. |
| `middleware.py` | `RequestContextMiddleware` | Deliberately **pure ASGI**, not `BaseHTTPMiddleware` — the latter runs the downstream app in a separate task and breaks `contextvars` propagation into it, which this service depends on for correlation and the learner token. Mints or validates (`X-Correlation-ID` pattern) the correlation id, writes one access-log line per request, and renders an unhandled exception as a generic 500 problem+json body rather than letting it leak a traceback. |
| `errors.py` | `AppError` hierarchy, RFC 7807 rendering | Mirrors fordona-engine's `ProblemDetail` shape exactly (`type, title, status, detail, instance, errorCode, correlationId`) so a client handles errors from both services identically. `ValidationFailedError`, `ContentNotFoundError`, `UnauthorizedError`, and three upstream-failure types (`UpstreamMisconfiguredError` = 502, `UpstreamUnavailableError` = 503, `UpstreamTimeoutError` = 504) map 1:1 to the Boost client's failure classification. |
| `security.py` | `TokenVerifier`, `JwksCache`, `Learner` | RS256-only (algorithm confusion closed before any key lookup); exact issuer match; audience-list match; `exp`/`nbf` with 30s leeway; `sub`/`exp`/`iat`/`iss`/`aud` required. JWKS fetched async and cached for 10 minutes; an unknown `kid` triggers at most one refetch per 60s window, so a forged `kid` cannot be used to hammer Kinde. If the JWKS cannot be fetched and nothing is cached, the response is 503, not 401 — a learner with a perfectly good token must not be told to sign in again because *we* couldn't reach Kinde. |

### 4.2 `clients/boost/` — the only code that talks to Boost

| File | Responsibility |
|---|---|
| `client.py` | `BoostClient` (one pooled `httpx.AsyncClient`, explicit timeouts, retry/backoff) and `BoostRequests` (a factory for every delivery call the service makes). |
| `models.py` | Typed, tolerant (`extra="ignore"`) Pydantic models of Boost's delivery payloads. |
| `errors.py` | Four failure types: `BoostNotFound`, `BoostMisconfigured`, `BoostUnavailable`, `BoostTimeout`. |

**Design decisions:**

- **Only the Delivery surface is used**, never Editorial (which contains drafts and answers) or
  Grading. See design doc §2 for the full comparison of Boost's three API surfaces.
- **Credential forwarding, not a shared secret, is the default** (`BOOST_AUTH_MODE=forward_learner_token`).
  The bridge verifies the caller's Kinde token itself (`core/security.py`), then forwards that same
  token to Boost via `learner_token_var`. This was a mid-project correction: Boost's own API docs
  state that `bst_…` API tokens *cannot* call delivery routes at all, and that a Boost-audience
  learner token is the primary delivery credential. A `service_token` mode remains available in case
  Boost later issues a shared service credential for this bridge.
- **Retries are GET-only** (every call this client makes is a GET), triggered by connect errors,
  timeouts, 429/502/503/504, with full-jitter exponential backoff, honouring (and capping)
  `Retry-After`, bounded by an overall time budget (`BOOST_TOTAL_BUDGET`, default 8s) so a learner
  never waits through an unbounded retry chain.
- **A 200 response that fails to parse against its model is treated as `BoostUnavailable`**, not as
  a crash — it falls back to the last-known-good snapshot rather than serving (or caching) garbage.
- **Answer fields are not modelled at all.** `correctOptionId` and `explanation` have no field in
  `QuestionTranslation`/`QuestionShared`. This is enforced structurally, not by a filter that could
  be forgotten — there is no way for an answer to reach the response schema because there is no
  attribute carrying it past the client boundary.

### 4.3 `cache/` — fail-open Redis wrapper

| File | Responsibility |
|---|---|
| `redis_cache.py` | `RedisCache`: get/set/delete/try_lock/ping, each with a 0.5s socket timeout and no client-side retry. |
| `keys.py` | `cache_key()` — deterministic, versioned (`bridge:v1:...`) key derived from resource + locale + sorted params. |

**Why fail-open:** Redis is an accelerator, never a correctness dependency. Every operation catches
`RedisError`/`OSError`, logs a warning, and degrades to "treat as a miss" (for reads) or "skip the
write" (for writes/locks) — never to a 500. This was verified directly: `tests/unit/test_content_cache.py`
simulates a disconnected Redis server (`fakeredis.FakeServer().connected = False`) and asserts the
request still succeeds by falling through to Boost.

### 4.4 `db/` — last-known-good snapshot

| File | Responsibility |
|---|---|
| `models.py` | SQLAlchemy 2.0 declarative model: `ContentSnapshot` (one table, `content_snapshot`). |
| `session.py` | Async engine/sessionmaker factory, short pool/connect timeouts (correctness fallback, not the hot path), `ping()` for readiness. |
| `snapshot_repository.py` | `SnapshotRepository.get/upsert/delete`; the upsert's `ON CONFLICT ... WHERE content_hash <> EXCLUDED.content_hash` means an unchanged refresh costs no write. |

**Why Postgres in addition to Redis:** if Boost fails at the same time Redis is cold (a flush, a
redeploy, an empty cache after a schema-version bump), Redis alone would turn that into a full
outage. Postgres is read **only** when Boost itself fails (`stale-if-error`), not as a general cache
tier — see the cache/refresh state machine in design doc §5.

**Migrations run as a pre-deploy step** (`alembic upgrade head`), never at app startup, so that
multiple replicas starting together cannot race to apply the same migration.

### 4.5 `services/` — business logic

| File | Responsibility |
|---|---|
| `content_cache.py` | `ContentCache` — the read-through orchestration: fresh/stale/miss decision, stale-while-revalidate with a cross-replica Redis lock, in-process single-flight on misses, fallback to the Postgres snapshot on Boost failure, purge-on-404. |
| `content_service.py` | `ContentService` — one method per use case (list/get modules, lessons, questions, revisions, lesson-questions). Maps `Served[T]` (value + whether it came from the degraded fallback) so routes can set `X-Content-Stale`. |
| `mappers.py` | The **allowlist**: every upstream field surfaced to the frontend is named explicitly here. This is the single place answer fields, `aiContextSummary`, and any future accidental upstream addition would have to pass through — and currently cannot, because the schemas and models don't carry them. |
| `sequencing.py` | `ContentSequencer` protocol + `CmsOrderSequencer` (the only implementation in this phase). |

**The recommendation-engine extension point**, concretely:

```python
class ContentSequencer(Protocol):
    async def sequence(
        self, learner: Learner, questions: list[Question], context: SequencingContext
    ) -> list[Question]: ...
```

`GET /v1/lessons/{lessonId}/questions` deliberately returns the lesson's **entire published question
set**, not a page — a sequencer (or future recommender) needs every candidate to reorder or select
from; reordering one page at a time would be meaningless. The service fetches up to
`_MAX_LESSON_QUESTION_PAGES` (4 pages × Boost's documented max `pageSize` of 250 = 1,000 questions)
concurrently via `asyncio.gather`, then passes the full candidate list through the active sequencer.
**Whatever the sequencer returns that is not in the published candidate set is dropped** — a test
(`test_sequencer_extension_point`) proves a misbehaving sequencer cannot inject unpublished content.
Swapping in the real recommendation engine is a one-line change in `container.py` where
`CmsOrderSequencer()` is constructed; no route, schema, or contract change is needed.

### 4.6 `schemas/` — the frontend's actual contract

CamelCase Pydantic models (`Module`, `Lesson`, `LessonSummary`, `Question`, `Page[T]`, `Problem`,
health schemas). These are deliberately **not** the same classes as the Boost client's upstream
models (`clients/boost/models.py`) — the DTO/domain-model separation convention from fordona-engine
applied here: upstream shape changes are absorbed in `mappers.py` without ever touching what the
frontend sees. `Question` has no field through which an answer *could* travel, by construction.

### 4.7 `api/` — HTTP boundary

| File | Responsibility |
|---|---|
| `deps.py` | FastAPI dependency providers: `get_current_learner` (verifies JWT or falls back to a fixed local principal when `AUTH_ENABLED=false`), `get_locale`, `serve()` (attaches `Content-Language`/`Vary`/`X-Content-Stale` headers). |
| `responses.py` | Shared OpenAPI response documentation for the problem+json error codes each route can return. |
| `router.py` | Mounts all `/v1` routers. |
| `routes/{modules,lessons,questions,health}.py` | Thin: parse/validate input via FastAPI's own typed parameters, call the service, return the schema. No business logic lives here. |

**Validation happens at the HTTP boundary, before any upstream call**: IDs match `^[1-9][0-9]*$`
via `Path(pattern=...)`, so a malformed id never reaches Boost (tested explicitly —
`test_malformed_ids_are_422_and_never_reach_boost`). Batch `ids=` lookups are capped at 100 and
validated the same way.

**`container.py`** is the composition root: it builds the Boost HTTP client, the Kinde JWKS HTTP
client, Redis connection, SQLAlchemy engine, `ContentCache`, `ContentService`, and `TokenVerifier`
(or `None` if auth is disabled), and owns closing all of them in its `finally` block. `main.py`'s
`create_app()` accepts a `services_factory` parameter specifically so tests can substitute an
equivalent factory wired to fakes (`tests/conftest.py`) while exercising the *real* routers,
dependencies, and middleware stack.

---

## 5. Key decisions and why (consolidated)

This section exists so a reviewer doesn't have to reconstruct *why* from the diff. Each item below
also appears, with more context, in `docs/design.md`.

1. **Credential model: forward the learner's token, don't hold a shared secret, by default.**
   Changed mid-project after reading Boost's actual API docs — the original plan (service token
   only) was based on an inference from the OpenAPI file alone, and Boost's docs explicitly say
   `bst_` tokens don't work against delivery routes. This also means: **gating access only inside
   this bridge cannot work.** Any learner holding a valid Boost-audience token can call Boost
   directly, bypassing the bridge entirely. This is called out as an open risk, not quietly worked
   around — see design doc §8 and §12, risk 1.
2. **Two-tier cache (Redis + Postgres), not Redis alone.** Redis is fail-open and ephemeral;
   Postgres exists solely to answer "what did we serve last, when Boost itself has failed."
3. **Stale-while-revalidate + single-flight**, implemented by hand rather than via a library,
   because the failure semantics needed (cross-replica lock via `SET NX`, in-process future
   sharing, cancellation safety on client disconnect) are specific enough that a library would
   obscure more than it would save. Every branch has a dedicated test
   (`tests/unit/test_content_cache.py`): fresh hit, stale hit + background refresh, lock contention
   between replicas, concurrent misses sharing one upstream call, a cancelled waiter not cancelling
   the shared load, Redis down, snapshot-store down, 404 purging both tiers.
4. **A 404 from Boost purges both cache tiers.** Unpublished content must not resurrect itself
   through the stale-if-error fallback path.
5. **Boost rejecting our/the forwarded credential is a 502, not a 401.** The caller's token was
   already verified locally; a rejection from Boost means the two services disagree about identity
   configuration (wrong audience, Boost-side issue), which is *our* problem to fix, not something to
   push back on the learner as "sign in again."
6. **Health readiness checks Postgres and Redis, but deliberately not Boost.** Boost being down is
   exactly the scenario the snapshot fallback exists for; making Boost's health gate this service's
   own readiness would turn a Boost outage into an outage of the bridge too. (Documented trade-off:
   this does mean a Redis blip removes replicas from rotation even though the service still
   functions without Redis — see design doc §12, risk 5.)
7. **Pure ASGI middleware instead of `BaseHTTPMiddleware`**, because the latter runs downstream
   handling in a separate task and loses `contextvars` — which this service relies on for
   correlation IDs, the forwarded learner token, and structlog's bound context.
8. **No `requirements.txt`.** `uv.lock` is the single source of truth; a second pinned list would
   drift from it over time. If a deployment target strictly needs one, `uv export --no-dev --format
   requirements-txt` generates it on demand rather than maintaining it by hand.
9. **uv installed via `pip install uv` in the Dockerfile, not `COPY --from=ghcr.io/astral-sh/uv`.**
   The original Dockerfile's GHCR-based copy failed in this environment with `denied` — a stale GHCR
   credential on the Docker Desktop builder blocked even a public, unauthenticated pull. Installing
   from PyPI removes the dependency on that registry entirely.
10. **Alembic's `alembic.ini` logging config originally printed the literal `%(levelname)-5.5s
    [%(name)s] %(message)s`** instead of substituting it, because Python's `logging.config.fileConfig`
    does not unescape the doubled `%%` that `configparser`-style ini files normally require. Fixed
    by writing single `%` directly in `[formatter_generic]`.
11. **Asset URLs are built from each content item's own `assetBaseUrl`**, per Boost's documented
    behaviour ("Build media URLs from assetBaseUrl and the returned asset ID"), with
    `BOOST_ASSET_BASE_URL` only as a fallback for the rare item that doesn't carry one.

---

## 6. What is verified vs. still assumed

**Verified** (against Boost's live API docs at `boost.fordona.io/api-docs` and its OpenAPI contract
at `boost-api.fordona.io/openapi.json`):

- API origin (`boost-api.fordona.io`, distinct from the CMS UI host).
- The delivery credential model (learner-token-forwarding is the documented primary path).
- The list envelope shape (`items, total, page, pageSize, asOf`).
- Per-item fields (`id, version, locale, shared, translation, resources, assetBaseUrl`).
- Boost's maximum `pageSize` (250).
- Field names inside `shared`/`translation`, cross-checked against the Boost CMS editor's own
  field usage.

**Still unverified** (requires a real learner token against the live API — see README's
"Verifying against live Boost" section for the exact `curl` recipe):

- The precise form of `assetBaseUrl` (a full origin? a path prefix? per-locale?).
- Whether `availableLocales` and `updatedAt` are actually present on delivery items (currently
  modelled as optional, defaulting to `None`, specifically so an absent field degrades gracefully
  instead of failing validation).
- The exact format Boost expects for a multi-id lookup (`?id=1,2,3` is assumed; comma-joined).

This list is also tracked as the risk table in `docs/design.md §12` — check there before assuming
something here is stale.

---

## 7. Testing approach

- **`tests/unit/`** — pure logic, no FastAPI app: config validation, locale resolution, JWT
  verification + JWKS caching (using a real generated RSA keypair via `tests/auth.py`, not mocked
  crypto), the Boost client's retry/backoff/error-classification (via `respx`), the cache/refresh
  state machine (via `fakeredis` + in-memory fakes), and that `container.build_services` wires
  without needing live infrastructure (connections are lazy).
- **`tests/api/`** — runs the **real** router → dependency → service → cache stack through
  `httpx.ASGITransport`, with only the true external edges replaced: Boost (`respx`), Kinde JWKS
  (`respx`), Redis (`fakeredis`). This is what proves, end-to-end, that a question response can
  never contain `correctOptionId`/`explanation` even when the upstream payload does
  (`test_question_never_contains_answers`), that malformed ids never reach Boost, and that both
  Boost-auth modes work correctly including that an unverified token is never forwarded.
- **`tests/integration/`** — `SnapshotRepository` against a real, ephemeral Postgres via
  `testcontainers`, applying the actual Alembic migration (not a hand-rolled schema), so the ORM
  model and the migration are checked against each other. Skips automatically when Docker isn't
  reachable rather than failing the whole suite.

Current status (all commands run from the repo root): 165 tests passing (158 unit/api + 7
integration), ruff and mypy (strict) clean. Confirmed end-to-end via the Docker Compose stack:
Postgres, Redis, the one-shot `migrate` service, and the app itself all start cleanly, `/health/ready`
reports both dependencies up, an unauthenticated request is rejected with 401, and a forged JWT is
rejected after a real JWKS fetch from `fordona.kinde.com`.
