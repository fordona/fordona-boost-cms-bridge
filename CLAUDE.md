# fordona-boost-cms-bridge — Developer Reference

## What this repository is

The **BFF** (backend for frontend) of the Fordona Theory App, plus — from P2 onwards — the **Boost stub**.

- **Today:** only health probes are routed. The Phase 1 catalogue routes were retired (P1.T1); the
  auth/locale dependencies, Boost client, read-through cache and snapshot store remain as the
  building blocks for P6.
- **Target (theory first shipment):** the public API the mobile app calls. It composes the
  fordona-engine's decisions (question *references*, lock state, grading feedback, progress) with
  answer-free bodies and theory from Boost, and resolves media asset ids to CDN URLs. It never holds
  learner state, grades, chooses questions or sees an answer key.

**Stack:** Python 3.12 · FastAPI · httpx (async) · Redis · PostgreSQL (SQLAlchemy 2 async + Alembic) ·
structlog · pydantic-settings · uv

---

## Source of truth and workflow

| File | Role |
|---|---|
| `docs/fordona-theory-first-shipment-architecture.md` | **The plan.** Every name, shape and rule. Never edit it. |
| `docs/BFF_IMPLEMENTATION_PROGRESS.md` | The task tracker for both repos. Follow its "How a Claude Code session uses this file" section. |
| `docs/PROGRESS__STATUS.md` | Append-only log: one entry per task and per phase exit. |
| `docs/design.md` | **Outdated** (Phase 1 design). Do not use it to decide behaviour. |
| `WORK_LOG.md` | History of how Phase 1 got its shape. Orientation only. |

These three `docs/` files are the **only live copy**; fordona-engine's `CLAUDE.md` points here.
If the plan looks wrong, ambiguous, or contradicts the code: stop, log a **BLOCKED** entry in
`PROGRESS__STATUS.md` with a concrete question and options, and ask. Never silently deviate.

---

## Layout

```
src/boost_bridge/
  main.py            app factory (create_app) + lifespan; `app` is built lazily
  container.py       composition root: builds clients, cache, DB, verifier; owns their lifecycle
  api/               routers (api/routes/*), dependencies (deps.py), OpenAPI error docs (responses.py)
  services/          read-through content cache (stale-while-revalidate + last-known-good snapshot)
  clients/boost/     typed async Boost delivery client + its error mapping
  cache/             fail-open Redis wrapper, cache keys
  db/                last-known-good snapshot table, repository, engine
  schemas/           public API Pydantic models (camelCase JSON)
  core/              config, logging, middleware, errors, auth (Kinde JWT), locale, clock, context
src/boost_stub/      the Boost stub — a separate FastAPI app, see "The Boost stub" below
migrations/          Alembic (`alembic upgrade head` is a pre-deploy step, never at app start)
scripts/             developer scripts, not in the image: `generate_stub_templates.py` (P2.T2)
stub-data/           the stub's generated data (`templates.json`, `synthetic.json`) — not yet
                     committed; the live run needs a Boost delivery token (P0.T3)
tests/               unit/ (incl. boost_stub/) · api/ · integration/ (Docker) · demo/ · contract/
```

---

## Commands

```bash
uv sync                                   # install (uv.lock is the only lockfile)
uv run pytest -q                          # unit + api; integration auto-skips without Docker
uv run pytest -m integration              # Postgres via testcontainers (needs a Docker daemon)
uv run ruff check . && uv run ruff format --check .
uv run mypy src scripts                   # strict
uv run uvicorn boost_bridge.main:app --reload
```

A task is not done until **pytest, ruff (check + format) and mypy (`src scripts`)** are all green. Report real
counts (`N passed, M skipped`), never "tests pass".

---

## Architecture rules

### Layers

| Layer | Does | Never does |
|---|---|---|
| `api/routes/*` | Declare the route, its params (`Annotated` + `Path`/`Query` with patterns), `response_model`, `responses=` error docs; call one service method; set headers via `serve()` | Business logic, calling clients or the cache directly, catching exceptions |
| `services/*` | Use cases; map upstream models → `schemas/*` via `mappers` | HTTP concerns (status codes, headers), reading settings from the environment |
| `clients/*` | Typed upstream calls; translate upstream failures into `AppError` subclasses | Caching decisions, API schema types |
| `container.py` | Construct every long-lived object once; close them on shutdown | Per-request work |

- **Dependency injection** goes through `api/deps.py` (`Content`, `CurrentLearner`, `Locale`, …).
  New services are added to `Services` in `container.py` and exposed through a deps provider — never
  imported as module-level singletons.
- **Settings** only through `core/config.Settings` (frozen, validated). Never read `os.environ`.
  Secrets are `SecretStr`. Cross-field rules go in the `model_validator`; refuse unsafe combinations
  at startup rather than warn. Every new variable is documented in `.env.example` with an **empty**
  secret value.
- **Ids are decimal strings** (`ContentId`, `ID_PATTERN`), never ints — 64-bit ids lose precision in
  JavaScript.
- **Public JSON is camelCase**: subclass `schemas/common.APIModel`. Upstream models subclass
  `BoostModel` (`extra="ignore"`, tolerant of drift).

### Security invariants (non-negotiable)

1. **Answer-free by construction.** No schema or Boost model in this repo has a field for a correct
   option, an answer key, or the grading explanation *before* an answer. The grading token and
   `/v1/grading/**` are never reachable from the BFF. Feedback content comes from the engine, after
   an answer.
2. **The BFF never decides access.** The engine says whether a lesson/unit is locked; the BFF obeys.
   For a locked lesson the BFF fetches **no** theory or bodies (paid content never leaves the server).
3. **Never expose question ids, revisions or template ids** in public attempt/item responses (plan
   §7.3). Tests assert this with a recursive key search.
4. **Only a verified token is forwarded.** `get_current_learner` verifies first, then stores it in
   `learner_token_var`. `AUTH_ENABLED=false` is permitted only with `APP_ENV=local` (enforced by
   `Settings`).
5. **Signed media URLs are built per response and never cached.** Cached bodies hold asset ids only.

### Errors

- Every deliberate error is an `AppError` subclass in `core/errors.py` with `status_code`,
  `error_code` (a constant on `ErrorCode`), `type_path` and `default_detail`. Raise it; the registered
  handler renders RFC 7807 `application/problem+json` with `errorCode` + `correlationId`, matching
  fordona-engine's `GlobalExceptionHandler`.
- Never return an error body from a route. Never invent error-code strings inline.
- Engine errors are **passed through unchanged** (status, `errorCode`, `detail`, `correlationId`).
- Document each route's possible errors via `responses=` (`api/responses.py`).

### Logging

- `log = get_logger(__name__)` (structlog). Events are snake_case names with key-value context:
  `log.warning("lesson_questions_truncated", lesson_id=..., total=...)`.
- `correlation_id` and `learner_sub` are bound per request by the middleware/deps — don't pass them by
  hand.
- Never log tokens, `Authorization` headers or secrets. Keys in `_SENSITIVE_KEYS` are redacted; add
  new secret-bearing keys there.
- Never swallow an exception silently — at least `log.warning` with context.

### The Boost stub (plan §4.5)

`src/boost_stub/` is a **second, independent FastAPI app** implementing the plan §13 contract over
today's Boost, for dev and staging. It is deployed and run separately from the BFF, and its own
`CLAUDE.md`-equivalent rules are:

- **`boost_bridge` and `boost_stub` never import each other** (`[tool.importlinter]` in
  `pyproject.toml`, `uv run lint-imports --config pyproject.toml` in CI; `boost_stub` has its own
  `config.py`/`logging.py`/`upstream.py` rather than reusing `boost_bridge`'s).
- **`boost_stub` is excluded from this project's wheel**
  (`[tool.hatch.build.targets.wheel].packages`), so `uv sync --no-editable` never installs it. The
  Dockerfile's `boost-stub` stage copies `src/boost_stub` as source instead (with `PYTHONPATH`), and
  the `runtime` stage must never copy it. `tests/integration/test_docker_stages.py` builds both
  stages for real and checks this (needs Docker).
- **No identity of its own: every token is probed against Boost** (`auth.py`). A delivery-scoped
  endpoint probes `GET /v1/delivery/modules`; a grading-scoped one probes a reserved, never-real id
  at `/v1/grading/questions/{id}/revisions/{version}` (404 = valid scope, since the id doesn't
  exist). A good result is cached per token for 30 s; a bad one is never cached. This applies even to
  requests the stub answers **without** calling Boost (the change feed, `question-templates`,
  `topics`), not just the ones it proxies.
- **The change feed is polled, not transactional** (`changes.py`, `container.poll_once`): every
  `STUB_POLL_SECONDS` it lists Boost (modules, lessons, questions) plus the generated templates and
  synthetic questions, diffs against the last snapshot in its SQLite file, and writes one row per
  difference. A row is invisible for `STUB_VISIBILITY_LAG_SECONDS` (commit-order safety, §13.3); rows
  older than `STUB_RETENTION_SECONDS` are purged, and a cursor at or before the purge watermark gets
  `CURSOR_EXPIRED`. `STUB_POLL_TOKEN` is the stub's **own** delivery credential for this background
  job — distinct from a caller's token, which is only ever forwarded, never stored.
- **Synthetic question ids never reach Boost.** `GeneratedData` (`data.py`) indexes
  `stub-data/templates.json`/`synthetic.json` by id; every route checks there first and only calls
  Boost for the ids it doesn't recognise.
- Register a **literal route before a path-parameter route on the same prefix**
  (`/questions/revisions` before `/questions/{question_id}`) — FastAPI matches registration order, so
  the reverse order makes the batch endpoint invisible (it 404s as if `question_id="revisions"`).
  `routes/content.py` keeps this order with a comment; get it wrong and
  `test_stub_against_contract_suite.py` catches it immediately.
- A bare query-parameter name (`module_id: str`) binds to that Python name, **not** Boost's
  camelCase one (`moduleId`) — always `Annotated[str, Query(alias="moduleId")]`.

**Acceptance (P2.T1 + P2.T3):** `tests/unit/boost_stub/test_stub_against_contract_suite.py` runs the
real `tests/contract/boost_content_v1` suite, as a subprocess, against a live stub instance backed by
a small in-process stand-in for Boost (`fake_boost.py`) — no Docker, no real Boost needed. It
currently deselects `test_expired_cursor_is_410`: a single short-lived instance can't age a cursor
past retention without also purging the history the *other* feed tests read from `0` (the tracker's
own `test_changes.py` covers `CursorExpiredError` directly instead).

---

## Testing

- **API tests run the real stack** (routes → service → cache → client → httpx). Only the edges are
  doubles: Boost and Kinde JWKS via **respx**, Redis via **fakeredis**, snapshots in memory. Use the
  `harness` / `harness_factory` fixtures in `tests/conftest.py` and payload builders in
  `tests/factories.py`; mint tokens with `harness.auth(...)`.
- Unit tests for pure logic live in `tests/unit/`; Docker-backed tests are marked `integration`.
- Names describe the behaviour: `test_<behaviour>_<expected>` (e.g.
  `test_missing_token_is_401_problem`). One behaviour per test; no logic in tests.
- Cover: happy path, 401, 404, 422 validation, upstream failure modes (timeout, 5xx, stale fallback),
  and the security invariants above.
- **Never weaken, skip or delete a test to make it pass.** A failing test is a bug or a BLOCKED entry.

---

## Git

- Work on the branch the task names; never push or open PRs unless asked.
- Conventional Commits with the tracker task id: `feat(theory): add engine client (P6.T2)`.
- Stage files explicitly. Never commit `.env`, real tokens, or local tool folders.

---

## Known gaps (as of 2026-11-02)

- GitHub Actions CI exists (`.github/workflows/ci.yml`) but has never run (nothing pushed yet).
- `README.md` still describes Railway deployment; the plan deploys on Dokploy.
- FastAPI 0.143 wraps included routers in `app.routes`: never filter `app.routes` on `APIRoute` to
  list endpoints (it silently returns nothing). Use `app.openapi()["paths"]`.
- Until P6 there is no `/v1` route in the BFF; its API tests reach the auth/locale dependencies
  through the test-only probe route mounted in `tests/conftest.py`.
- Local integration tests need a running Docker daemon.
- A `subprocess.run(..., text=True)` capturing Docker's own output needs `encoding="utf-8",
  errors="replace"` explicitly on Windows — the default locale codec (cp1252) can't decode
  buildkit's box-drawing characters and crashes the capture thread.
- `stub-data/templates.json`/`synthetic.json` are not committed yet: the live generator run needs a
  Boost delivery token (P0.T3). Until then the stub has nothing to serve for `question-templates`,
  and every lesson is "thin" with no real questions at all to top up.
- The stub's grading batch calls Boost's single-question grading endpoint once **per configured
  locale** per real ref (today's Boost is presumed to answer one locale at a time); this is unverified
  against real Boost (`boost_bridge`'s README has the same caveat for delivery).
