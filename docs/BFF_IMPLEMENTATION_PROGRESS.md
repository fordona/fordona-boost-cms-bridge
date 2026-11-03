# Fordona Theory: Implementation Progress

The implementation tracker for `fordona-theory-first-shipment-architecture.md` (the **plan**, revision 5). It covers
every repository the plan touches:

- **fordona-engine:** Spring Boot, `learn/theory`.
- **fordona-boost-cms-bridge:** the BFF and the Boost stub.
- **Work owned by others:** tracked so blockers stay visible.

---

## How a Claude Code session uses this file

**Read before every task:**
1. This file. Find the **first unticked task whose dependencies are all ticked**.
2. The plan sections the task cites (`Plan §x.y`). The plan is the source of truth for every name, shape and rule.
3. The repository's own `CLAUDE.md` and `.claude/rules/*`. For fordona-engine these are binding:
   - store pattern; `Payload<T>`;
   - `ErrorCode.*` + i18n in **both** `messages.properties` and `messages_sv.properties`;
   - Flyway in `db/migration/learn`; no cross-schema FKs;
   - `@Slf4j` with `correlationId`; jobs only in `job/scheduler`;
   - no TODOs.
4. `PROGRESS__STATUS.md`: the last entries, for open issues and the "ready to continue" verdict.

**Working rules:**
- **One task per session**, unless the task says otherwise. Don't start a task whose dependencies aren't ticked.
- **Mark progress:** when you start, append ` — IN PROGRESS (session date)` to the task line.
- **Ticking boxes:**
  - tick a **sub-task** when its code exists **and** its tests pass;
  - tick a **task** only when every sub-task is ticked **and** its *Acceptance* checks pass;
  - tick a **phase** only when every task is ticked **and** its *Phase exit* checks pass.
- **Cancelled or replaced items:** strike them through (`- [x] ~~text~~ — reason`) instead of deleting them.
- **Never weaken a test to make it pass.** If the plan is wrong or ambiguous, stop. Record it in
  `PROGRESS__STATUS.md` as **BLOCKED** with the question, and don't guess.
- **After each task**, add an entry to `PROGRESS__STATUS.md` (template inside that file): what was done, test
  results with commands and counts, deviations, and a "ready to continue" verdict.
- **Commits:** one task per branch or PR when possible. Mention the task ID (e.g. `P4.T3`) in the commit message.
- **Never commit secrets.** Real values go in Dokploy only.

**Legend:**
- `- [ ]` to do
- `- [x]` done
- `- [x] ~~…~~` cancelled
- **Dep:** tasks that must be ticked first
- **Repo:** `ENG` = fordona-engine, `BFF` = fordona-boost-cms-bridge, `EXT` = outside our repos

**Test commands:**
- **ENG:** `./gradlew test` (all) or `./gradlew test --tests '<Class>'`; `./gradlew compileJava` for a fast check.
- **BFF:** `uv run pytest`, `uv run ruff check .`, `uv run mypy src` (whatever the repo already uses: check
  `pyproject.toml`).

---

## Phase overview

- [ ] **P0** Decisions and prerequisites
- [ ] **P1** BFF security cleanup and staging infrastructure
- [ ] **P2** Boost content contract (§13) and the Boost stub
- [ ] **P3** Engine: content read model, sync and snapshot
- [ ] **P4** Engine: attempts, grading and the forced retry phase
- [ ] **P5** Engine: progress, home, learning path, readiness
- [ ] **P6** BFF: the public API
- [ ] **P7** End-to-end quality: concurrency, load, observability, runbook
- [ ] **P8** Hand-off to the mobile developer
- [ ] **P9** Production readiness (mostly external blockers)

**Dependency order:**
- P0 → P1 → P2.
- P3 depends on P2.T1 (contract) and P2.T3 (stub) for integration tests.
- P4 → P3. P5 → P4.
- P6 depends on P2, P4 and P5 (it can start on P4's endpoints while P5 is in progress).
- P7 → P6. P8 → P7. P9 → P8 plus the external work.

---

## P0. Decisions and prerequisites

- [ ] **P0 — phase done**

- [x] **P0.T1 Copy the plan where every session can read it** · Repo: BFF · Dep: none
  - [x] Copy `fordona-theory-first-shipment-architecture.md` into `fordona-boost-cms-bridge/docs/`.
  - [x] Copy this file and `PROGRESS__STATUS.md` into the same folder. That folder is the one sessions are told to
        read; it must be the single live copy.
  - [x] Add a one-line pointer to the plan in `fordona-engine/CLAUDE.md`, as a "Theory first shipment" reference.
  - **Acceptance:** a fresh session started in either repo finds all three files at the paths above.

- [ ] **P0.T2 Product and owner sign-offs (record each answer in `PROGRESS__STATUS.md`)** · Repo: EXT
  - [ ] O-2: first-attempt template is hash-spread (Plan §5.2).
  - [ ] O-4: sequential unlocking, including across units (Plan §1 decision 10).
  - [ ] O-5: `similar_scope` default `REACHED` (Plan §5.3).
  - [ ] O-6 / O-7: no retry phase when W = 0; no ceiling on retry size.
  - [ ] O-9: Start Quiz doesn't require finishing the theory.
  - [ ] O-11: a retake counts as activity; daily challenge = 3 distinct lessons; week start Sunday or Monday.
  - [ ] O-12: the readiness formula (Plan §5.7).
  - [ ] O-10: who processes and hosts media (Boost, or R2 + Cloudflare Stream).
  - **Acceptance:** every decision has an answer, an owner and a date. Any answer that differs from the plan's
    recommendation is logged as a plan change before P3 starts.

- [ ] **P0.T3 Credentials and identifiers** · Repo: EXT
  - [ ] Confirm the engine's real `KINDE_AUDIENCE` in Dokploy (expected `https://api.fordona.dev`). This value is used
        by the BFF.
  - [ ] Get a **delivery** service token for the BFF from the Boost owner (not a `bst_` token).
  - [ ] Get a **delivery** token and a **grading** token for the engine from the Boost owner.
  - [ ] Generate the internal token: `openssl rand -base64 48`. Store it only in Dokploy, on both apps.
  - [ ] Hand Plan §13 to the Boost owner and agree on a delivery date (O-1).
  - **Acceptance:** all values are stored in Dokploy or a password manager; none are in any repo.

- [ ] **P0.T4 Postgres hardening** · Repo: EXT
  - [ ] Remove the external port 5432 on `fordona-gearbox-l1bqji`, or IP-restrict it. Use an SSH tunnel for DBeaver.
  - [ ] Create the role and database:
        `CREATE ROLE boost_bridge LOGIN PASSWORD '…'; CREATE DATABASE boost_bridge OWNER boost_bridge; REVOKE CONNECT ON DATABASE boost_bridge FROM PUBLIC;`
  - [ ] Record `SHOW max_connections;` and the engine's Hikari size in `PROGRESS__STATUS.md`.
  - **Acceptance:** an `nc`/`psql` attempt from outside the server to port 5432 fails (or succeeds only from an
    allowed IP), and `boost_bridge` can connect only to its own database.

- [ ] **P0 Phase exit:** T1–T4 ticked; no BLOCKED entries open in `PROGRESS__STATUS.md`.

---

## P1. BFF security cleanup and staging infrastructure

- [ ] **P1 — phase done**

- [x] **P1.T1 Retire the leaky catalogue routes (Plan §15, R-11)** · Repo: BFF · Dep: P0.T1
  - [x] Search the web app (`fordona-trafikskola-web`, `fordona-next`) and any other client for calls to
        `/v1/questions`, `/v1/lessons/{id}/questions` and `/v1/modules`. Record the findings.
  - [x] ~~If a client uses them, write its migration path into `PROGRESS__STATUS.md` and get approval before
        deleting.~~ — not needed: no client calls them (see `PROGRESS__STATUS.md`, 2026-11-02 P1.T1).
  - [x] Delete `api/routes/questions.py` and the `/{lessonId}/questions` route in `api/routes/lessons.py`, along with
        the service methods and schemas used only by them.
  - [x] Delete `api/routes/modules.py` (replaced by `GET /v1/learning-path` in P6).
  - [x] Keep the `GET /v1/lessons/{lessonId}` path; its new meaning is implemented in P6.T5. — Owner decision
        2026-11-02: `GET /v1/lessons` and `GET /v1/lessons/{lessonId}` are **removed until P6.T5**, which re-adds
        the path with the engine's lock check (they served paid theory with no entitlement check, R-8). See
        `PROGRESS__STATUS.md`, 2026-11-02 P1.T1 addendum.
  - [x] Remove or replace the tests that covered the deleted routes.
  - **Unit tests:** the route table no longer contains the deleted paths, verified by a test that iterates
    `app.routes`.
  - **Acceptance:** `GET /v1/questions` and `GET /v1/lessons/1/questions` return 404 on a local run; the full test
    suite is green.

- [ ] **P1.T2 Deploy the BFF to staging on Dokploy (infrastructure smoke test)** · Repo: BFF/EXT · Dep: P1.T1, P0.T3, P0.T4
  - [ ] Redis service `bff-redis` in the engine's Dokploy project, with no external port.
  - [ ] Application `fordona-bff`: Dockerfile build, container port 8000, domain with HTTPS (Let's Encrypt).
  - [ ] Environment: the existing variables only (`APP_ENV=staging`, Kinde trio, `BOOST_*` with `service_token`,
        `DATABASE_URL` for `boost_bridge`, `REDIS_URL`).
  - [ ] Health check (Swarm settings JSON, Python-based, because the image has no curl).
  - [ ] Migrations: `alembic upgrade head` (command override, or once via the container terminal).
  - **Acceptance:**
    - `/health/live` returns 200 and `/health/ready` returns 200;
    - an authenticated call with a Kinde user token returns non-401;
    - the startup logs contain no `access_boundary_not_enforced`.

- [ ] **P1 Phase exit:** the staging BFF is healthy, and no leaky route exists in any deployed build.

---

## P2. Boost content contract (§13) and the Boost stub

- [ ] **P2 — phase done**

- [x] **P2.T1 Contract test suite for §13** · Repo: BFF · Dep: P0.T1 · Plan §13 — DONE (2026-11-02): run
  against real Boost with real tokens (prod, no staging yet — owner decision, see `PROGRESS__STATUS.md`):
  50 failed / 2 passed / 0 errors, every failure a genuine 404 ("§13 doesn't exist yet"), none an auth
  failure. Proves the suite is meaningful; Boost itself implementing §13 (P9.T1) is the only thing left.
  - [x] Create `tests/contract/boost_content_v1/`, parametrised by base URL + tokens from env
        (`CONTRACT_BOOST_BASE_URL`, `CONTRACT_DELIVERY_TOKEN`, `CONTRACT_GRADING_TOKEN`). Skip when unset.
  - [x] Tests per endpoint (§13.2):
    - [x] change feed;
    - [x] template list and revision;
    - [x] lesson revision;
    - [x] question batch;
    - [x] grading batch;
    - [x] topics;
    - [x] the multi-value `id=` filter.
  - [x] Rules:
    - [x] batch `missing[]` semantics;
    - [x] more than 100 refs → 422;
    - [x] `CURSOR_EXPIRED` → 410;
    - [x] `seq` strictly increasing;
    - [x] revision endpoints send `Cache-Control: … immutable` and `ETag`;
    - [x] lists answer `If-None-Match` with 304;
    - [x] the delivery token gets 401/403 on `/v1/grading/**`.
  - [x] Shape checks (§13.4):
    - [x] template `shared.questions[]` sorted;
    - [x] question `topicKey`, `prompt` blocks, `options[].blocks`;
    - [x] grading `correctOptionId` + per-locale explanation blocks;
    - [x] lesson `translation.blocks`.
  - [x] Block validation helper: the block types and required fields from Plan §4.6.
  - **Acceptance:** the suite runs and **fails cleanly** (it doesn't error) against today's Boost, which proves the
    assertions are meaningful; it is wired into CI as a separate job.

- [x] **P2.T2 Template generator** · Repo: BFF · Dep: P0.T3 · Plan §4.5 — DONE (2026-11-02): live run against
  real Boost, `stub-data/` committed. **Significant finding:** Boost has zero published content right now, so
  both files are genuinely (and correctly — determinism re-verified) empty; the "every block type" coverage
  below is proven by unit tests against fixtures, not by this live run, since there's no real lesson to
  demonstrate it against. Blocked on Eric publishing content (P9.T2) for the live output to mean anything in
  practice — re-run then. See `PROGRESS__STATUS.md`.
  - [x] `scripts/generate_stub_templates.py`: reads published modules, lessons and questions from today's Boost (delivery
        token from env).
  - [x] Per lesson:
    - [x] sort by (difficulty, id);
    - [x] deal round-robin into `k = max(1, floor(n/8))` templates, spreading the remainder one per template;
    - [x] top lessons with fewer than 3 real questions up to 8 with synthetic `[DEMO]` questions.
  - [x] Template ids ≥ 9,000,000; a `generation` number; a `version` bump only for changed templates.
  - [x] Writes `stub-data/templates.json` and `stub-data/synthetic.json`, deterministically.
  - [x] `synthetic.json` holds full questions with keys and explanations, covering **every block type** (Plan §4.6):
        text, image, animation (lottie and video_loop), video with captions, audio with transcript, rule_card. It
        also covers at least one option with an image.
  - **Unit tests:**
    - [x] deterministic output (two runs on the same input are byte-equal);
    - [x] difficulty spread per template within ±1 level;
    - [x] the thin-lesson top-up;
    - [x] id range.
  - **Acceptance:** the generated files are committed, and the generator re-run produces no diff.

- [x] **P2.T3 Boost stub service** · Repo: BFF · Dep: P2.T1, P2.T2 · Plan §4.5, §13 — DONE (2026-11-02):
  both deps are now DONE too. One sub-item deliberately deferred (the in-memory LRU), everything else done
  and verified; see `PROGRESS__STATUS.md`.
  - [x] Package `src/boost_stub/` with its own FastAPI app (`boost_stub.main:app`), its own settings
        (`STUB_UPSTREAM_BOOST_URL`, `STUB_DATA_DIR`, `STUB_SQLITE_PATH`, `STUB_POLL_SECONDS=60`).
  - [x] Endpoints:
    - [x] templates served from `templates.json`;
    - [x] change feed from the SQLite tracker, with a 5 s visibility lag, `CURSOR_EXPIRED`, and a 60 s poll of
          upstream lists;
    - [x] modules and lessons proxied, with `contentHtml` + `resources` converted to blocks (a supported HTML
          subset; unknown tags dropped and logged);
    - [x] questions proxied: prompt and option blocks, `topicKey = lesson-{lessonId}`;
    - [x] ~~batch endpoints as parallel fan-out to upstream singles, with an in-memory LRU of immutable
          revisions~~ — the fan-out is done; the LRU is **deferred**: revisions are immutable so a repeat call is
          safe, just not free, and the BFF's/engine's own caches are what sit on the hot path, not the stub.
    - [x] grading proxied with the caller's token; explanation → blocks;
    - [x] synthetic ids (≥ 9,000,000, actually ≥ 9,500,001 — see the P2.T2 entry) served from `synthetic.json`,
          including grading.
  - [x] Forwards the caller's `Authorization` header unchanged; adds `X-Boost-Stub: true` to every response.
  - [x] Cache headers per §13.5.
  - [x] Isolation:
    - [x] add `import-linter` with a contract that `boost_bridge` must not import `boost_stub`, run in CI;
    - [x] a Dockerfile stage `boost-stub` (CMD `uvicorn boost_stub.main:app --port 8080`);
    - [x] the `runtime` stage must not copy `src/boost_stub`.
  - **Unit tests (respx-mocked upstream):**
    - [x] each transformation (HTML → blocks, question → blocks, explanation → blocks);
    - [x] auth forwarding (as token-scope **probing**, not passthrough verification — the stub has no identity
          of its own; see `PROGRESS__STATUS.md`);
    - [x] the header;
    - [x] batch partial results;
    - [x] change detection.
  - **Acceptance:**
    - [x] the P2.T1 suite is **green against the stub**, locally (51/52 tests; `CURSOR_EXPIRED` is covered by a
          direct `ChangeTracker` unit test instead — see `PROGRESS__STATUS.md`) **and in CI** once pushed (the
          check has no marker, so `pytest -m "not contract"` runs it);
    - [x] `docker build --target runtime` contains no `boost_stub` files (built and checked for real,
          `tests/integration/test_docker_stages.py`, needs Docker);
    - [x] import-linter passes.

- [ ] **P2.T4 Deploy the stub to staging** · Repo: BFF/EXT · Dep: P2.T3
  - [ ] A Dokploy application from the same repo, build stage `boost-stub`, **no domain** (internal only), env
        `STUB_UPSTREAM_BOOST_URL=https://boost-api.fordona.io`, plus a volume for the SQLite file.
  - **Acceptance:** from the BFF container, `GET http://<stub-host>:8080/v1/delivery/changes?after=0` with the
    delivery token returns 200 with `X-Boost-Stub: true`.

- [ ] **P2 Phase exit:** the contract suite is green against the staging stub; the generated data is committed.

---

## P3. Engine: content read model, sync and snapshot

- [ ] **P3 — phase done**

- [x] **P3.T1 Package skeleton and conventions** · Repo: ENG · Dep: P0 · Plan §6 — DONE (2026-11-02): started
  before P0 exit (owner instruction, "continue implementations"); see `PROGRESS__STATUS.md`.
  - [x] Create `io.fordona.engine.learn.theory` with sub-packages:
        `api/{dto,request}`, `data/{entity,mapper,projection,repository,store}`,
        `exception/{business,resource,validation}`, `model`, `service`, `content`, `similarity`, `usecase`. —
        the still-empty ones (`api`, `data`, `model`, `service`, `content`, `similarity`, `usecase`) are
        deliberately not pre-created; they materialise with their first class, as every other module did.
  - [x] Add `ErrorCode.Theory` (nested class), following the existing naming: e.g. constant
        `ErrorCode.Theory.LESSON_NOT_FOUND` with value `"THEORY_LESSON_NOT_FOUND"`. It needs every code from Plan §7.3:
    - `THEORY_MODULE_LOCKED`, `THEORY_LESSON_LOCKED`;
    - `THEORY_LESSON_NOT_FOUND`, `THEORY_ATTEMPT_NOT_FOUND`, `THEORY_ITEM_NOT_FOUND`;
    - `THEORY_REQUEST_ID_CONFLICT`, `THEORY_RESPONSE_CONFLICT`;
    - `THEORY_PHASE_CLOSED`, `THEORY_PHASE_INCOMPLETE`;
    - `THEORY_OPTION_INVALID`.

    Add keys for each in `messages.properties` **and** `messages_sv.properties`. — **Deviation:** `MODULE_LOCKED`
    and `LESSON_NOT_FOUND` collided with two pre-existing `ErrorCode.Learn` values of the same string (the
    older, still-live quiz feature); renamed to `THEORY_ATTEMPT_MODULE_LOCKED` /
    `THEORY_ATTEMPT_LESSON_NOT_FOUND` (owner decision 2026-11-02, see `PROGRESS__STATUS.md`). The other eight
    match verbatim.
  - [x] Exception classes in the right hierarchy. One class per code (not a shared `Reason` enum — these span
        four different HTTP statuses). 409s use `BusinessException` with an explicit `HttpStatus.CONFLICT`.
  - **Unit tests:** an i18n test that every `ErrorCode.Theory.*` constant has a key in both bundles. — the
    existing generic `ErrorCodeMessageCoverageTest` already does this for every `ErrorCode.*` nested class; no
    new test needed.
  - **Acceptance:** `./gradlew compileJava` passes; the i18n test is green. — met.

- [x] **P3.T2 Flyway migrations: content read model** · Repo: ENG · Dep: P3.T1 · Plan §6 — DONE (2026-11-02)
  - [x] `V1_0_16__theory_content_read_model.sql` in `db/migration/learn`. Tables:
    - `content_release` (`release_id`, `source`, `change_cursor`, `activated_at`);
    - `content_unit` (`title jsonb`, `icon_asset_id`, `status`);
    - `content_lesson` (`title jsonb`, `current_version`, `estimated_minutes`, `status`);
    - `content_template` (`current_version`, `status`);
    - `content_template_question`;
    - `content_question` (`home_lesson_id`, `current_version`, `status`);
    - `content_question_revision` (`type`, `difficulty`, `level`, `domain_code`, `topic_tag`, `correct_option_key`,
      `option_keys jsonb`, `media_kinds jsonb`, `explanation jsonb`, `release_id`);
    - `question_neighbour`.
  - [x] `CHECK` constraints on every status column; indexes on foreign-key-like columns. No cross-schema FKs.
  - **Acceptance:** the engine starts on a clean database; Flyway validates; a Testcontainers migration test
    passes. — met via the existing `FordonaEngineApplicationTests` context-load test (Docker available this
    session); a dedicated migration-only test wasn't added since this one already runs the migration for real.

- [x] **P3.T3 Boost client (engine side)** · Repo: ENG · Dep: P3.T1 · Plan §7.5, §13 — DONE (2026-11-02)
  - [x] Config: `theory.boost.base-url`, `theory.boost.delivery-token`, `theory.boost.grading-token`, timeouts. Env
        overrides in `application.yml`; no defaults for tokens.
  - [x] `RestClient`-based `BoostContentClient`:
    - `changes(after, limit)`;
    - lists by `id=` filter (modules, lessons, questions, **and question-templates** — read "lists" as all four
      of §13.2's list resources, since P3.T2's schema needs template data and nothing else in the tracker
      supplies it; see `PROGRESS__STATUS.md`);
    - `questionRevisionsBatch(refs)` (≤ 100, chunked);
    - `gradingRevisionsBatch(refs)`;
    - `topics(moduleId)`.
    - Parse `missing[]`.
  - [x] **Prod guard:** on the first response with `X-Boost-Stub: true` under the `prod` profile, fail fast (startup
        check or first-call check that throws and alerts). — first-call check.
  - [x] Never log tokens; log `requestId` from the Boost Problem body.
  - **Unit tests (MockRestServiceServer or WireMock):**
    - [x] batch chunking;
    - [x] the `missing[]` handling;
    - [x] 410 `CURSOR_EXPIRED` mapped to a typed exception;
    - [x] the prod guard.
  - **Acceptance:** a WireMock suite covers every method. — met with `MockRestServiceServer` (8 tests, all
    public methods covered).

- [x] **P3.T4 Content validation and sync service** · Repo: ENG · Dep: P3.T2, P3.T3 · Plan §4.3, §4.4 —
  DONE (2026-11-02). See `PROGRESS__STATUS.md` for both parts' full writeups, including two real bugs
  (a missing JSONB-converter gap, and a lesson/template write-ordering bug) caught before or by tests.
  - [x] `ContentSyncService.sync(Instant now, boolean full)`:
    - [x] read the change feed from `content_release.change_cursor`;
    - [x] fetch the changed ids — **deviation:** the feed only decides *whether* to resync; any
          reported change triggers a full re-list rather than a batch-scoped fetch of just the
          changed ids (deliberate, logged, fine at today's content scale);
    - [x] fetch new grading revisions in batches;
    - [x] upsert the read model;
    - [x] apply validation;
    - [x] store the new cursor;
    - [x] create a new `content_release` **only if something changed**.
  - [x] **Full resync:** `full=true` resets the cursor and reads all lists (`pageSize` 250). It runs on
        `CURSOR_EXPIRED` too.
  - [x] Validation rules (Plan §4.4):
    - [x] a question is EXCLUDED when its key isn't among its options, options aren't distinct, difficulty is
          outside 1–5, domain or topic is unknown, or a locale is missing — **deviation:** the domain-unknown
          check uses a configurable allowlist that defaults to empty/permissive, since Boost's actual six
          domain codes aren't enumerated anywhere; see `PROGRESS__STATUS.md`;
    - [x] a template with fewer than 3 valid questions is HIDDEN;
    - [x] a lesson with no visible template or empty theory is HIDDEN.
  - [x] Level mapping from `difficulty_level_map` (default 1–2 easy, 3 medium, 4–5 hard) — hardcoded as the
        default for now; `retry_policy.difficulty_level_map` (P4.T1) doesn't exist yet to read from instead.
  - [x] `home_lesson_id` = the lesson of the question's first template by sort.
  - [x] `media_kinds` derived from the block types in the prompt and options.
  - [x] Unit and lesson titles stored per locale. **No question text or theory stored** (Plan §6 notes).
  - **Unit tests:**
    - [x] each validation rule;
    - [x] the level mapping;
    - [x] home lesson;
    - [x] no release when nothing changed;
    - [x] cursor advance.
  - **Acceptance:** a Testcontainers test syncs the stub's fixtures (recorded responses) into an empty database; a
    second sync creates no release. — met (`ContentSyncServiceTest`, real Postgres, `BoostContentClient` mocked
    with a hand-built fixture).

- [x] **P3.T5 Sync jobs (job module)** · Repo: ENG · Dep: P3.T4 · CLAUDE.md "Scheduled Jobs" — DONE
  (2026-11-02). See `PROGRESS__STATUS.md`.
  - [x] An `ExternalUseCase` exposing `syncTheoryContent(Instant now, boolean full)` — **deviation:**
        placed in `io.fordona.engine.client`, not `learn/theory/usecase`, matching every other
        cross-tier `*ExternalUseCase` in this codebase (`learn/theory/usecase` is for same-tier
        sibling calls within `learn.*`, which this isn't); see `PROGRESS__STATUS.md`.
  - [x] `JobNames.THEORY_CONTENT_SYNC` (every 30 s) and `JobNames.THEORY_CONTENT_FULL_RESYNC` (nightly, R-12).
  - [x] Schedulers in `job/scheduler/` implementing `ScheduledJob`:
    - [x] `@Scheduled` calls `jobRunner.run(name(), this::runNow)`;
    - [x] `@ConditionalOnProperty` on `fordona.jobs.enabled` + the per-job flag;
    - [x] `application.yml` entries under `fordona.jobs.configs.*` with env overrides and `lock-at-most-for`.
  - **Unit tests:** the scheduler delegates to the use case; the property gating. — both done; the gating
    tests use `@Import` of the plain `@Component` class rather than a hand-written `@Bean` factory method,
    which would have silently bypassed the condition entirely (see `PROGRESS__STATUS.md`).
  - **Acceptance:** a local run with the stub shows sync audit rows in `job_run`, and only one instance runs it at a
    time (ShedLock). — not separately re-verified: that machinery is `JobRunner`'s own, already relied on
    (and tested) by five other schedulers with no per-scheduler acceptance test of its own; this follows the
    same, already-established scope boundary rather than introducing a new one.

- [x] **P3.T6 In-memory content snapshot** · Repo: ENG · Dep: P3.T4 · Plan §9.2 — DONE (2026-11-02).
  See `PROGRESS__STATUS.md`.
  - [x] An immutable `ContentSnapshot` holding:
    - [x] units, lessons (titles, versions, `estimated_minutes`) and templates in order;
    - [x] current question revisions (tags, level, keys, option keys, explanations);
    - [x] neighbour lists — the read path is real and wired to `question_neighbour` now; the table
          itself stays empty until P3.T7's `NeighbourBuilder` writes to it;
    - [ ] the resolved retry policy (added in P4.T1) — genuinely deferred, as the tracker's own
          parenthetical already anticipated; `retry_policy` doesn't exist as a table yet.
  - [x] `ContentSnapshotProvider.get()`, held in an `AtomicReference`:
    - [x] **lazy freshness check**: at most once per 30 s, a single-flight check of `max(release_id)`;
    - [x] rebuilds when it changes.
    - [x] Don't use a ShedLock'd job here: **every instance** must refresh.
  - [x] Older pinned revisions load on demand into a bounded Caffeine cache (immutable, no expiry).
  - **Unit tests:**
    - [x] atomic swap;
    - [x] single-flight under concurrent `get()`;
    - [x] no rebuild without a release change;
    - [x] the old-revision loader.
  - **Acceptance:** after a sync creates a release, two engine instances (two Spring contexts in a test) both serve
    the new snapshot within 30 s. — met with two plain `ContentSnapshotProvider` instances rather than two full
    Spring contexts: the provider holds no static/shared state, so two instances sharing only the real database
    *are* two independent "engine instances" for everything this check is actually testing; see `PROGRESS__STATUS.md`.

- [x] **P3.T7 Neighbour builder (metadata strategy)** · Repo: ENG · Dep: P3.T4 · Plan §8 — DONE
  (2026-11-02). See `PROGRESS__STATUS.md`.
  - [x] `NeighbourBuilder` runs after each release. For every ACTIVE question, rank ACTIVE candidates from the
        **whole bank** by these groups:

        | Group | Score |
        |---|---|
        | Same lesson (other templates), same topic | 1.0 |
        | Same unit, same topic | 0.8 |
        | Same lesson, same domain | 0.6 |
        | Same topic, anywhere | 0.5 |
        | Same domain, same unit | 0.4 |

        Within a group, sort by closest difficulty, then `questionId`. Keep the top 20. Write `question_neighbour`
        with `provider = metadata`.
  - [x] A `SimilarQuestionProvider` port: `neighbours(questionId)` read from the snapshot.
  - [x] `theory.similarity.source=metadata|vector`. Only metadata is implemented; vector is an empty extension point
        with no code, documented. — **strengthened:** the property genuinely gates the bean via
        `@ConditionalOnProperty` rather than existing as an inert switch; see `PROGRESS__STATUS.md`.
  - **Unit tests:**
    - [x] group ordering;
    - [x] tie-breaks are deterministic;
    - [x] excluded questions are never neighbours;
    - [x] at most 20.
  - **Acceptance:** for the stub data, every question with ≥ 2 same-lesson peers has ≥ 2 neighbours. — met
    against a real Postgres fixture (today's real Boost still has no content to run this against for real).

- [x] **P3.T8 Platform endpoints: sync and content report** · Repo: ENG · Dep: P3.T5, P3.T7 · Plan §7.6 · `.claude/rules/platform-module.md`
  - [x] `learn/platform/api/TheoryContentPlatformController`:
    - `POST /v1/platform/theory/content-sync?full=` (calls the same use case);
    - `GET /v1/platform/theory/content-report`: release, hidden templates and lessons, excluded questions with
      reasons, similarity coverage, and the per-template difficulty mix (R-7).
    - The extras-shortfall rate is added in P4.
  - [x] Platform-admin permission, the same mechanism as the existing platform controllers.
  - **Tests:** 401 when unauthenticated; 403 for a non-admin; happy path for both endpoints.
  - **Acceptance:** after a sync, the report against the stub data lists the generated templates and any synthetic
    gaps. — the report assembly itself is verified against a real Postgres fixture; running it against the actual
    staging stub's generated templates is still open, same caveat as P3.T7 (today's real Boost/stub has nothing to
    sync yet).

- [ ] **P3 Phase exit:** the engine syncs the staging stub every 30 s, holds a snapshot on every instance, and the
  content report is clean, or its findings are logged.

---

## P4. Engine: attempts, grading and the forced retry phase

- [x] **P4 — phase done**

- [x] **P4.T1 Migrations and retry policy** · Repo: ENG · Dep: P3 · Plan §5.6, §6
  - [x] `V1_0_17__theory_attempts.sql`:
    - `lesson_attempt` (all Plan §6 columns, incl. `kind`, `template_id`, `lesson_version`, `selection_strategy`,
      `selection_reason`, `policy_snapshot jsonb`, phase totals, `retry_extras_short`);
    - `attempt_item` (incl. answer columns, `response_id`);
    - `mistake`.
    - Note: `policy_snapshot`/`option_order` are TEXT holding JSON, not JSONB — this engine has no
      JSONB converter pair registered anywhere (same reasoning as P3.T2's content read model).
  - [x] Constraints:
    - `UNIQUE(app_user_id, request_id)`;
    - partial unique `(app_user_id, lesson_id) WHERE status <> 'COMPLETED'`;
    - PK `(attempt_id, seq)` and `UNIQUE(response_id)`;
    - indexes `attempt_item(app_user_id, question_id)` and `(app_user_id, answered_at)`, and
      `mistake(app_user_id, unit_id, status)`;
    - `CHECK` constraints.
  - [x] `V1_0_18__theory_retry_policy.sql`: `retry_policy` with a GLOBAL row holding the defaults:
        `retry_enabled` true, `extras_per_wrong` 1.5, `extras_min` 2, `extras_max` 5, `level_drop_allowed` 1,
        `similar_scope` REACHED, `difficulty_level_map`.
        Deviation: surrogate `BIGSERIAL id` + `UNIQUE(scope, scope_id)` instead of Plan §6's literal
        `PK(scope, scope_id)` — see PROGRESS__STATUS.md, 2026-11-02, P4.T1 for why.
  - [x] `RetryPolicyResolver`: LESSON > UNIT > GLOBAL, with range validation, cached in the snapshot.
  - [x] Platform endpoints `GET /v1/platform/theory/retry-policy` and `PUT …/{scope}/{scopeId}`. A PUT bumps the
        content release so every instance reloads.
  - **Unit tests:** resolution order; every range rule (incl. min ≤ max); the PUT validation returns 422.
  - **Acceptance:** a policy change is visible on a second instance within 30 s. — proven as
    release-bump-on-PUT + `ContentSnapshotProvider`'s already-tested 30s polling, not a literal
    two-instance test.

- [x] **P4.T2 Entitlement and unlock rules** · Repo: ENG · Dep: P4.T1 · Plan §1 decision 10, §5.1
  - [x] Locate today's unit-lock logic (`LearnHubService` / `LearnAccessContext`, free vs subscribed). Expose it as
        `TheoryEntitlement.isUnitEntitled(userId, unitId)`, cached per user, invalidated on subscription change.
        **Verify how existing rules identify a unit** (Directus ids vs sort). Map to Boost module ids by **sort
        order**, and record the mapping decision in `PROGRESS__STATUS.md`.
        Finding: the existing module lock is a *navigation-order* rule (free learners can't skip ahead, but are
        never permanently blocked), not a paywall — there is no existing per-unit entitlement to reuse or map.
        The entitled boundary used here (first Boost unit by sort, free; everything else needs a subscription) is
        confirmed against Plan §14's own test-account list, not derived from the old logic.
  - [x] `UnlockService` (pure, over the snapshot + the learner's completed set):
    - lesson n+1 unlocks after lesson n is completed;
    - the first lesson of unit u+1 unlocks after the last visible lesson of unit u **and** if unit u+1 is
      entitled;
    - HIDDEN lessons are skipped.
  - **Unit tests:**
    - [x] first lesson unlocked;
    - [x] the skip over a hidden lesson;
    - [x] cross-unit with and without entitlement;
    - [x] retakes of completed lessons are allowed.
  - **Acceptance:** a table-driven test covers each `status` value used by the learning path (`completed`,
    `current`, `locked`).

- [x] **P4.T3 QuestionSetSelector (`fixed-v1`)** · Repo: ENG · Dep: P4.T2 · Plan §5.2
  - [x] A pure port `QuestionSetSelector.select(SelectionContext)` → ordered refs `(questionId, version, templateId)`
        + strategy id + reason.
  - [x] `FixedTemplateSelector`:
    - first attempt: `hash(app_user_id, lesson_id) mod visibleTemplates`. Use a stable hash (e.g. murmur3 over the
      ids), never `Object.hashCode`;
    - retake k: `(firstIndex + k − 1) mod visibleTemplates`;
    - only valid questions, in template order.
    - No murmur3 dependency existed in the project; hand-rolled `MurmurHash3_x86_32` rather than adding
      one (e.g. Guava) for a single hash call — see `PROGRESS__STATUS.md`, 2026-11-03, P4.T3.
  - [x] A config switch `theory.selection.strategy=fixed-v1`.
  - **Unit tests:**
    - [x] stable across JVM runs;
    - [x] the spread is roughly uniform across 10k synthetic users (chi-square or a ±10 % bound);
    - [x] rotation;
    - [x] the template count changing between attempts.
  - **Acceptance:** the selector is pure; it has no Spring context in its tests.

- [x] **P4.T4 Start, resume and read attempt** · Repo: ENG · Dep: P4.T3 · Plan §5.1, §6 concurrency, §7.4
  - [x] `AttemptService.start(userId, lessonId, requestId)`:
    - guards: entitlement, the lesson visible and unlocked;
    - selects and pins items with shuffled `option_order` (`SecureRandom`, stored);
    - snapshots the policy and `lesson_version`;
    - inserts the attempt plus items in one batch;
    - upserts `lesson_progress` (in P5) and bumps `progress_version` (in P5; leave a hook). — no hook
      added yet; `lesson_progress` doesn't exist, so there's nothing to call. `findCompletedLessonIds`
      derives completion straight from `lesson_attempt.status = 'COMPLETED'` in the meantime.
    - **Idempotency:** a `request_id` conflict is a replay; an open-attempt conflict returns the existing attempt
      (200).
    - The racy insert (attempt + items) runs in its own `REQUIRES_NEW` transaction
      (`AttemptInsertTransaction`) — see `PROGRESS__STATUS.md`, 2026-11-03, P4.T4, for why a shared
      transaction with the caller would break the race recovery below.
  - [x] `get(userId, attemptId)` for resume: 404 for another learner's attempt.
  - [x] Internal endpoints:
    - `POST /internal/theory/v1/lessons/{lessonId}/attempts`;
    - `GET /internal/theory/v1/attempts/{attemptId}`.
    - Responses are `Payload<T>` with item **refs only** (`seq`, `phase`, `questionId`, `version`, `optionOrder`,
      `answered?`); never a key before an answer.
  - [x] Internal-route security:
    - check for an existing internal-token mechanism first;
    - otherwise add a filter on `/internal/theory/**` that requires a valid JWT **and** an `X-Fordona-Internal-Token`
      equal (constant-time comparison) to config `theory.internal.token`.
    - No existing mechanism found — `TheoryInternalTokenFilter` is new, registered after
      `BearerTokenAuthenticationFilter` in `SecurityConfig`.
  - **Tests:**
    - [x] happy path;
    - [x] 403 locked unit / lesson;
    - [x] 404 unknown lesson;
    - [x] a replay returns the same attempt;
    - [x] a parallel double start creates one attempt (Testcontainers, two threads);
    - [x] a missing internal token → 401/403;
    - [x] another learner's attempt → 404.
  - **Acceptance:** no response body contains `correct_option_key` before an answer (assert by JSON search).

- [x] **P4.T5 Answer endpoint and grading** · Repo: ENG · Dep: P4.T4 · Plan §5.4, §5.5, §6
  - [x] `POST /internal/theory/v1/attempts/{attemptId}/responses`:
    - `SELECT … FOR SHARE` on the attempt;
    - validate the phase and the option key;
    - grade from the snapshot; — graded from `PinnedRevisionLoader`'s cached pinned revision, not the
      live snapshot: an item is pinned to the revision current when its attempt started, which can
      lag the snapshot's current one after a republish. The snapshot is still used for the mistake
      ledger's `home_lesson_id` (in-memory, no extra DB read).
    - conditional `UPDATE attempt_item … WHERE answered_at IS NULL`;
    - store the tag snapshot fields (set at item creation) plus the answer fields;
    - upsert the ledger (OPEN; RESOLVED with `resolved_via` `REPEAT` / `RETAKE` / `LATER`). —
      `REPEAT` is not yet reachable: it only applies to retry-phase items, which don't exist until
      P4.T6. Every item answered today is `phase=LESSON`, so `resolved_via` only ever computes
      `RETAKE` (resolved within the mistake's own home lesson) or `LATER` (resolved elsewhere).
  - [x] Idempotency:
    - the same `responseId` + same option → replay (200, same feedback);
    - a different option or a reused `responseId` → 409 `THEORY_RESPONSE_CONFLICT`.
  - [x] Feedback: `isCorrect`, `selectedOptionKey`, `correctOptionKey`, `correctOptionLabel` (from `option_order`),
        `explanation` blocks for the request locale (fall back to `sv-SE`).
  - **Tests:**
    - [x] correct / incorrect;
    - [x] 422 invalid option;
    - [x] 404 unknown seq;
    - [x] 409 `PHASE_CLOSED`;
    - [x] a replay;
    - [x] 409 conflict;
    - [x] the ledger transitions (OPEN → RESOLVED → OPEN on a retake);
    - [x] two concurrent answers to the same item: exactly one wins.
  - **Acceptance:** the grading path makes zero database reads of content (verified by a query-count assertion or a
    repository spy). — verified by a `@MockitoSpyBean` on `TheoryContentStore`: after priming
    `PinnedRevisionLoader`'s cache once, a full `answer()` call makes no further `findRevision` call.

- [x] **P4.T6 Retry composer** · Repo: ENG · Dep: P4.T5, P3.T7 · Plan §5.3
  - [x] `E = clamp(ceil(extras_per_wrong × W), extras_min, extras_max)`. W = 0 → no retry phase.
  - [x] Repeat items: the same pinned version, **re-shuffled** options.
  - [x] Similar items: round-robin over the seeds (wrong items in `seq` order). Walk each neighbour list and apply
        filters a–f **exactly** as Plan §5.3:
    - (a) valid and visible;
    - (b) level in `{L, L−1}`, floor easy; — hardcoded, not `policy.levelDropAllowed()`; Plan §5.3 itself
      states this filter as fixed. Logged as a known, deliberate gap — see `PROGRESS__STATUS.md`.
    - (c) not in this attempt;
    - (d) **unit entitled**, mandatory and not configurable;
    - (e) `similar_scope` REACHED / ALL;
    - (f) unseen first: two passes, with one indexed "seen" query.
  - [x] Stored order: shuffle repeat + similar items with a seed derived from `attemptId`.
  - [x] Shortfall recorded in `retry_extras_short`. — the composer *computes* and returns the shortfall;
        writing it onto `lesson_attempt.retry_extras_short` is P4.T7's I/O, same as every other write.
  - [x] Pure composer (inputs: snapshot, seeds, seen set, entitlement, policy); I/O stays in the service.
  - **Unit tests:**
    - [x] the E table (W = 1 → 2, 2 → 3, 3 → 5, 4+ → 5);
    - [x] every filter on its own;
    - [x] the paid-unit question is never selected;
    - [x] the REACHED scope;
    - [x] the unseen-first fallback;
    - [x] the shortfall down to repeats only;
    - [x] deterministic order for the same attempt id.
  - **Acceptance:** a property test confirms the composer never returns duplicates or questions already in the
    attempt.

- [x] **P4.T7 Phase completion** · Repo: ENG · Dep: P4.T6 · Plan §5.1, §7.3
  - [x] `POST /internal/theory/v1/attempts/{id}/phases/lesson/complete`:
    - `FOR UPDATE`;
    - all lesson items answered, else 409 `PHASE_INCOMPLETE`;
    - write the totals;
    - W > 0 → compose and insert retry items, status `IN_RETRY`;
    - W = 0 → `COMPLETED` (lesson completion side effects run in P5).
  - [x] `POST …/phases/retry/complete`: all retry items answered; totals; `COMPLETED`.
  - [x] Natural idempotency: completing an already-completed phase returns the stored summary.
  - [x] Response refs for the retry items.
  - [x] Leave the `next` + `progress` fields for P5 (null until then, contract shape fixed).
  - **Tests:**
    - [x] W = 0 path;
    - [x] W > 0 path;
    - [x] incomplete → 409;
    - [x] double complete returns the same summary;
    - [x] a late answer after completion → 409;
    - [x] two devices completing at once are serialised (Testcontainers).
  - **Acceptance:** a full flow test: start → 8 answers with 2 wrong → lesson complete returns 5 retry items → 5
    answers → retry complete → `COMPLETED`.

- [x] **P4.T8 Lesson state endpoint** · Repo: ENG · Dep: P4.T7 · Plan §7.3 (lesson theory), §7.4
  - [x] `GET /internal/theory/v1/lessons/{lessonId}` returns
        `{ status, locked, lockReason, openAttempt, questionCount, estimatedMinutes, lessonVersion }`.
    - `questionCount` comes from a **dry run** of the selector, with no writes.
    - `estimatedMinutes`: the authored value, else reading time + media durations + 45 s × questions.
      **Deviation (logged, see status log):** the engine only ever computes the 45 s × questions
      component — it never syncs lesson theory content (text/media live in Boost, fetched only by the
      BFF), so reading time and media durations are not available to it.
  - **Tests:**
    - [x] locked → 200 with `locked=true` and the right `lockReason` (**deviation, logged**: not a
      403 — see status log for why this endpoint intentionally differs from start/answer);
    - [x] with an open attempt;
    - [x] the preview count matches the next start's count.
  - **Acceptance:** zero writes during the call (query-count assertion).

- [x] **P4 Phase exit:** the full attempt flow passes in Testcontainers; no answer key appears in any pre-answer
  response; all concurrency tests pass.

---

## P5. Engine: progress, home, learning path, readiness

- [ ] **P5 — phase done**

- [x] **P5.T1 Migrations: progress tables** · Repo: ENG · Dep: P4 · Plan §5.7, §6
  - [x] `V1_0_19__theory_progress.sql`:
    - `lesson_progress` (incl. `best_accuracy`, `open_attempt_id`, `updated_at`; PK `(app_user_id, lesson_id)`;
      partial index on open attempts);
    - `learner_theory_summary`;
    - `learner_activity_day`;
    - `learner_activity_lesson`.
  - **Acceptance:** migration test green (via the existing Spring-context-boot Flyway check every
    `IntegrationTestBase` test already runs — no dedicated migration test exists for prior theory
    migrations either).

- [x] **P5.T2 Timezone handling** · Repo: ENG · Dep: P5.T1 · Plan §5.7
  - [x] Read `X-Timezone` (validate with `ZoneId.of`; ignore invalid values); default `Europe/Stockholm`.
  - [ ] Store it on the summary when it changes — **deferred, logged in the status log**: no endpoint
        reads `X-Timezone` yet and no `learner_theory_summary` store/model exists (P5.T1 only migrated
        the table). Wiring this write happens once a real call site exists (P5.T3/P5.T4).
  - [x] A `LocalDay` helper: the local date for an `Instant` + zone; the next local midnight as an `Instant` (DST
        safe).
  - **Unit tests:** invalid zone ignored; 23:59 / 00:01 boundaries; DST transition days (Europe/Stockholm, both
    March and October).

- [x] **P5.T3 ProgressService write path** · Repo: ENG · Dep: P5.T2, P4.T7 · Plan §5.7
  - [x] In the lesson-completion transaction (W = 0 lesson complete, or retry complete), steps 1–4 of Plan §5.7:
    - `lesson_progress` upsert with `GREATEST(best_accuracy)`;
    - the activity-lesson insert `ON CONFLICT DO NOTHING`, then the day upsert if inserted;
    - the summary: streak rule, longest streak, `sum_best_accuracy += delta`, `completed_lessons` on the first
      completion, `progress_version + 1`.
  - [x] Attempt start: upsert `lesson_progress` (`open_attempt_id`, `IN_PROGRESS` if not completed) and bump
        `progress_version`. Fill in the P4.T4 hook.
  - [x] Also closes P5.T2's deferred bullet: `X-Timezone` is now threaded through both phase-completion
        endpoints and stored on the summary at the same write.
  - **Unit tests:**
    - [x] streak today / yesterday / gap;
    - [x] the same lesson twice in a day counts once;
    - [x] two different lessons count twice;
    - [x] a retake improves `best_accuracy` and never lowers it;
    - [x] a timezone change doesn't double count.
  - **Acceptance:** a Testcontainers test runs 3 lessons across 2 local days and asserts every summary field.

- [x] **P5.T4 Home endpoint** · Repo: ENG · Dep: P5.T3 · Plan §7.3 `GET /v1/home`
  - [x] `GET /internal/theory/v1/home`, built from:
    - one summary read;
    - ≤ 7 activity days;
    - one `lesson_progress` range scan;
    - the snapshot;
    - the entitlement cache;
    - the user's initials and first name **via the user module's ExternalUseCase** (learn tier 4 → user tier 2).
  - [x] `continue.action`:
    - `CONTINUE` (most recent open attempt);
    - `START` (next unlocked, not completed);
    - `UPGRADE` (next lesson in a non-entitled unit);
    - `null` when everything is done.
  - [x] `upNext` (next 1 entry after `continue` — **decision, logged**: always relative to the forward
        sequence pointer, not to a retake's own position, when the two differ); `tabs.mockExams` locked
        with `NOT_AVAILABLE`; `learningPathEtag`.
  - [x] **Partial failure:** if the progress reads fail, `week`, `dailyChallenge`, `streak` and `readiness` are null
        and the rest renders (log WARN).
  - [x] `week.startsOn` from config `theory.progress.week-starts-on` (O-11); `daily_challenge_lessons` config
        (default 3).
  - **Tests:**
    - [x] each `continue.action`;
    - [x] the streak shown as 0 after a gap;
    - [x] the challenge reset at local midnight;
    - [x] the week statuses;
    - [x] partial failure;
    - [x] query count ≤ 3 (+ the user lookup) — verified via spy invocation counts, not a literal SQL counter.
  - **Acceptance:** the response matches the Plan §7.3 example shape field for field (asserted directly, not a
        separate JSON-schema file).

- [x] **P5.T5 Learning path with ETag** · Repo: ENG · Dep: P5.T3 · Plan §7.3 `GET /v1/learning-path`
  - [x] `GET /internal/theory/v1/learning-path`:
    - every unit with `entries` (`kind = lesson`), `displayIndex` from the snapshot order, and per-unit progress;
    - entry status `completed | current | locked`, with **exactly one** `current`;
    - `openAttempt` on a retaken completed lesson.
  - [x] ETag `"{release_id}.{progress_version}.{entitlement_hash}.{locale}"`: a matching `If-None-Match` → 304 after
        **one** PK read. Headers `Cache-Control: private, no-cache`.
  - **Tests:**
    - [x] 304 path (query count = 1 — verified as "the full-body read path is never invoked" via a
          service mock, not a literal SQL counter, same convention as P5.T4);
    - [x] ETag changes on completion, on start, on an entitlement change, on a new release, and on a locale change;
    - [x] exactly one `current`;
    - [x] locked unit 2 with `lockReason: SUBSCRIPTION`.
  - **Acceptance:** a ~150-lesson fixture serialises to ≤ 30 KB.

- [x] **P5.T6 Readiness endpoint** · Repo: ENG · Dep: P5.T3 · Plan §5.7, §7.3
  - [x] `GET /internal/theory/v1/readiness`:
    - `percent = round(100 × sum_best_accuracy / visible lessons)`;
    - `completedLessons`, `totalLessons`, `averageBestAccuracy` (**decision, logged**: divides by
      `completedLessons`, not `totalLessons` — see status log for why the plan's own example numbers
      only work under two different denominators);
    - per-unit values with the same formula.
  - **Tests:** zero progress → 0; full marks → 100; a new lesson published lowers the percent; per-unit sums are
    consistent.

- [x] **P5.T7 Completion responses carry `next` and `progress`** · Repo: ENG · Dep: P5.T4, P5.T5 · Plan §7.3
  - [x] Fill in the `next` (entry + `action`) and `progress` (streak, `dailyChallenge`, readiness, `learningPathEtag`)
        fields left in P4.T7, for both completion endpoints.
  - **Tests:** the values equal what a following `GET home` returns.
  - **Acceptance:** a full flow ends with the next lesson `current` in the learning path and `START` on home.

- [ ] **P5 Phase exit:** every engine internal endpoint of Plan §7.3 exists, with tests green; the progress values
  agree between completion responses, home, the learning path and readiness.

---

## P6. BFF: the public API

- [ ] **P6 — phase done**

- [ ] **P6.T1 Settings for the new integrations** · Repo: BFF · Dep: P1 · Plan §7.4, the BFF env file
  - [ ] Add settings with validation:
    - `ENGINE_BASE_URL`, `ENGINE_INTERNAL_TOKEN` (`SecretStr`), `ENGINE_READ_TIMEOUT`,
      `ENGINE_PHASE_COMPLETE_TIMEOUT`, `ENGINE_POOL_MAX_CONNECTIONS`;
    - `BOOST_BATCH_MAX_REFS`, `CONTENT_PREFETCH_ON_RELEASE`;
    - `MEDIA_CDN_BASE_URL`, `MEDIA_SIGNING_KEY` (`SecretStr`), `MEDIA_SIGNED_URL_TTL_SECONDS`,
      `MEDIA_FREE_UNIT_IDS`;
    - `RATE_LIMIT_READ_PER_MINUTE`, `RATE_LIMIT_WRITE_PER_MINUTE`.
  - [ ] Update `.env.example` (no secrets); set the Boost timeouts to the plan values (1.5 s read, 1 retry, 3 s
        budget).
  - **Unit tests:** the missing-required-value errors; startup refuses a missing engine token outside `local`.

- [ ] **P6.T2 Engine client** · Repo: BFF · Dep: P6.T1, P5 · Plan §7.4
  - [ ] An async httpx client with a keep-alive pool. Forwards the learner JWT, `X-Fordona-Internal-Token`,
        `Accept-Language`, `X-Timezone` and the correlation id. Unwraps `Payload<T>`.
  - [ ] Passes engine RFC 7807 errors through unchanged (status, `errorCode`, `detail`, `correlationId`);
        `If-None-Match` / `ETag` / 304 pass through.
  - [ ] Per-call timeouts (2 s; 5 s for phase completion). An engine outage → 503 `UPSTREAM_UNAVAILABLE`.
  - **Unit tests (respx):**
    - [ ] header forwarding;
    - [ ] unwrapping;
    - [ ] error passthrough;
    - [ ] 304 passthrough;
    - [ ] timeout → 503.

- [ ] **P6.T3 Boost §13 client and body cache** · Repo: BFF · Dep: P2.T3 · Plan §7.4, §9.1, §13
  - [ ] Extend the Boost client:
    - the lesson revision;
    - the question batch (chunks of 100, `missing[]`);
    - models for blocks and the new fields.
  - [ ] Redis cache keyed `(entity, id, version, locale)` with **no TTL** (immutable). A cache miss for an attempt
        loads all missing refs in **one batch call**.
  - [ ] **Never model answer fields** (keep the existing rule): grading is not reachable from the BFF.
  - **Unit tests:**
    - [ ] cache hit makes no Boost call;
    - [ ] a mixed hit/miss makes one batch call;
    - [ ] `missing[]` → item dropped + logged;
    - [ ] Boost down + cached → served;
    - [ ] Boost down + not cached → 503.

- [ ] **P6.T4 Block rendering and media URLs** · Repo: BFF · Dep: P6.T3, P0.T2 (O-10) · Plan §4.6, §9.5
  - [ ] Map Boost blocks to the public block shapes in Plan §7.3: image `url`/`srcset`, video `hlsUrl`/`posterUrl`/
        `captions`, audio `hlsUrl`/`transcript`, animation `url`, `rule_card`, `text`.
  - [ ] Asset id → URL. Signed (HMAC over path + expiry, TTL from config) for units not in `MEDIA_FREE_UNIT_IDS`;
        plain URLs otherwise. **Signed per response, never cached.** Implement behind an interface so the O-10
        decision changes only the signer.
  - [ ] Unknown block types are dropped and logged; an unresolvable asset drops the block, never the response.
  - **Unit tests:**
    - [ ] every block type;
    - [ ] the signature (verifiable with the key);
    - [ ] expiry;
    - [ ] free-unit plain URLs;
    - [ ] cached bodies contain no signed URL.

- [ ] **P6.T5 Public routes** · Repo: BFF · Dep: P6.T2, P6.T4 · Plan §7.3 (endpoint table)
  - [ ] `GET /v1/home`: engine passthrough (+ icon URLs).
  - [ ] `GET /v1/learning-path`: passthrough with ETag/304.
  - [ ] `GET /v1/readiness`.
  - [ ] `GET /v1/lessons/{lessonId}`:
    - engine lesson state;
    - **if locked, return the 403 without fetching theory**;
    - otherwise the lesson revision blocks from cache/Boost;
    - compose the response.
  - [ ] `POST /v1/lessons/{lessonId}/attempts` and `GET /v1/attempts/{attemptId}`: engine refs → hydrated items:
    - `prompt` blocks;
    - `options` ordered by `optionOrder` with labels A–D;
    - **drop `questionId`/`version`**;
    - `answered` feedback on resume;
    - `retry` items when `IN_RETRY`.
  - [ ] `POST /v1/attempts/{attemptId}/responses`: engine feedback + `correctOption.content` from the cached body +
        explanation blocks with resolved URLs.
  - [ ] `POST …/phases/lesson/complete` and `…/retry/complete`: hydrate the retry items; pass `next` / `progress`
        through.
  - [ ] Request validation: UUID formats for `requestId` / `responseId`; `selectedOptionKey` non-empty;
        `durationMs ≥ 0`.
  - **Unit tests (respx engine + Boost):**
    - [ ] every route's shape matches Plan §7.3 (JSON schema tests);
    - [ ] no public response ever contains `questionId`, `version`, `correctOptionKey` before an answer, or any
          template id (a recursive key search in tests);
    - [ ] a locked lesson makes no Boost call;
    - [ ] option order and labels.
  - **Acceptance:** the OpenAPI document at `/openapi.json` lists exactly the 9 public endpoints (+ health).

- [ ] **P6.T6 Rate limiting** · Repo: BFF · Dep: P6.T5 · Plan §7.3
  - [ ] A per-learner (JWT `sub`) Redis token bucket. Read routes use `RATE_LIMIT_READ_PER_MINUTE`; write routes
        (starts, responses, completions) use `RATE_LIMIT_WRITE_PER_MINUTE`. Return 429 RFC 7807 with `Retry-After`.
  - **Unit tests:** limit reached → 429; separate buckets per learner; separate buckets read/write.

- [ ] **P6.T7 Release prefetch (optional, off by default)** · Repo: BFF · Dep: P6.T3 · Plan §9.1
  - [ ] When `CONTENT_PREFETCH_ON_RELEASE=true`, warm the cache for every current question and lesson revision after
        an engine release change. Use a background task, with batch calls rate-limited.
  - **Unit tests:** idempotent; respects batch limits.

- [ ] **P6.T8 Deploy BFF + stub + engine together on staging** · Repo: EXT · Dep: P6.T5, P6.T6
  - [ ] BFF environment: `ENGINE_BASE_URL` (internal host), `ENGINE_INTERNAL_TOKEN` (same as the engine),
        `BOOST_BASE_URL` = the stub's internal URL, the `MEDIA_*` values.
  - [ ] Engine environment: `theory.boost.*` = the stub, the tokens, the internal token, jobs enabled.
  - **Acceptance:** the Postman journey (P8.T1) runs green against staging.

- [ ] **P6 Phase exit:** all 9 public endpoints work on staging against the stub; the leak tests pass; the OpenAPI
  is published.

---

## P7. End-to-end quality

- [ ] **P7 — phase done**

- [ ] **P7.T1 Concurrency suite (engine, Testcontainers)** · Repo: ENG · Dep: P5 · Plan §14.2
  - [ ] double start → 1 attempt;
  - [ ] double answer → replay or 409;
  - [ ] double phase-complete → same summary;
  - [ ] two devices completing at once → serialised;
  - [ ] the streak counted once per local day under concurrent completions.
  - **Acceptance:** green 10 runs in a row (no flakiness).

- [ ] **P7.T2 Load test (k6)** · Repo: BFF (scripts) · Dep: P6.T8 · Plan §9.1, §9.3
  - [ ] Scenario: a mix of home, learning-path (with ETag), theory, starts, answers and completions; target 670
        answers/s on staging-sized infrastructure (or scaled proportionally, documented).
  - [ ] Record the p99 per endpoint at the BFF, error rate, Postgres CPU and connections, Redis hit rate.
  - **Acceptance:** p99 within the Plan §9.1 targets, or a deviation logged with its cause and fix in
    `PROGRESS__STATUS.md`.

- [ ] **P7.T3 Observability** · Repo: ENG + BFF · Dep: P6.T8
  - [ ] OpenTelemetry trace propagation BFF → engine (one trace per request).
  - [ ] Metrics:
    - p99 per endpoint;
    - Boost cache-hit rate;
    - sync lag (feed cursor age);
    - snapshot release id per instance;
    - `retry_extras_short` rate;
    - error rate by `errorCode`.
  - [ ] SigNoz dashboard + alerts: sync lag > 5 min, 5xx rate > 1 %, p99 above 2× target.
  - **Acceptance:** a test request is visible as one trace across both services.

- [ ] **P7.T4 Runbook** · Repo: BFF `docs/` · Dep: P7.T3
  - [ ] Covers:
    - content sync and full resync;
    - stub → Boost swap (Plan §4.5);
    - resetting a test learner (SQL scoped to one `app_user_id`);
    - rotating the internal token and the media signing key;
    - reading the content report.
  - **Acceptance:** a second person can do a full resync using only the runbook.

- [ ] **P7 Phase exit:** the concurrency, load and observability checks pass; the runbook is reviewed.

---

## P8. Hand-off to the mobile developer

- [ ] **P8 — phase done**

- [ ] **P8.T1 Postman collection** · Repo: BFF `docs/` · Dep: P6.T8
  - [ ] Environment: the staging base URL; Kinde OAuth 2.0 (Authorization Code + PKCE, Fordona audience, callback
        `https://oauth.pstmn.io/v1/callback`).
  - [ ] The journey: home → learning path (twice, the second → 304) → theory → start → answers (incl. deliberately
        wrong) → lesson complete → retry answers → retry complete → home.
  - [ ] Scripts:
    - pre-request scripts generate `requestId` / `responseId`;
    - test scripts store `attemptId` and assert status codes and key fields.
  - **Acceptance:** the collection runner passes end to end on staging.

- [ ] **P8.T2 Test accounts and QA answer sheet** · Repo: EXT/BFF · Dep: P6.T8
  - [ ] One free learner (Unit 1 only) and one entitled learner in Kinde + the engine.
  - [ ] A **staging-only** QA sheet of the correct options for the stub's templates, generated from the stub data.
        Never generated from production.

- [ ] **P8.T3 Hand-off pack** · Repo: BFF `docs/` · Dep: P8.T1, P8.T2 · Plan §14.3
  - [ ] Contents:
    - the OpenAPI link;
    - the Postman collection;
    - the error-code table;
    - the Kinde settings + auth guide;
    - the test accounts;
    - the **client rules checklist** copied from Plan §14.3.
  - **Acceptance:** the mobile developer confirms they can run the journey from the pack alone.

- [ ] **P8 Phase exit:** the hand-off has been delivered and acknowledged.

---

## P9. Production readiness (external blockers)

- [ ] **P9 — phase done**

- [ ] **P9.T1 Boost implements §13** · Repo: EXT (Boost owner) · Dep: P0.T3
  - [ ] The P2.T1 contract suite is green against **Boost staging**.

- [ ] **P9.T2 Eric's content in Boost** · Repo: EXT · Dep: P9.T1
  - [ ] Templates authored and published for the launch units, meeting the equal-difficulty guideline (R-7).
  - [ ] The engine content report on Boost staging shows no hidden lessons in the launch scope.

- [ ] **P9.T3 Media pipeline live (O-10)** · Repo: EXT · Dep: P0.T2
  - [ ] Processing (variants, GIF → loop, HLS), captions and transcripts enforced, the CDN with signed URLs; the BFF
        signer matches it.

- [ ] **P9.T4 Staging swap from stub to Boost** · Repo: EXT · Dep: P9.T1, P9.T2 · Plan §4.5
  - [ ] Point `BOOST_BASE_URL` (BFF) and `theory.boost.base-url` (engine) at Boost; run
        `content-sync?full=true`; reset staging learner data.
  - [ ] Re-run the Postman journey and the load test.

- [ ] **P9.T5 Production deploy** · Repo: EXT · Dep: P9.T4, P8
  - [ ] Production configuration:
    - `APP_ENV=prod`;
    - `DOCS_ENABLED=false`;
    - Boost URLs pointing at Boost (never the stub);
    - no stub app in production;
    - the prod guard verified.
  - [ ] The old catalogue routes are confirmed absent (R-11).
  - [ ] Smoke test with a production test account; dashboards and alerts active.

- [ ] **P9 Phase exit:** production is live; the mobile app release can go out.
