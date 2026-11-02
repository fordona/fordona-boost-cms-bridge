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
src/boost_stub/      (P2.T3) the Boost stub — a separate FastAPI app, see "Stub isolation"
migrations/          Alembic (`alembic upgrade head` is a pre-deploy step, never at app start)
scripts/             developer scripts, not in the image: `generate_stub_templates.py` (P2.T2)
stub-data/           the stub's generated data (`templates.json`, `synthetic.json`), committed
tests/               unit/ · api/ · integration/ (Docker) · demo/ · contract/ (P2.T1)
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

### Stub isolation (from P2.T3)

`boost_bridge` must **never** import `boost_stub` (an import-linter contract enforces it), and the
Dockerfile's `runtime` stage must not contain `src/boost_stub`. The stub runs only in dev/staging.

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

- There is **no CI configuration** in the repo yet; tracker items that say "wired into CI" need one.
- `README.md` still describes Railway deployment; the plan deploys on Dokploy.
- FastAPI 0.143 wraps included routers in `app.routes`: never filter `app.routes` on `APIRoute` to
  list endpoints (it silently returns nothing). Use `app.openapi()["paths"]`.
- Until P6 there is no `/v1` route; API tests reach the auth/locale dependencies through the
  test-only probe route mounted in `tests/conftest.py`.
- Local integration tests need a running Docker daemon.
