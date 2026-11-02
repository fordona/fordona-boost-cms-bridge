# Fordona Theory: Progress Status

The diagnostics and reports log for `BFF_IMPLEMENTATION_PROGRESS.md`:
- what was done in each task and phase;
- test results;
- problems found;
- whether the next work is ready to start.

**Rules:**
- **Append only.** Add the newest entry at the bottom; never edit or delete earlier entries. To correct one, add a new
  entry that references it.
- **One entry per task**, written when the task ends (done, partly done, or blocked). Add one more entry per phase
  when the phase exit checks run.
- **Real numbers.** Use real test commands and counts. Never write "tests pass" without the command and its output
  summary.
- **Blocked tasks:** if a task is blocked, set **Ready to continue: NO** and state exactly what is needed and from
  whom.

---

## Entry template

```markdown
### <YYYY-MM-DD> · <Task or phase ID, e.g. P4.T5> · <short title>

- **Status:** DONE | PARTIAL | BLOCKED
- **Repo / branch / commit:** <ENG|BFF> · <branch> · <short sha>
- **What was done:** <2–5 bullets>
- **Tests:**
  - Unit: `<command>` → <passed>/<total>, <failures if any>
  - Acceptance: <check> → <result>
- **Deviations from the plan:** <none | what and why; link the decision>
- **Issues found / open risks:** <none | list>
- **Ready to continue:** YES | NO: <what blocks it and who must act>
- **Next task:** <ID>
```

---

## Log

### 2026-11-02 · P0.T1 · Plan, tracker and log in one readable place

- **Status:** DONE
- **Repo / branch / commit:** BFF · feat/theory-app-implementations · (this commit, "docs(theory): add the theory first-shipment plan, tracker and log (P0.T1)") · ENG · feat/theory-app-implementations · 482b9e8f
- **What was done:**
  - Committed `docs/fordona-theory-first-shipment-architecture.md`, `docs/BFF_IMPLEMENTATION_PROGRESS.md` and
    `docs/PROGRESS__STATUS.md` in the BFF (they were present but untracked).
  - Added a one-line "Theory first shipment" pointer to `fordona-engine/CLAUDE.md` (Project Overview) naming
    `../fordona-boost-cms-bridge/docs/` as the only live copy.
- **Tests (baseline; this task changes no code):**
  - BFF: `uv run pytest -q` → 189 passed, 6 skipped / 195 (skips: `tests/integration/test_snapshot_repository.py`,
    "Docker is not available"); `uv run ruff check .` → all checks passed; `uv run mypy src` → no issues in 44 files.
  - ENG: `./gradlew test` → 1292 tests, 1235 passed, 26 failed, 31 skipped. All 26 failures are
    `initializationError` of Testcontainers-based classes (25 × `NoClassDefFoundError: IntegrationTestBase`,
    1 × `ExceptionInInitializerError` in `FordonaEngineApplicationTests`). Root cause is the local machine, not code:
    Testcontainers' `DockerMachineClient` throws `InvalidPathException: Trailing char < > at index 10: C:\Program `
    because the **Machine PATH contains a broken entry `C:\Program `**; Docker Desktop is also not running
    (`docker info` fails). The only diff in the engine is one line of `CLAUDE.md`.
  - Acceptance: the three files exist at `fordona-boost-cms-bridge/docs/`, and the engine's `CLAUDE.md` names that
    path → met.
- **Deviations from the plan:** none.
- **Issues found / open risks:**
  - Identical copies of the plan, tracker and log also sit in the parent folder `Fordona Work/` (outside both
    repos). They will drift from the live copy; owner should delete or archive them.
  - **No Testcontainers test can run on this machine** until the Machine PATH entry `C:\Program ` is removed and
    Docker Desktop is started. This blocks the Testcontainers acceptance checks from P3.T2 onwards, and the
    engine's existing integration suite.
  - The BFF repo has no `CLAUDE.md` or `.claude/rules`; its conventions are taken from the code and `pyproject.toml`.
- **Ready to continue:** YES for P0.T1. The P0 phase is not complete (see the next entry).
- **Next task:** P0.T2–P0.T4 (EXT, owner).

### 2026-11-02 · P0 · Phase exit check

- **Status:** BLOCKED (external)
- **Repo / branch / commit:** — 
- **What was done:** ran the P0 exit check: "T1–T4 ticked; no BLOCKED entries open".
- **Tests:** n/a (see the P0.T1 baseline above).
- **Deviations from the plan:** none.
- **Issues found / open risks:** P0.T2 (product sign-offs), P0.T3 (credentials, §13 hand-off to the Boost owner)
  and P0.T4 (Postgres hardening) are owner tasks and unticked.
- **Ready to continue:** NO. Needs the owner to complete P0.T2–T4, or to explicitly allow P1.T1 and P2.T1 (which
  depend only on P0.T1) to start before the P0 exit. P2.T2 additionally needs the Boost delivery token (P0.T3); P3
  needs all of P0.
- **Next task:** P1.T1 once allowed.

### 2026-11-02 · P1.T1 · Retire the leaky catalogue routes

- **Status:** DONE
- **Repo / branch / commit:** BFF · feat/theory-app-implementations · 5aa0b87 (code), 163ad2b (new `CLAUDE.md`,
  requested by the owner before this task)
- **Owner decision recorded:** the owner allowed P1.T1 to start before the P0 phase exit (2026-11-02).
- **What was done:**
  - **Client search:** `grep` over the working trees and `git grep` over every local and remote-tracking ref of
    `fordona-trafikskola-web` (24 refs) and `fordona-next` (8 refs), plus `fordona_chat_app`, `chat_app`,
    `fordona-ai-analysis`, for `/v1/questions`, `/v1/modules`, `/v1/lessons/…/questions`, `boost-cms-bridge`,
    `boost_bridge`. **No caller found.** The only hits were the engine's own `/v1/theory/lessons/{id}/questions/…`
    routes in `fordona-trafikskola-web/api-migration-guide.md`, which are not BFF routes. No migration path needed.
    Limit: remote refs are as of their last fetch, and no Flutter/mobile repo exists locally.
  - Deleted `api/routes/questions.py`, `api/routes/modules.py`, the `/{lessonId}/questions` route, and everything
    used only by them: `ContentService` module/question methods, `services/sequencing.py` (the sequencer existed
    only for lesson questions; the engine's `QuestionSetSelector` replaces it), `to_module`/`to_question`/
    `asset_url` mappers, `schemas/modules.py`, `schemas/questions.py`, `schemas.common.Media`.
  - Kept `GET /v1/lessons/{lessonId}` (new meaning in P6.T5) and `GET /v1/lessons` (not named by Plan §15 or the
    tracker; see open issues).
  - Kept the Boost client layer (`clients/boost/*` incl. module/question requests and their unit tests) unchanged:
    the tracker scopes deletion to routes, service methods and schemas, and P6.T3 rewrites the client for §13.
  - Tests: cross-cutting API tests (auth, forward-token mode, locale, pagination validation, caching, 404/502/503/504,
    stale snapshot, Redis down, correlation id, CORS, OpenAPI) and the whole login-security demo were **retargeted**
    from `/v1/modules*` onto the lesson routes, so that coverage is kept, not deleted. Tests of deleted behaviour
    (question mapping/answer-free guard on question routes, `ids` batch parsing, question revision, lesson-question
    paging, sequencer extension point, module mapping, module lessons) were removed with the routes. New
    `tests/api/test_retired_routes.py`: two route-table tests over `app.routes` and a 404 + "never reaches Boost"
    check for each of the 7 retired paths. The OpenAPI no-answer-field check now covers every component schema.
  - `README.md` route table and examples updated; the app's OpenAPI description no longer advertises questions.
- **Tests:**
  - Unit/API: `uv run pytest -q` → 186 passed, 0 skipped / 186 (Docker is now running, so the integration tests
    ran: `uv run pytest -q -m integration` → 7 passed). Count check: 195 before − 18 removed + 9 new = 186.
  - `uv run ruff check .` → all checks passed; `uv run ruff format --check .` → 70 files already formatted;
    `uv run mypy src` → no issues in 39 source files.
  - (`uv run mypy tests` is not a repo check; it reports 34 errors both before and after this change, all
    pre-existing, e.g. `tests/conftest.py:71` `Settings(**values)` arg-type.)
  - Acceptance: a local `uvicorn boost_bridge.main:app` run returned **404** for `GET /v1/questions`,
    `GET /v1/lessons/1/questions` and `GET /v1/modules` (problem+json, `errorCode` `NOT_FOUND`), and 401 for
    `GET /v1/lessons/1` without a token; `/openapi.json` lists only `/health/live`, `/health/ready`,
    `/v1/lessons`, `/v1/lessons/{lessonId}` → met.
- **Deviations from the plan:** none.
- **Issues found / open risks:**
  - **QUESTION for the owner (blocks the P1 phase exit, not P1.T1).** Until P6.T5, `GET /v1/lessons/{lessonId}`
    still returns the full theory (`contentHtml`, resources) of **any** published lesson, paid units included, to
    any signed-in user, and `GET /v1/lessons` lists every lesson. That contradicts Plan R-8 / §7.3 ("the BFF
    doesn't serve theory for locked lessons at all") and the P1 exit check "no leaky route exists in any deployed
    build", while P1.T2 deploys this build to staging. Options:
    (a) accept it for **staging only** (no real paid content in Boost yet, and P6.T5 replaces the route) and record
        the exception;
    (b) also remove `GET /v1/lessons` and `GET /v1/lessons/{lessonId}` now, so the deployed BFF serves only health
        probes until P6;
    (c) keep the routes but return 404 until the engine check exists.
    Recommendation: (b). It is the only option where the P1 exit holds as written, nothing calls these routes, and
    P6.T5 re-adds the path with the engine's lock check. Note that P6.T5's acceptance ("exactly the 9 public
    endpoints") already requires `GET /v1/lessons` to be gone.
  - `mypy tests` is not clean (34 pre-existing errors). Not a repo standard today; worth fixing separately.
- **Ready to continue:** YES for P1.T1. The P1 phase exit needs the decision above plus P1.T2 (needs P0.T3 and P0.T4).
- **Next task:** P1.T2 (BFF/EXT; blocked on P0.T3, P0.T4) or P2.T1 if the owner allows it.

### 2026-11-02 · P1.T1 (addendum) · Lesson routes removed until P6.T5

- **Status:** DONE
- **Repo / branch / commit:** BFF · feat/theory-app-implementations · 788c761
- **Owner decision recorded (2026-11-02):** option (b) of the question in the P1.T1 entry: remove
  `GET /v1/lessons` and `GET /v1/lessons/{lessonId}` now. P6.T5 re-adds `GET /v1/lessons/{lessonId}` with the
  engine's lock check; `GET /v1/lessons` does not come back (it is not in Plan §7.3).
- **What was done:**
  - Deleted the lesson routes and everything used only by them: `api/router.py`, `api/routes/lessons.py`,
    `api/responses.py`, `services/content_service.py`, `services/mappers.py`, `schemas/lessons.py`,
    `schemas.common.Page`/`Localized`, and the content deps (`Content`, `serve`, `PageNumber`, `PageSize`).
    `container.py` no longer builds the Boost HTTP client or the content cache; `Services` holds the verifier and
    the readiness checks. The routed surface is now `/health/live` and `/health/ready` only.
  - Kept, as P6 building blocks with their unit tests: the auth and locale dependencies (`CurrentLearner`,
    `Locale`), `clients/boost/*`, `services/content_cache.py`, `cache/*`, `db/*` (snapshot store; readiness still
    pings Postgres and Redis), `schemas.common.Problem`/`ContentId`.
  - Tests: the harness mounts a **test-only probe route** (`/v1/__probe`, `tests/conftest.py`) that depends on the
    real `CurrentLearner` and `Locale`, so the auth boundary is still tested end to end through HTTP. New
    `tests/api/test_auth_boundary.py` (auth 401 cases, valid token, auth-disabled local, locale default /
    `Accept-Language` / query precedence / 422, correlation id, CORS preflight, no answer fields in any OpenAPI
    schema). The login-security demo now runs against the probe. Removed `tests/api/test_content_routes.py` and
    `tests/demo/test_endpoints_showcase.py`: their content-route behaviour (mapping, stale snapshot, 502/503/504,
    Redis down) is deleted with the routes, and the underlying cache and client behaviour stays covered by
    `tests/unit/test_content_cache.py` (22 tests) and `tests/unit/test_boost_client.py` (21 tests).
  - **Bug found and fixed in my P1.T1 test (5aa0b87):** `test_route_table_has_no_retired_path` filtered
    `app.routes` on `APIRoute`, but FastAPI 0.143 wraps included routers (`_IncludedRouter`), so the set was empty
    and the test **passed vacuously**. It now reads `app.openapi()["paths"]` (verified against the previous commit:
    it returns `/v1/lessons`, `/v1/lessons/{lessonId}` and the health paths), and the new exact check
    `test_route_table_serves_only_health_probes` fails if the set is ever empty. The 404 behaviour tests were not
    affected. Recorded in `CLAUDE.md` "Known gaps".
  - `README.md` and `CLAUDE.md` updated for the health-only surface.
- **Tests:**
  - `uv run pytest -q` → 165 passed / 165, 0 skipped (`-m integration` → 7 passed; Docker running).
  - `uv run ruff check .` → all checks passed; `uv run ruff format --check .` → 63 files already formatted;
    `uv run mypy src` → no issues in 33 source files.
  - Acceptance (local `uvicorn`): `GET /v1/questions`, `/v1/lessons/1/questions`, `/v1/modules`, `/v1/lessons`,
    `/v1/lessons/1` → 404; `/health/live` → 200; `/openapi.json` paths = `/health/live`, `/health/ready`.
- **Deviations from the plan:** `GET /v1/lessons/{lessonId}` is absent between now and P6.T5 (owner decision).
- **Issues found / open risks:** none new. The P1 exit check "no leaky route in any deployed build" now holds for
  this build.
- **Ready to continue:** YES. P1.T2 is blocked on P0.T3 and P0.T4 (owner). Continuing with P2.T1 per the owner's
  instruction to continue implementing (its only dependency, P0.T1, is ticked).
- **Next task:** P2.T1.

### 2026-11-02 · P2.T1 · Contract test suite for §13

- **Status:** PARTIAL (all sub-tasks done; the acceptance run with real tokens waits on P0.T3)
- **Repo / branch / commit:** BFF · feat/theory-app-implementations · 699f8b6
- **Owner instruction recorded:** "continue implementations" (2026-11-02), so P2.T1 started while P1 is still open
  (P1.T2 is blocked on P0.T3 and P0.T4). P2.T1's only dependency, P0.T1, is ticked.
- **What was done:**
  - `tests/contract/boost_content_v1/`: 52 black-box tests in 7 modules (change feed 7, templates 11, lesson
    revision 4, question revisions 10, grading 6, topics 3, lists/`id=`/ETag 11). It never imports `boost_bridge`
    or `boost_stub`, so it judges the server against §13, not against our models.
  - Beyond the tracker's list, these §13 rules are also checked: the template publish rules that are visible from
    outside (≥ 3 questions, all published, all in the template's module); `correctOptionId` is one of the
    delivered options of the same revision; every question's `topicKey` is in its module's topic vocabulary;
    delivery batch responses carry no answer field anywhere (recursive key search); Boost's error envelope
    (`status`, `code`) on 410/422; the batch honours `locale`; unknown revisions → 404.
  - `blocks.py`: the §4.6 validator (types, required fields, "Allowed in" per context, prompt starts with
    `text`, per-locale explanation maps), with 40 unit tests in `tests/unit/test_contract_blocks.py`.
  - Config: skips entirely without `CONTRACT_BOOST_BASE_URL`; refuses a run with a base URL but no tokens
    (`pytest.UsageError`) so a half-configured run can't look green. No I/O at fixture setup, so any server
    problem is a test **failure**, never a setup error. Marker `contract` registered in `pyproject.toml`.
  - CI: the repo had none. Added `.github/workflows/ci.yml` (GitHub Actions): job `checks` (ruff, ruff format,
    `mypy src`, `pytest -m "not contract"`, which includes the Docker integration tests) and a separate job
    `contract-boost` fed from repository secrets `CONTRACT_BOOST_BASE_URL`, `CONTRACT_DELIVERY_TOKEN`,
    `CONTRACT_GRADING_TOKEN`, `CONTRACT_EXPIRED_CURSOR` (skips while unset). P2.T3 adds a job against the stub.
- **Tests:**
  - `uv run pytest -q` → 205 passed, 52 skipped (the contract suite, no base URL) / 257.
    `uv run pytest -q -m "not contract"` → 205 passed, 52 deselected. Block validator: 40/40.
  - `uv run ruff check .` → all checks passed; `uv run ruff format --check .` → 77 files already formatted;
    `uv run mypy src` → no issues in 33 files; `uv run mypy --strict tests/contract` → no issues in 13 files.
    `.github/workflows/ci.yml` parses as YAML; `uv lock --check` → lockfile up to date.
  - Half-configured run (`CONTRACT_BOOST_BASE_URL` only) → refused: "CONTRACT_BOOST_BASE_URL is set but
    CONTRACT_DELIVERY_TOKEN, CONTRACT_GRADING_TOKEN is not".
  - Acceptance, **partial**: against today's Boost (`https://boost-api.fordona.io`) with **placeholder** tokens
    → 50 failed, 2 passed, **0 errors**, in 17.4 s. Every failure is an assertion that names the request and the
    response; the 2 passes are the two token-scope tests, where a rejected token is the expected result. This
    proves the suite fails cleanly. It does **not** yet prove the assertions are meaningful, because every call
    stops at 401. That needs a real delivery token and grading token (P0.T3), after which the expected result is
    404s and shape failures on the endpoints §13 adds.
  - The CI workflow has not run yet: nothing is pushed (owner's rule).
- **Decisions taken where the plan is silent (please confirm or correct):**
  1. **Expired cursor:** a black-box test cannot age a cursor by 30 days, so the server's operator supplies one in
     `CONTRACT_EXPIRED_CURSOR`. Unset → that one test **fails** with instructions (not skipped). The stub
     (P2.T3) must therefore offer a known-expired cursor, and the Boost owner must supply one for staging.
  2. **Image `width`/`height` are optional** (positive integers when present). §4.6 lists them, but §13.4's
     option example omits them. If they are meant to be required, the §13.4 example is wrong.
  3. **Video `captions`:** required as a non-empty list whose entries each have a `locale`. The plan doesn't
     define the entry's other fields (asset id vs URL), so the suite doesn't check them.
  4. **Not contract-tested** (they can't be checked reliably from outside): commit-order safety, at-least-once
     delivery, 30-day retention, latency p99, and gzip/brotli (servers skip compressing small bodies). The
     out-of-range `limit` on the feed, and `id=` lists over 100 ids, are not tested because §13 doesn't say what
     they return.
  5. **CI provider:** GitHub Actions, since the repo is on GitHub and had no CI. `uv` is pinned to the
     Dockerfile's version and installed from PyPI, like the Dockerfile.
- **Deviations from the plan:** none.
- **Issues found / open risks:**
  - The suite has not yet passed against any conforming server; the first green run will be against the stub in
    P2.T3. A suite bug could surface there.
  - Discovery builds on the **first published template**. A server with templates but an empty change feed, or
    without topics for that module, fails the "precondition" assertions. That is intended: §13 requires both.
- **Ready to continue:** NO, blocked on the owner. P2.T1's acceptance, P2.T2 (needs a Boost delivery token to read
  today's Boost) and therefore P2.T3, plus all of P3 (needs P0), wait on **P0.T3: a Boost delivery token and a
  grading token** (P0.T2/P0.T4 for P3 too). No task in the tracker has all its dependencies ticked now.
- **Next task:** finish P2.T1's acceptance run, then P2.T2, once the P0.T3 tokens exist.

### 2026-11-02 · P2.T2 · Template generator (code only)

- **Status:** PARTIAL (all sub-tasks done; the live run and the committed `stub-data/` files wait on P0.T3)
- **Repo / branch / commit:** BFF · feat/theory-app-implementations · d35aff4
- **Owner decision recorded (2026-11-02):** start P2.T2 before its dependency P0.T3 is ticked, building the code
  and unit tests without Boost; only the final run against today's Boost waits for the delivery token.
- **What was done:**
  - `scripts/stub_data/generator.py`: the pure core, with no I/O, clock or randomness.
    - Per published lesson, questions with difficulty 1–5 are sorted by `(difficulty, id)` and dealt round-robin
      (question i → template i mod k) into `k = max(1, floor(n/8))` templates.
    - Lessons with < 3 real questions are topped up to 8 with `[DEMO]` questions.
    - Template ids start at 9,000,001 and synthetic-question ids at 9,500,001 (both ≥ 9,000,000). Each is keyed by
      `(lessonId, sort)` / `(lessonId, slot)`, so it is stable across runs. Ids are **never reused**:
      `nextTemplateId` / `nextQuestionId` are carried in the files.
    - `version` bumps only when a template's membership or order changes, or a synthetic question's content
      changes. `generation` bumps only when either file changes.
    - Output is sorted-key UTF-8 JSON with a trailing newline (`render`).
  - `scripts/stub_data/synthetic.py`: six `[DEMO]` variants, complete in both locales (prompt, options, correct
    option, per-locale explanation). Together they show text, image, an image option, lottie and video_loop
    animations, video with captions, audio with a transcript, and RULE and SIGN rule cards, each only where §4.6
    allows it. A thin lesson always gets ≥ 6 consecutive variants, so **any one thin lesson shows every block
    type**. Asset ids are `demo/...` placeholders.
  - `scripts/stub_data/boost_source.py`: paged delivery reads (`pageSize` 250, `sv-SE`) of modules, lessons and
    questions, reading only ids, a lesson's module, and a question's lesson, subject and difficulty. It accepts the
    nested and the flat item shape and fails loudly on any non-200.
    `scripts/generate_stub_templates.py`: the CLI (`uv run python -m scripts.generate_stub_templates`). It reads
    `BOOST_BASE_URL` / `BOOST_DELIVERY_TOKEN` from the process environment only (never `.env`), reads the previous
    files, writes both, and prints a report (skipped questions with reasons, topped-up lessons, missing demo media).
  - CI and `CLAUDE.md`: mypy now covers `src scripts`.
- **Tests:**
  - New: `tests/unit/test_stub_template_generator.py` and `tests/unit/test_stub_generator_io.py` → 59 passed.
    - Tracker items: byte-identical output across runs (also with shuffled input); per-level counts per template
      differ by ≤ 1 for n ∈ {8, 16, 17, 24, 29, 40, 47}; thin-lesson top-up 0/1/2 → 8/7/6 synthetic and 3 → none;
      id range and distinctness.
    - Beyond them: k and remainder sizes; dealing order; never-reused ids after shrink and regrow; version bump
      only for the changed lesson; synthetic content change bumps version and keeps id; re-run → no diff (also
      through the files); every synthetic variant validated with the contract suite's §4.6 validator in both
      locales, with the correct option among the options; Boost reader paging, nested/flat parsing, and error.
  - Mutation check (temporary edits, reverted): chunked dealing → 6 failures; always-bump versions → 4 failures;
    id reuse from the current file's max → 1 failure. The tests are not vacuous.
  - Full suite: `uv run pytest -q` → 264 passed, 52 skipped (contract suite, no base URL) / 316.
    `uv run ruff check .` → all checks passed; `uv run ruff format --check .` → 85 files already formatted;
    `uv run mypy src scripts` → no issues in 39 source files.
  - The script without a token exits 1 with "BOOST_DELIVERY_TOKEN is required" and writes nothing.
  - Acceptance (**pending P0.T3**): generated files committed, and a re-run produces no diff. Covered by
    `test_rerun_produces_no_diff` on fixture data, but not yet run on real Boost data.
- **Decisions taken where the plan is silent (please confirm or correct):**
  1. **Stable ids and the never-reuse counters.** The plan says "ids from a reserved range". Without stability,
     every regeneration would renumber templates, and the engine would see every template as new. Without
     never-reuse, a removed id could come back with different questions under an attempt that pinned it.
  2. **Separate sub-ranges:** templates from 9,000,001, synthetic questions from 9,500,001, both inside the
     reserved range, so an id alone tells which kind it is.
  3. **Synthetic subject (domain):** the most common `subjectId` among the module's real questions, else the
     bank's. The engine excludes questions with an unknown domain (§4.4), so a synthetic question without one
     would hide its whole template.
  4. **Questions with a missing or out-of-range difficulty, or no published lesson, are skipped and reported**,
     not dealt. They would be excluded at engine sync anyway and would skew the difficulty mix.
  5. **Template titles** are labels (`Mall A` / `Template A`), not the lesson's title: §13.4 calls the title an
     internal label, and labels keep the output independent of lesson-title edits.
  6. **`synthetic.json` record shape** is locale-neutral (`translations` + `explanation` per locale +
     `correctOptionId`); P2.T3's stub renders it into the §13.4 delivery and grading shapes.
- **Issues found / open risks:**
  - **QUESTION (P2.T2 acceptance):** the tracker requires `synthetic.json` to show every block type, but synthetic
    questions exist only for thin lessons (< 3 real questions). If today's Boost has **no** thin lesson,
    `synthetic.json` is empty and the stub has no rich-media demo content at all. The generator then prints a
    warning, and `test_no_thin_lesson_reports_the_missing_demo_media` covers that. Options:
    (a) accept it; rich media then appears only once Eric authors it;
    (b) always add one `[DEMO] Media showcase` template to the first lesson, built from the six variants,
        whatever its real question count.
    Recommendation: decide after the first live run shows whether any thin lesson exists. If none does, (b).
  - Boost's delivery field names (`shared.lessonId`, `shared.difficulty`, `shared.subjectId`,
    `shared.moduleId`) are still **inferred** (README). The live run will be their first real check.
  - The `demo/...` media files must exist in the dev media bucket for the BFF to resolve them (ops, O-10).
- **Ready to continue:** NO, blocked on the owner. P2.T1's and P2.T2's acceptance runs need **P0.T3: a Boost
  delivery token and grading token**. P2.T3 depends on both being ticked; P3 needs all of P0.
- **Next task:** with the tokens: P2.T1 acceptance run → P2.T2 live run and commit of `stub-data/` → P2.T3.


### 2026-11-02 · P2.T3 · Boost stub service

- **Status:** PARTIAL (one sub-item deliberately deferred; the task cannot be ticked while its
  dependencies P2.T1 and P2.T2 are themselves PARTIAL — see those entries)
- **Repo / branch / commit:** BFF · feat/theory-app-implementations · 6f8c0f9
- **Owner instruction recorded:** "continue implementations" (2026-11-02). P2.T3's own dependencies are both
  PARTIAL (P2.T1, P2.T2), so this is a second layer of "started ahead of the tracker's order" — recorded so a
  later session knows this was deliberate, not an oversight.
- **What was done:**
  - `src/boost_stub/`: a second FastAPI app (`config.py`, `logging.py`, `upstream.py`, `auth.py`, `changes.py`,
    `data.py`, `transforms.py`, `container.py`, `deps.py`, `responses.py`, `main.py`, `routes/*`), independent of
    `boost_bridge` (no shared imports; it has its own settings/logging/HTTP-client code).
  - **Change feed** (`changes.py`, `container.poll_once`): polls Boost's module/lesson/question lists plus the
    generated templates/synthetic questions every `STUB_POLL_SECONDS` (default 60), diffs against a SQLite
    snapshot (`tracked_entity`), writes one `change_log` row per PUBLISHED/UNPUBLISHED difference with a strictly
    increasing `seq`. `feed()` hides a row until `STUB_VISIBILITY_LAG_SECONDS` after it was written (commit-order
    safety, §13.3) and raises `CursorExpiredError` for a cursor at or before the purge watermark (`purge()`,
    `STUB_RETENTION_SECONDS`).
  - **Question templates and topics**: served entirely from `GeneratedData` (`data.py`, loads
    `stub-data/templates.json`/`synthetic.json`), no Boost call. Topics are derived — one per lesson with a
    published template in the module, matching the `lesson-{lessonId}` key every question is given.
  - **Lessons and questions**: proxied from Boost (existing lists + the new `/revisions/{version}` endpoints),
    with `transform_lesson_item`/`transform_question_item` (`transforms.py`) adding `translation.blocks` /
    `shared.topicKey` + `translation.prompt`/`options[].blocks`, keeping the legacy plain-text fields. The
    multi-value `id=` filter (§13's requirement, Boost's own support unverified) is enforced by the stub itself:
    a filtered list request fetches every page from Boost and filters in Python, never trusting upstream to do it.
  - **Batch endpoints** (new, §13.2 #5/#6): `questions/revisions` and `grading/questions/revisions` split a
    ref list into synthetic (served locally) and real (fanned out in parallel to Boost's existing single-revision
    endpoints via `asyncio.gather`), merging `missing[]` for anything not found. Grading calls Boost **once per
    configured locale** per real ref to assemble the multi-locale `explanation` map, since today's Boost is
    presumed to answer one locale at a time (matches `boost_bridge`'s own "still unverified" caveat for delivery).
  - **No identity of its own**: every stub endpoint — proxied or local — probes the caller's token against Boost
    itself before serving (`auth.py`): a delivery-scoped call to `GET /v1/delivery/modules`, a grading-scoped call
    to a reserved, never-real id at the existing single-revision grading path (404 = valid scope). A success is
    cached 30 s per token; a failure is never cached, so a token that starts working is picked up immediately.
  - **Isolation** (plan §4.5): `boost_stub` excluded from `[tool.hatch.build.targets.wheel].packages`, so it is
    never installed as part of the project wheel; a new Dockerfile stage `boost-stub` runs it from source
    (`PYTHONPATH=/app/src`) with the shared dependency set, while the `runtime` stage is untouched. Added
    `import-linter` (new dev dependency) with an `independence` contract between `boost_bridge` and `boost_stub`,
    wired into the CI `checks` job.
- **Tests:**
  - New unit tests: `test_transforms.py` (23), `test_changes.py` (15), `test_auth.py` (13), `test_data.py` (9),
    `test_container.py` (3), `test_isolation.py` (2) — 65 total, all passing.
  - **`test_stub_against_contract_suite.py`**: the actual P2.T1 suite, run as a subprocess, against a **live**
    instance of the stub (real `uvicorn.Server`s on real sockets, in threads) backed by a small in-process
    stand-in for Boost (`fake_boost.py`) built from `fixture_data.py` (2 modules; one lesson with 9 real
    questions needing no top-up, two thin lessons topped up with synthetic ones — exercising the real P2.T2
    `generate()` as the actual data source). Result: **51 of 52 tests pass**;
    `test_expired_cursor_is_410` is deselected (see "Decisions" below) and is covered directly by
    `test_changes.py`'s `CursorExpiredError` tests instead.
  - **`tests/integration/test_docker_stages.py`** (needs Docker, ran locally): builds `--target runtime` and
    `--target boost-stub` for real and checks (a) `runtime` contains no `boost_stub` files
    (`find / -iname '*boost_stub*'`), (b) `runtime` still has `boost_bridge` importable, (c) the `boost-stub`
    image actually starts and serves `/openapi.json`. All three passed.
  - `uv run lint-imports --config pyproject.toml` → 1 contract kept, 0 broken.
  - Full suite: `uv run pytest -q` → 333 passed, 52 skipped (contract suite, no base URL) / 385.
    `uv run ruff check .` → all checks passed; `uv run ruff format --check .` → 114 files already formatted;
    `uv run mypy src scripts` → no issues in 57 files; `uv run mypy --strict src/boost_stub
    tests/unit/boost_stub` → no issues in 27 files.
  - **Bugs found and fixed while building this** (none shipped):
    - a route-ordering bug: `/questions/{question_id}` was registered before the new `/questions/revisions`,
      so FastAPI matched the batch path as `question_id="revisions"` and 404'd it — caught immediately by the
      live acceptance test, fixed by moving the literal path first (now documented in `CLAUDE.md`);
    - `topics`'s `module_id` parameter had no `Query(alias="moduleId")`, so the real query name was rejected
      as 422 "missing" — same root cause class as the route-ordering bug (FastAPI/Boost naming mismatch), same
      test caught it;
    - the fake-Boost fixture initially ignored the `locale` query param on single-item endpoints, which looked
      like a stub bug (`test_batch_honours_locale[en-GB]` failing) until traced to the fixture;
    - the `boost-stub` Docker image crashed on startup: its SQLite path default resolves under `/app`, which is
      root-owned at that point in the build (`WORKDIR` runs before `USER app`) — fixed with an explicit
      `mkdir`+`chown` of a `/app/data` directory, caught only by actually running the built image;
    - `tests/integration/test_docker_stages.py` itself crashed capturing `docker build`'s output on Windows
      (`UnicodeDecodeError`, cp1252 can't decode buildkit's box-drawing characters) — fixed with
      `encoding="utf-8", errors="replace"`;
    - **a real bug in `transforms.html_to_blocks`**, caught by its own unit test, not the integration test: each
      `<li>` flushed as its own block, so a 2-item list became two separate text blocks instead of one list
      block. Fixed (list items now accumulate within one block, separated by newlines, flushing only when the
      list itself ends).
- **Decisions taken where the plan is silent (please confirm or correct):**
  1. **Token scope is enforced by probing Boost, never by the stub's own judgement.** The plan says the stub
     "forwards the caller's bearer token to Boost unchanged, so token scopes stay real" — true for an endpoint
     the stub already proxies per request, but several §13 endpoints (the change feed, `question-templates`,
     `topics`, an all-synthetic batch) never call Boost at all. Without a probe, nothing would check those
     tokens. The probe is cached 30 s per token to bound the extra Boost load.
  2. **The stub's own poll needs its own credential** (`STUB_POLL_TOKEN`), distinct from a caller's forwarded
     token, since the background poll isn't triggered by any one request.
  3. **The §13 batch endpoints and the single-question-revision endpoint get `Cache-Control: … immutable`**
     (matches §13.5's list, which names "3, 4, 5, and the existing single question revision"); the **grading**
     batch does not (§13.5 does not list it — grading content is sensitive and not meant for public caching).
  4. **The in-memory LRU of immutable revisions (tracker item) is deliberately not built.** Revisions are
     immutable, so an uncached repeat fetch from the stub is correct, just not free; the BFF's Redis cache and
     the engine's in-memory snapshot are what actually sit on the learner's hot path, not the stub. Building a
     second cache here felt like speculative work the plan didn't ask for. Flagged for reconsideration once the
     stub is under real load in staging.
  5. **`test_expired_cursor_is_410` is deselected from the live acceptance run**, not weakened or deleted: a
     single short-lived test server can't produce "cursor 0 is still valid" and "some cursor is expired"
     simultaneously without an operator-aged server (exactly the real-world reason `CONTRACT_EXPIRED_CURSOR` is
     an externally-supplied env var in the first place, per the P2.T1 entry). The behaviour itself is unit-tested
     directly against `ChangeTracker`.
- **Issues found / open risks:**
  - `stub-data/templates.json`/`synthetic.json` do not exist yet (P2.T2's live run is pending P0.T3), so the
    stub currently has nothing to serve for `question-templates`/`topics` in a real deployment. Code and tests
    are unaffected (they supply their own fixture data).
  - Grading's per-locale fan-out doubles Boost calls for every real grading batch; acceptable for a stub, worth
    watching if Boost rate-limits aggressively.
  - Boost's exact single-question grading response shape (plain string explanation vs. something richer) is
    still inferred, same caveat as `boost_bridge`'s own Boost models.
- **Ready to continue:** NO, blocked on the owner. P0.T3 (Boost delivery + grading tokens) unblocks: P2.T1's
  acceptance run against real Boost, P2.T2's live run (and committing `stub-data/`), and P2.T4 (deploying the
  stub to staging, which also needs P0.T3 per its own `Dep`). P3 (the engine) needs P0.T2 and P0.T4 too.
- **Next task:** P2.T4 (Repo: BFF/EXT) once P2.T3 is deployable — it is EXT work (Dokploy), so largely yours;
  otherwise, with the tokens: P2.T1/P2.T2 acceptance runs.


### 2026-11-02 · Token attempt · The supplied `bst_...` token is not a delivery service token

- **Status:** BLOCKED (external) — P0.T3 is still open
- **What happened:** the owner supplied a `bst_...`-prefixed value as "the delivery
  token" (redacted here — never commit secrets). `scripts/generate_stub_templates.py`'s own docstring already warns "never a `bst_` token, which
  cannot call delivery routes" — running it against real Boost (`BOOST_BASE_URL=https://boost-api.fordona.io`)
  confirmed this immediately: `GET /v1/delivery/modules` → `401 {"code":"authentication_required","detail":
  "Sign in to continue."}`. This looks like a personal/browser-session token, not a service credential. No
  data was read or written; nothing was committed.
- **Ready to continue:** NO. P2.T1's and P2.T2's acceptance runs still need a real delivery token (service
  credential, not `bst_`), and P2.T1 additionally needs a grading token.
- **Next task:** re-request P0.T3 from the Boost owner, specifically a **service** token.

### 2026-11-02 · P3.T1 · Package skeleton and conventions

- **Status:** DONE
- **Repo / branch / commit:** ENG · feat/theory-app-implementations · 1ec80622
- **Owner instruction recorded:** "continue with the implementations until I acquire them [the tokens]"
  (2026-11-02). P3.T1's tracker dependency is P0, which is still open (P0.T2–T4 are owner/EXT tasks) — started
  anyway because nothing in this task's actual content needs a token, a sign-off, or Postgres hardening; it's
  pure code. Same pattern as P1.T1/P2.T1/P2.T2/P2.T3 before it.
- **A real naming collision found and resolved before writing any code:** the tracker's exact list of new
  error codes (Plan §7.3) reuses two string values that `ErrorCode.Learn` — the **existing**, still-live
  Directus-backed quiz/theory feature (`learn/content`, `learn/exam`, `learn/hub`) — already owns:
  `THEORY_MODULE_LOCKED` and `THEORY_LESSON_NOT_FOUND`. Confirmed in both `ErrorCode.java` and
  `messages.properties`/`messages_sv.properties`, where those exact keys already have different English/Swedish
  copy for the old feature. Plan §0 ("What changed") confirms the new learn.theory feature supersedes the old
  one in product terms, but no task in the tracker retires `ErrorCode.Learn` or the old module, so both error
  codes would otherwise collide for real, live endpoints — the one thing `errorCode` is documented as being
  for (machine-readable, client-branchable) would silently mean two different things, and the second bundle
  entry would clobber the first's translation.
  - **Asked the owner how to resolve it** rather than guessing silently (AskUserQuestion): rename the new
    codes, or retire/rename the old ones. **Decision: rename the new ones** — `ErrorCode.Learn` and the old
    feature are untouched. Of the ten new `ErrorCode.Theory.*` constants, only the two that actually collide
    are renamed off the plan's literal string (`MODULE_LOCKED` → `THEORY_ATTEMPT_MODULE_LOCKED`,
    `LESSON_NOT_FOUND` → `THEORY_ATTEMPT_LESSON_NOT_FOUND`); the other eight (`LESSON_LOCKED`,
    `ATTEMPT_NOT_FOUND`, `ITEM_NOT_FOUND`, `REQUEST_ID_CONFLICT`, `RESPONSE_CONFLICT`, `PHASE_CLOSED`,
    `PHASE_INCOMPLETE`, `OPTION_INVALID`) match Plan §7.3 verbatim, since they don't collide with anything.
    Documented with a Javadoc on `ErrorCode.Theory` pointing back here.
- **What was done:**
  - `io.fordona.engine.learn.theory` package created with its `exception/{business,resource,validation}`
    subpackages populated now; `api/{dto,request}`, `data/*`, `model`, `service`, `content`, `similarity`,
    `usecase` are deliberately **not** pre-created empty — they materialise with their first real class in
    P3.T3+ (P3.T3 already added `client/` and `config/`), matching how every other module in this codebase
    grew. No placeholder/empty packages were committed.
  - `ErrorCode.Theory` (10 constants) added to `common/constants/ErrorCode.java`.
  - Ten exception classes, one per code, following the existing single-cause-per-class convention (not the
    `Reason`-enum idiom — that fits a single HTTP status with many causes, e.g. `UserNotPermittedException`;
    these ten span four different statuses with no need to share one class):
    - 403: `TheoryModuleLockedException`, `TheoryLessonLockedException` (`BusinessException`)
    - 409: `TheoryRequestIdConflictException`, `TheoryResponseConflictException`, `TheoryPhaseClosedException`,
      `TheoryPhaseIncompleteException` (`BusinessException`, explicit `HttpStatus.CONFLICT`)
    - 404: `TheoryLessonNotFoundException`, `TheoryAttemptNotFoundException`, `TheoryItemNotFoundException`
      (`ResourceException`) — `TheoryAttemptNotFoundException`'s Javadoc records the plan's explicit rule that
      another learner's attempt is a 404, never a 403, so a wrong-owner read can't be used to confirm an id
      exists.
    - 422: `TheoryOptionInvalidException` (`ValidationException`)
  - i18n: all ten keys added to **both** `messages.properties` and `messages_sv.properties`, grouped together
    with a comment pointing at `ErrorCode.Theory`'s Javadoc so a future reader isn't confused by the two THEORY_
    key groups sitting next to each other.
  - No new i18n test was needed — the repo already has a generic `ErrorCodeMessageCoverageTest` that reflects
    over every `ErrorCode.*` nested class and fails if a constant is missing from either bundle, or if the two
    bundles' key sets diverge. It already covers `ErrorCode.Theory` for free; this satisfies the tracker's
    "an i18n test that every `ErrorCode.Theory.*` constant has a key in both bundles" item without a new test.
- **Tests:**
  - `./gradlew compileJava` → clean.
  - `./gradlew test --tests io.fordona.engine.common.constants.ErrorCodeMessageCoverageTest` → 4/4 passed
    (confirms all ten new keys are present and matched in both bundles).
- **Deviations from the plan:** the two renamed error-code string values (above); everything else matches
  Plan §7.3 verbatim.
- **Issues found / open risks:** none new.
- **Ready to continue:** YES.
- **Next task:** P3.T2.

### 2026-11-02 · P3.T2 · Flyway migrations: content read model

- **Status:** DONE
- **Repo / branch / commit:** ENG · feat/theory-app-implementations · 1ec80622
- **What was done:**
  - `V1_0_16__theory_content_read_model.sql` (`db/migration/learn/`): `content_release`, `content_unit`,
    `content_lesson`, `content_question`, `content_template`, `content_template_question`,
    `content_question_revision`, `question_neighbour` — exactly Plan §6's tables, no `lesson_attempt`/
    `attempt_item`/`retry_policy` (those are `V1_0_17`/`V1_0_18`, P4.T1, per the tracker's own split).
  - `CHECK` constraints on every actual **status** column (`content_release.source`, `content_unit.status`,
    `content_lesson.status`, `content_template.status`, `content_question.status`,
    `content_question_revision.level`, plus a sanity range check on `difficulty` 1–5 and `question_neighbour.rank`
    1–20) — not on `type`/`domain_code`/`topic_tag`, which are open vocabularies Boost/config controls, not a
    fixed state machine, matching CLAUDE.md's "CHECK constraints on every status column" distinction.
  - Indexes on every foreign-key-shaped column used for lookup (`content_lesson.unit_id`,
    `content_question.{home_lesson_id,unit_id}`, `content_template.lesson_id`,
    `content_template_question.question_id`, and `release_id` on both revision/neighbour tables).
  - **One inferred default, flagged rather than silently assumed:** Plan §6's ER diagram gives explicit
    status values for lesson/template/question (`VISIBLE`/`HIDDEN`/`ACTIVE`/`EXCLUDED`) but **not** for
    `content_unit.status` — no value list, no prose elsewhere mentions a unit being individually
    hidden/excluded (only unit-level *locking* exists, which is an entitlement concern, not a status). Assumed
    `VISIBLE`/`HIDDEN` for consistency with lesson/template; recorded here rather than guessed invisibly. If
    this is wrong, it's a one-column `CHECK` constraint to fix, nothing downstream depends on a specific value
    yet.
  - **`level` is stored uppercase** (`EASY`/`MEDIUM`/`HARD`) though Plan §4.1's prose example is lowercase
    (`1–2 easy, 3 medium, 4–5 hard`) — this is an engine-computed, engine-owned value (derived from
    `difficulty` by `difficulty_level_map`, not read verbatim from Boost), so it follows this schema's own
    enum-casing convention (`VISIBLE`/`ACTIVE`/etc.), not the plan's prose casing.
- **Tests:**
  - `./gradlew test --tests io.fordona.engine.FordonaEngineApplicationTests` → green. This is the engine's
    existing Spring-context-load test, which runs every Flyway migration (`V1_0_16` included) against a real
    Postgres via Testcontainers — Docker is available again this session (unlike the P0.T1 baseline), so this
    is a genuine, not a skipped, check. A dedicated migration-only test wasn't added; the tracker's acceptance
    line ("the engine starts on a clean database; Flyway validates; a Testcontainers migration test passes")
    is met by this existing test, and a second one would just re-assert the same fact.
- **Deviations from the plan:** the `content_unit.status` value-set inference above.
- **Issues found / open risks:** none new.
- **Ready to continue:** YES.
- **Next task:** P3.T3.

### 2026-11-02 · P3.T3 · Boost client (engine side)

- **Status:** DONE
- **Repo / branch / commit:** ENG · feat/theory-app-implementations · 38719168
- **What was done:**
  - `learn/theory/client/BoostContentClient.java`: a `RestClient`-based client over Plan §13 —
    `changes(after, limit)`; `modules`/`lessons`/`questions`/`questionTemplates` (all four accept the
    multi-value `id=` filter); `questionRevisionsBatch`/`gradingRevisionsBatch` (chunk the caller's refs into
    groups of 100 and merge `items`/`missing` transparently); `topics(moduleId)`.
  - **Scoping decision beyond the tracker's literal method list:** the tracker names `changes`, "lists by
    `id=` filter", the two batches, and `topics` — it doesn't explicitly name a question-**templates** method,
    but P3.T2's own schema has `content_template`/`content_template_question`, which the sync service (P3.T4)
    has no other way to populate. Read "lists by `id=` filter" as covering all four of Boost's list resources
    (modules, lessons, questions, question-templates — Plan §13.2's own endpoint table lists templates as
    endpoint #2 alongside the "existing lists" row), and added `questionTemplates(...)`. Did **not** add a
    single question-template-revision fetch (Plan §13.2 #3) — the list endpoint already returns each
    template's current `version` inline, the same convention lessons/questions use, so nothing in the sync
    path needs the dedicated revision endpoint; it mainly serves the BFF's own cacheable single-item reads.
  - **Response models carry structure only, by construction.** `BoostQuestion`/`BoostLesson` have no Java
    field for `translation.{prompt,options,title,contentHtml}` text at all — matching Plan §1 decision 3 ("the
    engine never sends text") at the type level, not just by convention: there's no field for question/lesson
    text to land in even by accident. Field names (`shared.moduleId`, `shared.lessonId`, `shared.subjectId`,
    `shared.difficulty`, `shared.mediaId`, `shared.estimatedReadMinutes`) are taken from
    `boost_bridge/clients/boost/models.py`'s own Javadoc-equivalent sourcing (Boost's API docs +
    cross-checked CMS field names) — the one place in either repo that has actually verified these against
    Boost, rather than re-guessing them. **`topicKey` and a template's `shared.sort`/question `sort` have no
    verified source yet** (they're new, §13-only fields) — taken directly from Plan §13.4's own JSON examples,
    since Fordona defines §13 itself.
  - **A real modeling gap caught before it became a bug:** Plan §6's `content_unit.title`/`content_lesson.title`
    columns are `jsonb "locale to text"` — a **multi-locale map** — but Boost's `translation.title` convention
    (confirmed in `boost_bridge`'s own models) is a **single string for the requested locale only** (one
    locale per request, like every other Boost endpoint). Assembling the jsonb map therefore needs **one
    client call per supported locale**, the same per-locale fan-out the Boost stub's own grading route already
    uses. `BoostContentClient`'s list methods take a single `locale` parameter on purpose and do **not** try
    to assemble the map themselves — that composition is P3.T4's job (the sync service), which is exactly
    where the stub's own grading precedent lives. Flagging this now so whoever builds P3.T4 doesn't have to
    rediscover it.
  - **No defaults for the tokens** (tracker requirement): `theory.boost.delivery-token` /
    `grading-token` bind from `${THEORY_BOOST_DELIVERY_TOKEN}` / `${THEORY_BOOST_GRADING_TOKEN}` with no
    fallback in `application.yml` — Spring fails fast at startup if either is unset, same convention as
    `mollie.*`. Added matching test-only dummy values to `application-test.yml` (not `application.yml`) so the
    existing test suite's Spring context still boots.
  - **A second, dedicated `RestClient` bean** (`boostRestClient`), not the shared `restClient` bean Mollie
    uses — Boost's own connect/read timeouts (`theory.boost.connect-timeout-ms`/`read-timeout-ms`, default
    2000/3000) must never change Mollie's. Verified the two beans don't collide: `MollieApiClient`'s
    constructor parameter is literally named `restClient`, which Spring resolves by name among the two
    same-typed beans; the context-load test (`FordonaEngineApplicationTests`) passing confirms this.
  - **Prod guard** (tracker requirement, Plan §4.5): every response is checked for the `X-Boost-Stub` header;
    if present while the `prod` Spring profile is active, the call throws `IllegalStateException` immediately
    (logged at ERROR first) rather than silently serving stub data in production. Implemented as a first-call
    check (every real call passes through the same response-handling path), not a separate startup probe —
    the tracker allows either.
  - **410 `CURSOR_EXPIRED` → a dedicated `BoostCursorExpiredException`**, distinct from the generic
    `BoostIntegrationException` used for every other failure (unreachable, 5xx, unexpected shape) — so the
    P3.T4 sync service can tell "run a full resync" apart from "Boost is down" by catching a specific type,
    not by string-matching an error code. Both log Boost's own `requestId` (parsed from the `{status, code,
    detail, requestId, errors}` envelope) alongside the engine's own `correlationId`, for support
    correlation — genuinely new diagnostic detail, not a duplicate of `GlobalExceptionHandler`'s own logging
    (java-code-standards' explicit carve-out), since these calls mostly happen from a background job, not a
    controller. **Never logs tokens**: the existing shared `RestClientLoggingInterceptor` (reused on the new
    bean) never logs request headers at all, only the sanitized URL and body — Authorization is never on
    either.
  - New `ErrorCode.Integration.BOOST_UNAVAILABLE`/`BOOST_CURSOR_EXPIRED` (not `CONTENT_UNAVAILABLE`, which the
    old Directus client already owns — same collision-avoidance reasoning as P3.T1), with keys in both i18n
    bundles.
- **Tests:**
  - New `BoostContentClientTest` (`MockRestServiceServer`, per the tracker's own suggestion) — 8 tests: change-feed
    parsing; the 410 → `BoostCursorExpiredException` mapping; a generic 500 → `BoostIntegrationException`
    mapping; `topics` parsing; batch chunking (150 refs → two requests of 100 + 50, merged `items`/`missing`
    back into one result); grading-batch answer-key + per-locale explanation parsing; both sides of the
    prod/stub guard (throws under `prod`, does not throw otherwise) via `MockEnvironment`.
  - `./gradlew test --tests io.fordona.engine.learn.theory.client.BoostContentClientTest` → 8/8 passed.
  - Full suite: `./gradlew test` → **1381 passed, 31 skipped, 0 failures, 0 errors** (Docker available this
    session, so the Testcontainers-backed classes ran for real, not skipped as in the P0.T1 baseline).
    `./gradlew compileJava` → clean.
- **Deviations from the plan:** none beyond the modeling/scoping decisions above, all flagged.
- **Issues found / open risks:**
  - `topicKey` and template `sort` field names are taken from Plan §13.4's own examples, not from a captured
    real payload (today's Boost doesn't have them yet) — same "will be the first real check" caveat P2.T2's
    entry already carries for `shared.lessonId`/`shared.difficulty`/etc.
  - The per-locale title/theory-content composition this client's design assumes is **not yet built** — it's
    P3.T4's job, flagged above so it isn't rediscovered from scratch.
- **Ready to continue:** YES for P3.T1–P3.T3 (all code-complete, no token needed, nothing here blocks on
  P0). **P3.T4 onward still needs real Boost data to verify against** (the stub's fixture data, or real Boost
  once the correct delivery token arrives) for a genuine Testcontainers-backed sync test, though its own unit
  tests (validation rules, level mapping, etc.) don't need either.
- **Next task:** P3.T4 (content validation and sync service) — the next task whose dependencies (P3.T2,
  P3.T3) are now both ticked.


### 2026-11-02 · P0.T3 (partial) · Real Boost tokens received — production, no staging yet

- **Status:** PARTIAL — the credentials half of P0.T3 is resolved; the rest (Kinde audience, internal
  token, a delivery date agreement) is still open.
- **What happened:** the Boost owner sent a grading token and a "service" token, explicitly stating these
  are the **production** credentials and that Boost has no staging environment yet ("let me fix that now").
  Both tokens were verified read-only before any further use (never committed): the service token
  authenticates on `/v1/delivery/modules` (200) and is correctly refused on a grading route (401); the
  grading token authenticates correctly on a reserved probe id (404, same convention the Boost stub's own
  `auth.py` uses). Scope separation holds.
- **Decision recorded (2026-11-02, owner):** use these two prod tokens for the bounded P2.T1/P2.T2
  acceptance runs now, swap to real staging credentials once the owner's staging environment exists. **Not**
  wired into any continuously-running dev/staging service config — this was a one-off, explicit scope
  agreed with the owner, not a standing arrangement.
- **Open naming question, not yet resolved:** P0.T3 asks for three credentials — a delivery token for the
  BFF, and a delivery token **and** a grading token for the engine. The owner sent two: a grading token and
  one "service token". Assumed (not confirmed) that the one service token covers delivery-scope reads for
  both the BFF and the engine — reasonable, but worth a one-line confirmation from the owner rather than
  leaving it implicit.
- **Ready to continue:** the credentials are usable for read-only verification and the two acceptance runs
  below; P0.T3's remaining items (Kinde audience, internal token, O-1 delivery date) are still open.

### 2026-11-02 · P2.T1 (acceptance) · Contract suite run against real Boost with real tokens

- **Status:** DONE — acceptance criterion fully met.
- **What was done:** ran `tests/contract/boost_content_v1` against `https://boost-api.fordona.io` with the
  real service token (as `CONTRACT_DELIVERY_TOKEN`) and the real grading token (as `CONTRACT_GRADING_TOKEN`).
  `CONTRACT_EXPIRED_CURSOR` left unset (no way to get one from real Boost yet) — that one test fails with
  its own instructions, as designed.
- **Result:** 50 failed, 2 passed, 0 errors. Confirms the prediction recorded in the earlier (placeholder-token)
  P2.T1 entry exactly: with real tokens, failures are genuine **404s** ("Published content not found." /
  route not found) on every §13-only endpoint — not blanket 401s — proving Boost's existing auth works and
  §13 itself simply doesn't exist there yet. One failure came back as a bare `401 authentication_required`
  on the new grading batch route (`/v1/grading/questions/revisions`) rather than a 404 — consistent with an
  unmatched route falling through to a generic auth wall rather than Boost's normal "not found" handler, not
  a credential problem (the same grading token works correctly elsewhere in the run). The 2 passes are the
  pre-existing token-scope tests (a token rejected on the wrong endpoint is the expected result).
- **This closes the "does not yet prove the assertions are meaningful" caveat** from the placeholder-token
  run: the suite now demonstrably tells a real auth failure apart from a real "endpoint doesn't exist yet"
  failure.
- **Ready to continue:** YES for P2.T1 itself. Boost implementing §13 for real (P9.T1, external) is what
  turns these 404s into passes — nothing further for us to do here until then.
- **Next task:** P2.T2's own acceptance (below), already unblocked by the same tokens.

### 2026-11-02 · P2.T2 (acceptance) · Live generator run — Boost has zero published content

- **Status:** DONE, with a significant finding — the generated files are genuinely, correctly empty.
- **What was done:** ran `scripts/generate_stub_templates.py` against real Boost with the real service
  token. `GET /v1/delivery/modules` (and, checked directly afterward, `/lessons` and `/questions` too) all
  return `{"items": [], "total": 0}`. The generator produced `templates.json`/`synthetic.json` with empty
  arrays, `generation 1 (changed)`, and a warning that no block type could be demonstrated (no lesson existed
  to need a top-up). **Confirmed this is not a tooling bug**: re-ran the generator a second time and diffed
  byte-for-byte against the first run — identical, satisfying the determinism acceptance check even though
  the content is empty.
- **Interpretation:** Boost has nothing published yet — either nothing authored, or everything still in
  draft (§13.1: drafts are invisible to delivery endpoints regardless of token). This is `P9.T2`'s remit
  ("Eric's content in Boost"), not something we can act on from either repo.
- **Practical consequence for P2.T3/P2.T4:** the Boost stub, once deployed, currently has **nothing to
  serve** for `question-templates`/`topics` — not real content, and no synthetic `[DEMO]` content either
  (the top-up is per-lesson, and there are zero lessons). This was already a known risk in the P2.T3 entry
  ("stub-data/templates.json/synthetic.json do not exist yet"); now they exist, and they're empty for a
  different, upstream reason than originally expected.
- **Decision recorded (2026-11-02, owner):** commit the empty files now rather than wait, to prove the
  generator pipeline works end-to-end against real Boost, with `stub-data/README.md` added documenting
  exactly why they're empty so a future reader doesn't mistake it for a bug. Re-run once Eric publishes
  anything.
- **Field-naming caveat still open, not resolved by this run:** `BoostContentClient`'s (engine, P3.T3)
  assumed field names (`shared.lessonId`, `shared.difficulty`, `topicKey`, a template's `shared.sort`, etc.)
  remain **unverified against a real payload** — there is still nothing in Boost to check them against. Same
  caveat `boost_bridge`'s own models carry. Revisit the moment any real content exists.
- **Tests:** `uv run python -m scripts.generate_stub_templates` (twice) → byte-identical
  `stub-data/templates.json`/`synthetic.json`; both `{"templates": []}` / `{"questions": []}` respectively.
- **Ready to continue:** YES, mechanically. **Blocked on real content** for this to mean anything in
  practice (P9.T2, external).
- **Next task:** P2.T4 (deploy the stub to staging — EXT/Dokploy, and now also waits on the Boost owner
  actually standing up a staging Boost tenant, per their own message today) or P3.T4 (engine: content
  validation and sync service), whichever the owner picks next.

### 2026-11-02 · P9.T2 (status note) · Boost owner + Eric aware, publishing to follow

- **Status:** note only, no code change.
- **What happened:** the owner had a call with the content author (Eric); both are aware the content
  sitting in Boost is still all Draft (confirmed via the Boost admin dashboard: 111 theory records, 712
  questions, 0 published anywhere). They're having their own call to review and publish. The owner's advice:
  keep completing the implementation on our side so there's no blocker once publishing happens.
- **Decision recorded (2026-11-02, owner):** continue down `BFF_IMPLEMENTATION_PROGRESS.md` in order. Next
  up per dependency order: P3.T4 (content validation and sync service, engine).
- **Ready to continue:** YES.
- **Next task:** P3.T4.

### 2026-11-02 · P3.T4 (part 1 of 2) · Content validation and derivation rules

- **Status:** PARTIAL — the pure validation/derivation logic is done and tested; the stateful half
  (data layer, `ContentSyncService`, Testcontainers acceptance test) is not started.
- **Repo / branch / commit:** ENG · feat/theory-app-implementations · f0441fac
- **What was done:**
  - `QuestionValidator`, `TemplateValidator`, `LessonValidator`, `DifficultyLevelMapper`,
    `HomeLessonResolver` — all pure functions, no I/O, no Spring context, in a new
    `learn/theory/content/` package.
  - `HomeLessonResolver` needed its own design, not just a lookup: a question's templates can span
    different lessons (even different units), and a template's own `sort` only orders it *within its
    lesson* — "first template by sort" (Plan §4.1) is only well-defined as a triple order (unit sort,
    then lesson sort, then template sort), which is the order a learner actually walks the unit path.
    Implemented and tested that ordering explicitly, including the "different units" case.
  - Two small, deliberately narrow additions to the already-committed P3.T3 Boost client models,
    each justified in its own Javadoc so a future reader doesn't mistake them for a reintroduction of
    question text:
    - `BoostLesson.Translation.hasContent()` — reads `contentHtml` only to answer "is there any
      theory at all" (Plan §4.4's lesson-visibility rule); there is no public accessor for the HTML
      itself — `Translation` is a hand-written class, not a record, specifically so no accessor method
      is auto-generated for it.
    - `BoostQuestion.Translation.optionKeys()`/`mediaKinds()` — reads only each option's `id` (needed
      to validate `correctOptionKey` is among them and to store `option_keys`) and each block's bare
      `type` discriminator (needed for `media_kinds`); no markdown, no asset id, no alt text is ever
      modelled.
  - **Decision recorded, not guessed:** `QuestionValidator`'s domain-code check takes a caller-supplied
    allowlist that defaults to empty, meaning "accept any non-blank value." Plan §4.1 says the domain
    code comes from "Boost's subject taxonomy (6 codes)," but those six codes are never actually listed
    anywhere in either repo, and — unlike `topicKey`, which Plan §13.2 #7 gives a real endpoint for
    (`GET /v1/delivery/topics`) — there is no Boost endpoint that enumerates the domain taxonomy.
    Hardcoding a guessed list of six values would silently exclude every question tagged with a real,
    unanticipated seventh code. **Open question for the Boost owner or Eric:** what are the actual six
    domain codes, so `theory.content.known-domain-codes` can be configured with them and this check
    tightened from "present" to "present and recognised."
- **Tests:** new unit tests for every validation rule (each exclusion reason individually), the
  difficulty→level table, home-lesson resolution (same lesson, different lessons same unit, different
  units, and the empty-memberships error case), and the two client-model derivations
  (`optionKeys`/`mediaKinds`/`hasContent`). `./gradlew test` → full suite still green (see commit for
  the exact count).
- **Deviations from the plan:** none beyond the domain-allowlist decision above.
- **Issues found / open risks:** the domain-code taxonomy question above.
- **Ready to continue:** YES. The remaining half of P3.T4 — the data layer for P3.T2's tables, the
  actual `ContentSyncService.sync(now, full)` orchestration (change feed, full resync, release
  creation, upsert), and its Testcontainers acceptance test — is real, substantial work on its own and
  was deliberately left as a separate, clean next slice rather than rushed in the same pass.
- **Next task:** P3.T4 (part 2): data layer + `ContentSyncService` + acceptance test.

### 2026-11-02 · P3.T4 (part 2 of 2) · Content sync service and its data layer

- **Status:** DONE — P3.T4 is now fully complete.
- **Repo / branch / commit:** ENG · feat/theory-app-implementations · ba16efdb
- **What was done:**
  - The full Spring Data JDBC layer for P3.T2's tables: entities, repositories (mostly
    `@Modifying @Query` upserts with real `ON CONFLICT`, since the primary keys are Boost's own
    string ids, not auto-generated), one MapStruct mapper, and a single `TheoryContentStore` —
    the content read model is one cohesive concept, not seven unrelated ones.
  - `ContentSyncService.sync(Instant now, boolean full)`: polls the change feed, re-lists Boost's
    structure, validates with P3.T4-part-1's rules, upserts, and creates a `content_release` only
    when something actually changed.
  - **A real bug caught before writing any Java, by research alone:** `V1_0_16`'s five JSON
    columns were `JSONB`, but this engine has **no Spring Data JDBC JSONB converter registered
    anywhere** — confirmed by an existing migration's own comment explaining why it deliberately
    used `TEXT` for the identical reason (nothing queries *into* the JSON, only reads it back
    whole). Fixed with a follow-up migration (`V1_0_16_1`) before any entity touched those columns,
    rather than editing the already-committed `V1_0_16`.
  - **A real ordering bug, caught by a failing test, not by review:** lesson rows must exist before
    any question or template can reference them (foreign keys), but a lesson's own VISIBLE/HIDDEN
    status can only be computed *after* its templates (which themselves depend on their questions)
    have been processed — the reverse of what the FK demands. Fixed with the same two-phase
    write pattern already used for templates: the structural fields land early via a dedicated
    `upsertStructure()` that never touches `status`; `status` is set once, later, via its own
    `updateStatus()`.
  - **A second bug in the first fix, caught by the test suite itself:** the first attempt at that
    two-phase write re-asserted a placeholder status on every sync, including re-syncs of
    completely unchanged data — which would have made the "did anything change" signal always
    report true, breaking the single acceptance check that matters most. Caught by writing the
    "second sync, identical data, no new release" test *before* trusting the fix, and watching it
    fail for exactly the reason described.
  - **Change detection is exact, not approximate**: every upsert's `ON CONFLICT ... DO UPDATE` is
    guarded with `IS DISTINCT FROM` against every column, and the repository methods return the
    real affected-row count (Postgres's own default is to report a row as "touched" on every
    conflict, identical values or not — that default would have made every sync look like a
    change). Template membership (a delete-then-reinsert, which `ON CONFLICT` can't express) is
    diffed explicitly in the store before touching the table at all.
  - **Deliberate scope decision** (not what Plan §4.3's diagram literally shows): the change feed
    is consulted only to decide *whether* to resync, not to scope *which* ids to refetch — any
    reported change triggers a full re-list of modules, lessons, templates and questions, rather
    than the batch-scoped incremental fetch the plan describes. At today's real content scale,
    confirmed against Boost's own admin dashboard (7 modules, 104 chapters, 712 questions), that's
    a handful of HTTP calls per sync, not a performance concern. This is real, deliberately
    deferred work for when the catalogue grows enough that the assumption stops holding — not
    forgotten, just not needed yet.
- **Tests:**
  - `TheoryContentStoreTest` (12 tests, real Postgres via Testcontainers): every store method
    round-trips correctly, including the JSON (de)serialization, the ordered template membership,
    the `HomeLessonResolver`-feeding membership query, and — the one that matters for the
    acceptance criterion — that an upsert called twice with identical data reports no change the
    second time.
  - `ContentSyncServiceTest` (3 tests, same real-Postgres base, `BoostContentClient` mocked with a
    small hand-built fixture mirroring the shape of the BFF repo's own stub fixtures): a full sync
    into an empty database creates a release and gets the HIDDEN-template → HIDDEN-lesson cascade
    right (not just isolated field writes); a second identical full sync creates no new release;
    an incremental sync against an empty change feed creates no release and still advances the
    cursor. This is the tracker's own P3.T4 acceptance test.
  - Full suite: `./gradlew test` → **1429 passed, 31 skipped, 0 failures, 0 errors**.
- **Deviations from the plan:** the change-feed scoping simplification above, logged for when
  content volume grows.
- **Issues found / open risks:** none new beyond what P3.T4 part 1 already flagged (the domain-code
  allowlist question).
- **Ready to continue:** YES.
- **Next task:** P3.T5 (sync jobs — `ExternalUseCase` + scheduler wiring this service into
  `JobRunner`) is the natural next step; P3.T6/T7/T8 are also now unblocked.

### 2026-11-02 · P3.T5 · Sync jobs (job module)

- **Status:** DONE
- **Repo / branch / commit:** ENG · feat/theory-app-implementations · 3b2e4845
- **What was done:**
  - `TheoryContentSyncExternalUseCase` (one method, `syncTheoryContent(Instant now, boolean full)`,
    returning `Payload<Integer>` — 1 if a release was created, 0 if nothing changed), implemented by
    `ContentSyncService` as a one-line proxy around its own `sync()`, per the ExternalUseCase
    delegation rule.
  - **Deviation from the tracker's literal wording, following the binding convention instead:** the
    tracker says "An ExternalUseCase in `learn/theory/usecase`." Checked how every existing
    cross-**tier** ExternalUseCase in this codebase is actually placed (e.g.
    `PaymentReconciliationExternalUseCase`) — all of them live in the top-level `io.fordona.engine.client`
    package, not in the callee module's own `usecase/` folder. A module's own local `usecase/`
    package is reserved for same-tier sibling calls within `learn.*` (e.g. `LearnSubscriptionUseCase`,
    called by `learn.chat`, `learn.content`, `learn.exam`, `learn.hub` — all tier 4 like
    `learn.subscription` itself). The job module (tier 6) calling `learn.theory` (tier 4) is a
    cross-tier call, the same shape as the payment example, so it went in `client/` to match. Nothing
    was placed in `learn/theory/usecase` for this task — it stays empty until a genuine same-tier
    sibling call needs it.
  - Two schedulers in `job/scheduler/`, both routed through the existing `JobRunner` (locking, the
    `job_run` audit row, Micrometer timers, error isolation — no new machinery needed):
    - `theory-content-sync`, every 30 s, `full=false`;
    - `theory-content-full-resync`, nightly at 03:00, `full=true` (Plan §4.3, R-12) — the same path
      `ContentSyncService` already takes on `CURSOR_EXPIRED`, just scheduled rather than reactive.
  - `fordona.jobs.configs.{theory-content-sync,theory-content-full-resync}` in `application.yml`,
    each with its own `enabled` flag and `cron`, both overridable by env var, matching every other
    job's convention exactly.
- **Tests:**
  - Per scheduler: the delegation (`runNow()` calls the use case with the right `full` value and
    returns its response) and the tick method (`jobRunner.run(name(), this::runNow)` is actually what
    gets called).
  - The `@ConditionalOnProperty` gating, for both the global `fordona.jobs.enabled` switch and each
    job's own flag — three cases each (both enabled → bean present; jobs globally disabled → absent;
    this job individually disabled → absent). **Worth flagging the technique, since it's easy to get
    wrong silently:** a hand-written `@Bean` factory method that does `return new
    TheoryContentSyncScheduler(...)` would have compiled and *looked* like it tested the condition,
    while actually bypassing it entirely — Spring only evaluates `@ConditionalOnProperty` on a
    `@Component` class when something routes through its own conditional registration path. Used
    `@Import(TheoryContentSyncScheduler.class)` instead, which does go through that path. No existing
    test in this codebase tried this before, so there was no precedent to copy — worth the Javadoc
    note left on the pattern for the next person who needs it.
  - **Not written, and not standard for any job in this codebase today:** a live Testcontainers
    assertion that `job_run` actually gets a row, or a ShedLock concurrency test proving two instances
    can't both run the job. Checked — zero existing schedulers in this repo have either kind of test;
    that machinery is `JobRunner`'s own responsibility and is exercised generically by its existing
    tests, not re-verified per scheduler. Followed the same scope boundary rather than introducing a
    new, heavier standard unilaterally.
  - Full suite: `./gradlew test` → **1439 passed, 31 skipped, 0 failures, 0 errors**.
- **Deviations from the plan:** the `client/` vs. `learn/theory/usecase` placement above.
- **Issues found / open risks:** none new.
- **Ready to continue:** YES.
- **Next task:** P3.T6 (in-memory content snapshot) or P3.T7 (neighbour builder) — both now unblocked;
  P3.T8 (platform endpoints) needs P3.T5 (done) and P3.T7.

### 2026-11-02 · P3.T6 · In-memory content snapshot

- **Status:** DONE
- **Repo / branch / commit:** ENG · feat/theory-app-implementations · 49c99911 (test-infra fix),
  56ee0de3 (feature)
- **What was done:**
  - `ContentSnapshot`: an immutable, in-memory object per instance, holding every unit/lesson/template
    in order, every `ACTIVE` question with its current revision (tags, level, keys, option keys,
    explanation), and neighbour lists. `HIDDEN`/`EXCLUDED` rows are simply absent — exactly what
    "never chosen for an attempt" requires.
  - `ContentSnapshotProvider.get()`: single-flight, lock-free. A compare-and-set race on a
    last-checked timestamp means at most one `get()` call per 30 s window actually queries
    `max(release_id)` (and, only if it changed, rebuilds); every other concurrent caller in that
    window returns whatever is already cached, without waiting on anything. No background thread, no
    ShedLock — every instance refreshes itself, which is the whole point (Plan §9.2).
  - **A design choice worth flagging:** the `AtomicReference` starts at `ContentSnapshot.empty()`,
    never `null`. Today's real Boost has zero published content (still true as of this entry), so
    "no release exists yet" is not a hypothetical edge case here — it's the actual current state —
    and every caller downstream gets a valid, iterable, empty structure instead of a null check they'd
    all have to remember to write.
  - Two fields the tracker itself already called out as arriving later stay genuinely deferred: the
    retry policy isn't modelled at all yet (P4.T1's `retry_policy` table doesn't exist); neighbour
    lists **are** wired to `question_neighbour` now (a real column-for-column read path), just empty
    until `NeighbourBuilder` (P3.T7) starts writing to it — so the snapshot's public shape won't need
    to change when P3.T7 lands, only start returning real data.
  - `PinnedRevisionLoader`: a `@Cacheable`-backed loader for a revision that is no longer current (an
    attempt pinned to it before a republish) — immutable, so no expiry, only a bounded Caffeine size.
    Its own `@Component`, not a method on the provider, for the same reason `PermissionCatalog` is its
    own bean elsewhere in this codebase: a self-invoked `@Cacheable` method bypasses the Spring proxy
    that applies the annotation and silently never caches anything.
  - New bulk-read queries backing the snapshot build, each a single query with no per-row follow-up:
    `findAllVisibleLessons`/`findAllVisibleTemplates` (status-filtered), a joined
    `findAllActiveQuestionsWithCurrentRevision` (one row per question, its *current* revision only —
    not every revision it's ever had), and `findAllNeighboursByQuestionId`.
  - **A real, reproducible regression found and fixed, separate from the feature itself:** running the
    full suite after adding these tests started failing two completely unrelated tests
    (`BookingAvailabilityTimeOffTest`, `PerStaffBookingAvailabilityTest`) with "sorry, too many clients
    already" from Postgres. Root cause: Spring's test-context cache keeps every *distinct* context
    alive for reuse (each with its own connection pool), and a differently-mocked bean earns its own
    context; enough of those accumulate over a full run to exceed Postgres's own default
    `max_connections` (100). The failure surfaces on whichever *unrelated* test happens to need a
    connection once the ceiling is hit — which is exactly why it looked disconnected from this task at
    first. Confirmed reproducible across two full runs (same two classes, both passing standalone)
    before concluding it was a connection-limit issue rather than flakiness. Fixed by raising the
    shared test container's own `max_connections`; no production config touched.
- **Tests:**
  - `ContentSnapshotTest`: ordering (units/lessons/templates by sort, independent of input order),
    indexing (by id), and that an unknown parent returns empty rather than null.
  - `ContentSnapshotProviderTest`: the freshness gate (no store query inside the 30 s window); no
    rebuild when the release is unchanged after the window elapses; a rebuild when it has; 20
    concurrent threads past the window resulting in exactly one store query (single-flight) — all via
    a controllable test `Clock`, not real sleeps.
  - `ContentSnapshotProviderAcceptanceTest` (real Postgres): **the tracker's own P3.T6 acceptance
    check** — two independent `ContentSnapshotProvider` instances, sharing only the real database,
    both pick up a newly-created release within the 30 s window. Two plain instances rather than two
    full Spring contexts, since the provider holds no static or shared in-process state for a second
    context to prove anything about that two instances sharing a database don't already.
  - `PinnedRevisionLoaderTest` (real Spring context, `@MockitoSpyBean`): confirms the cache actually
    hits — a mocked store in a plain unit test would never touch the real proxy `@Cacheable` needs to
    do anything at all, so it would pass identically whether caching worked or not.
  - Extended `TheoryContentStoreTest` with the new bulk-read methods, specifically proving the status
    filtering (a `HIDDEN` lesson/template is absent from the "all visible" lists) and the join (the
    *current* revision is the one returned, not an older one still sitting in the table).
  - Full suite: `./gradlew test` → **1456 passed, 31 skipped, 0 failures, 0 errors**.
- **Deviations from the plan:** none beyond the two deliberately-deferred fields, already anticipated
  by the tracker itself.
- **Issues found / open risks:** the test-infrastructure connection-limit issue above — fixed, but
  worth knowing it exists as the suite keeps growing; the fix (a higher ceiling on the shared test
  container) buys headroom rather than removing the underlying cause (accumulating distinct Spring
  test contexts), so it could resurface again much further down the line.
- **Ready to continue:** YES.
- **Next task:** P3.T7 (neighbour builder) — the snapshot's neighbour-list read path is already built
  and tested; P3.T7 only needs to populate `question_neighbour`. P3.T8 (platform endpoints) still
  needs P3.T7 too.

### 2026-11-02 · P3.T7 · Neighbour builder (metadata strategy)

- **Status:** DONE
- **Repo / branch / commit:** ENG · feat/theory-app-implementations · 38d1439d
- **What was done:**
  - `NeighbourRanker` (pure): for one seed question, every other ACTIVE question in the whole bank is
    scored into one of Plan §8's five groups — mutually exclusive, not summed: a candidate matching
    both "same lesson, same topic" (1.0) and "same unit, same topic" (0.8) counts once, at 1.0. Within
    the resulting list: score descending, then closest difficulty, then `questionId` — fully
    deterministic. Top 20 kept.
  - `NeighbourBuilder`: runs the ranker over the whole bank and replaces `question_neighbour`
    wholesale (delete-all, bulk insert) — correct here, not a shortcut, since the whole table is
    recomputed fresh from the current bank every time; there's no per-row "did this one change" to
    preserve the way template membership has. Wired directly into `ContentSyncService`, called right
    after a release is created and its revisions inserted — matching Plan §8's own flowchart, which
    has the release trigger this immediately rather than on a separate schedule.
  - `SimilarQuestionProvider` (the documented port) and `MetadataSimilarQuestionProvider` (the only
    implementation), reading straight off `ContentSnapshot.neighboursOf(...)` — no query, no
    computation at request time, matching the P3.T6 snapshot's whole design.
  - **`theory.similarity.source` genuinely gates the bean**, not just in name: setting it to anything
    other than `metadata` (including the plan's own documented future value, `vector`) removes
    `MetadataSimilarQuestionProvider` via `@ConditionalOnProperty`, and since no
    `VectorSimilarQuestionProvider` exists, that fails application startup loudly. Considered adding
    the property as a documented-but-inert placeholder (closer to the tracker's literal phrasing) and
    rejected it: a switch that silently does nothing when flipped is worse than not having the switch
    at all. This way, a misconfiguration surfaces immediately as a missing-bean startup error instead
    of a silent no-op.
  - **Two bugs found while writing the integration tests, both in the tests themselves — confirmed
    by fixing each and watching the real logic hold, not by weakening the test:**
    - a copy-pasted unrelated `id()` call stood in for a unit id that was supposed to come from a
      helper method's return value, causing a foreign-key violation unrelated to anything being
      tested;
    - an assertion assumed "no longer a neighbour of anyone" would show up as an empty list; it
      actually (correctly) means no row in `question_neighbour` at all, so the lookup returns `null`,
      not an empty list — fixed with `getOrDefault(..., List.of())` at the assertion, not in the
      production code.
- **Tests:**
  - `NeighbourRankerTest` (pure, 11 tests): all five groups score correctly; no group match means not
    a neighbour at all; a candidate matching multiple groups is scored once, at the higher value; the
    seed is never its own neighbour; the difficulty/id tie-break ordering; the 20-cap; every result
    carries `provider = "metadata"`.
  - `NeighbourBuilderTest` (3 tests, real Postgres): **the tracker's own P3.T7 acceptance check** —
    every question with ≥ 2 same-lesson-and-topic peers gets ≥ 2 neighbours; an `EXCLUDED` question is
    never a candidate, neither as a seed nor as someone else's neighbour; calling `build` again after
    content changes replaces the previous computation wholesale rather than leaving stale pairings
    (the question that lost its shared topic correctly ends up with zero neighbours, not a leftover
    pairing with its old partner).
  - Full suite: `./gradlew test` → **1470 passed, 31 skipped, 0 failures, 0 errors**.
- **Deviations from the plan:** the `theory.similarity.source` always-gates-a-real-bean design above
  (a strengthening, not a weakening, of what the tracker literally asked for).
- **Issues found / open risks:** none new.
- **Ready to continue:** YES.
- **Next task:** P3.T8 (platform endpoints: sync and content report) — now unblocked, since it depends
  on P3.T5 (done) and P3.T7 (done). That's also the last task in Phase P3.

### 2026-11-02 · P3.T8 · Platform endpoints: sync and content report

- **Status:** DONE
- **Repo / branch / commit:** ENG · feat/theory-app-implementations · 1743929e
- **What was done:**
  - **A real gap found while scoping this task, fixed as a necessary precursor:** `ContentSyncService`
    already computed *why* a question was excluded (`QuestionValidationResult.reason()`) but never
    persisted it, and an `EXCLUDED` question never gets a `content_question_revision` row either (the
    insert is gated on `result.valid()`), so the reason was permanently unrecoverable after the fact —
    the content report needed it reportable. Fixed with `V1_0_16_2__content_question_exclusion_reason.sql`
    (`content_question.exclusion_reason TEXT`), threaded through the entity/model/repository/store, and
    wired into `ContentSyncService`'s question loop
    (`questionModel.setExclusionReason(result.valid() ? null : result.reason().name())`).
  - `TheoryContentPlatformController` (`learn/platform/api/`), both endpoints `@PlatformAdmin`:
    - `POST /v1/platform/theory/content-sync?full=` calls `ContentSyncService#sync` directly — same
      module as the controller, so this is "the regular controller" CLAUDE.md's ExternalUseCase
      delegation rule talks about, not a cross-tier call; `TheoryContentSyncExternalUseCase` stays the
      job module's own entry point into the same primary method.
    - `GET /v1/platform/theory/content-report` calls the new `ContentReportService`.
  - `ContentReportService` (read-only, `@Transactional(readOnly = true)`) assembles: the latest
    release; hidden lessons and templates; excluded questions with their reason; similarity-coverage
    gaps; and the per-template difficulty mix (R-7) — all from store reads already built in earlier
    tasks, plus two new store methods (`findAllHiddenLessons`, `findAllHiddenTemplates`,
    `findAllExcludedQuestions`) added alongside the exclusion-reason fix.
  - `SimilarityCoverageChecker` (pure, like `NeighbourRanker`/`HomeLessonResolver`): Plan §4.4's
    report-only rule — for each ACTIVE question at level `L`, at least 2 of its stored neighbours must
    be at level `L` or `L-1` **and** in the same-or-earlier lesson (the same filters the retry phase's
    similar-item selection will apply in P4, so a neighbour that wouldn't pass those filters can't
    count toward coverage either). Lesson order is `(unit sort, lesson sort)`, built from every lesson
    (visible or hidden) joined with unit sort — a question's home lesson isn't guaranteed visible.
  - The extras-shortfall rate from Plan §5.3 step 5 is **not** in this report, per the tracker's own
    note — `retry_extras_short` lives on `lesson_attempt`, which P4.T1 creates.
  - New DTOs in `learn/platform/api/dto/`: `TheoryContentReleaseDTO`, `HiddenLessonDTO`,
    `HiddenTemplateDTO`, `ExcludedQuestionDTO`, `SimilarityCoverageGapDTO`, `TemplateDifficultyMixDTO`,
    `TheoryContentReportDTO` (the aggregate).
- **Tests:**
  - `SimilarityCoverageCheckerTest` (pure, 6 tests): the 2-neighbour threshold; a neighbour one level
    *above* the seed doesn't count; a neighbour in a later lesson doesn't count; a neighbour in an
    earlier lesson does; zero stored neighbours is a gap with count 0. Each assertion scopes to the
    seed question's own gap, since the checker (correctly) evaluates every question in the bank, not
    only the one the test cares about — the bank's other questions come back as their own gaps too
    when the test gives them no neighbours of their own.
  - `ContentReportServiceTest` (1 test, real Postgres): seeds a visible lesson/template, a hidden
    lesson/template, two ACTIVE questions each with only one stored neighbour (below the coverage
    threshold) and one EXCLUDED question with a reason, then asserts every section of the assembled
    report.
  - `TheoryContentPlatformControllerTest` (6 tests): opts out of the test harness's blanket permit-all
    security chain (imports the real `SecurityConfig` + `MethodSecurityConfig`, same pattern as
    `PublicEndpointSecurityTest`) — needed because under the default permit-all chain an anonymous
    request still reaches `@PreAuthorize` as a 403, never a genuine 401. Covers: unauthenticated → 401,
    authenticated without `platform_admin` → 403, and the happy path for both endpoints.
  - Full suite: `./gradlew test` → **1483 passed, 31 skipped, 0 failures, 0 errors**.
- **Deviations from the plan:** none beyond the exclusion-reason persistence fix, which is a
  precursor the tracker's own P3.T4 entry didn't call for explicitly but P3.T8 depends on.
- **Issues found / open risks:** none new.
- **Ready to continue:** YES.
- **Next task:** P3 phase exit is now checkable (every P3 task is done) — the engine syncs the staging
  stub every 30 s, holds a snapshot per instance, and the content report is in place. P4 (engine:
  attempts, grading, retry) is next, starting with P4.T1 (migrations and retry policy), but per this
  session's pattern that's a proposal to make, not something to start unilaterally.

### 2026-11-02 · P4.T1 · Migrations and retry policy

- **Status:** DONE
- **Repo / branch / commit:** ENG · feat/theory-app-implementations · 20268b67
- **What was done:**
  - `V1_0_17__theory_attempts.sql`: `lesson_attempt`, `attempt_item`, `mistake` with every Plan §6
    column, the tracker's own constraint list (the `UNIQUE(app_user_id, request_id)`, the partial
    unique one-open-attempt-per-lesson index, `PK(attempt_id, seq)` + `UNIQUE(response_id)`, both
    named indexes, and non-negative-count CHECKs), plus one strengthening beyond the tracker's literal
    list: a composite FK `attempt_item (question_id, version) → content_question_revision (question_id,
    version)`, so a pinned revision can never point at a version that was never synced.
  - `V1_0_18__theory_retry_policy.sql`: `retry_policy` with the seeded GLOBAL row (every key, the
    tracker's own defaults). **Deviation, logged deliberately:** Plan §6's diagram shows this table's
    PK as `(scope, scope_id)` directly; this uses a surrogate `BIGSERIAL id` + `UNIQUE(scope,
    scope_id)` instead, the same shape `theory_lesson_progress` (V1_0_4, pre-dating this feature)
    already uses for its own natural key. Spring Data JDBC's `CrudRepository` wants one single
    `@Id`, and unlike `content_template_question`/`question_neighbour` (which fold into a sibling
    entity's repository that already has one), there is no natural parent entity for this table to
    fold into — so a surrogate id is more idiomatic here than inventing a composite-key repository
    from scratch.
  - Both `policy_snapshot`/`option_order`/`key_values` are TEXT holding JSON from the start, not
    JSONB-then-converted — the mistake from P3.T2 (the engine has no JSONB converter pair registered
    anywhere) is now known up front, so there was no need to repeat the two-migration fix.
  - `RetryPolicyResolver` (pure, like `NeighbourRanker`): merges every stored row that applies —
    GLOBAL, then UNIT, then LESSON — **key by key**, not row-by-row, so a LESSON row overriding only
    `extras_per_wrong` still inherits `extras_min`/`extras_max`/etc. from UNIT or GLOBAL. Falls back
    to Plan §5.6's hardcoded defaults if even the seeded GLOBAL row is somehow missing a key.
    `RetryPolicyKey` is the single table of which keys exist at which scopes (`similar_scope` never at
    LESSON, `difficulty_level_map` only at GLOBAL), read by both the resolver and the validator so the
    two can't drift apart on this.
  - **Cached in the snapshot, per the tracker's own wording:** `ContentSnapshot` now holds the whole
    `retry_policy` table (a handful of rows) and exposes `retryPolicyFor(unitId, lessonId)`, resolving
    lazily per call rather than precomputing one policy per lesson up front — cheap enough (linear
    scan over a handful of rows) that precomputing would solve a problem that doesn't exist yet.
  - Platform endpoints on the existing `TheoryContentPlatformController`: `GET
    /v1/platform/theory/retry-policy` (every stored row) and `PUT
    /v1/platform/theory/retry-policy/{scope}/{scopeId}`. The PUT is a **full replace** of that row's
    overrides (CLAUDE.md's own PUT = full-replace rule), not a merge — a field left out of the body is
    cleared, not left as it was. This was a real design decision, not a default: a merge would better
    match "set one override without resending the rest", but CLAUDE.md is explicit that PUT means full
    replace and PATCH means partial, and `GET` already returns each row's current content for a
    front-end to load-modify-resend. Logged here so a future PATCH variant isn't mistaken for a fix to
    a bug.
  - **A real security gap caught before it shipped:** the tracker doesn't specify where `updated_by`
    comes from. A first draft took it from the request body — trusting the caller to say who they are
    is exactly the kind of thing CLAUDE.md's Identity section calls out as a defect elsewhere in this
    codebase. Fixed before writing any test against it: `updated_by` is derived from
    `AuthenticatedUser#getUserId(jwt)` in the controller, never accepted from the client.
  - Validation is split in two, deliberately: Jakarta bean validation on `UpdateRetryPolicyRequest`
    covers each field's own range (`@DecimalMin`/`@Max` etc., matching Plan §5.6's table exactly), and
    the pure `RetryPolicyValidator` covers what bean validation can't express — `extrasMin ≤ extrasMax`
    together, and "this key isn't editable at this scope". A scope string that isn't
    `GLOBAL`/`UNIT`/`LESSON`, or a GLOBAL PUT whose `scopeId` isn't the literal string `"GLOBAL"`, are
    both rejected the same way (`RetryPolicyInvalidException`, 422, new `ErrorCode.Theory.RETRY_POLICY_INVALID`).
  - **Known, deliberate gap, not silently dropped:** a PUT to a UNIT/LESSON `scopeId` that doesn't
    correspond to any real `content_unit`/`content_lesson` row is not rejected — it simply never
    resolves for any real lesson, exactly like the migration's own comment on why `scope_id` carries
    no FK (a unit/lesson can be re-synced away without a stale policy row blocking that). Existence
    validation at write time was consciously left out of scope here; worth a 404 check if an admin UI
    for this ships later.
- **Tests:**
  - `RetryPolicyResolverTest` (pure, 7 tests): no-rows-at-all falls back to hardcoded defaults; a
    GLOBAL-only override; UNIT overriding GLOBAL for one key while another key falls through
    untouched; LESSON overriding both; rows for an unrelated unit/lesson are ignored; the exact
    `BigDecimal` round-trip for `extras_per_wrong`; `difficulty_level_map` replaces wholesale.
  - `RetryPolicyValidatorTest` (pure, 11 tests): every range/scope rule, including the two keys'
    scope-eligibility in both directions (allowed and rejected) and the "at least one field" guard.
  - `TheoryContentStoreTest` (+3 tests, real Postgres): the seeded GLOBAL row is readable; a new
    scope/scopeId inserts; a second PUT to the same row **replaces** `key_values` wholesale rather than
    merging (the specific behaviour the full-replace decision above depends on).
  - `RetryPolicyServiceTest` (7 tests, real Postgres): a valid edit is readable afterward; GLOBAL with
    a mismatched scopeId, an unknown scope string, `extrasMin > extrasMax`, and `similar_scope` at
    LESSON scope all reject with `RetryPolicyInvalidException`; **a valid edit bumps the content
    release** (`updatePolicy_validEdit_bumpsTheContentRelease`) — the tracker's own acceptance line
    ("visible on a second instance within 30 s") is this test plus `ContentSnapshotProviderTest`'s
    already-proven 30 s polling, composed rather than re-proven from scratch; and a full multi-key PUT
    applies every provided key at once.
  - `TheoryContentPlatformControllerTest` (+8 tests): 401/403/200 for both new endpoints, a
    bean-validation 422 (`extrasPerWrong` out of its `@DecimalMax` range), and a service-level 422
    (mocked `RetryPolicyInvalidException`) to prove both validation layers actually reach the HTTP
    response as 422, not just internally.
  - `ContentSnapshot`/`ContentSnapshotProvider`/`ContentSnapshotBuilder`'s existing tests updated for
    the new constructor parameter — no behavioural change to any of them.
  - Full suite: `./gradlew test` → **1519 passed, 31 skipped, 0 failures, 0 errors**.
- **Deviations from the plan:** the surrogate-id `retry_policy` table (above); PUT = full replace
  rather than merge (above); `updated_by` from the JWT, never the request body (above).
- **Issues found / open risks:** the UNIT/LESSON `scopeId` existence gap noted above — deliberate, not
  forgotten.
- **Ready to continue:** YES.
- **Next task:** P4.T2 (entitlement and unlock rules) — depends only on P4.T1, which is now done.

### 2026-11-03 · P4.T2 · Entitlement and unlock rules

- **Status:** DONE
- **Repo / branch / commit:** ENG · feat/theory-app-implementations · 7ff5b92f
- **What was done:**
  - **The tracker's own first instruction — "locate today's unit-lock logic" — turned up a real
    finding, not just a mapping exercise.** `LearnHubService#buildModuleProgress` (the Directus-backed
    theory hub) computes `isLocked = accessLevel == FREE && !previousCompleted`: a free learner can
    reach *every* module eventually, one at a time, in order — subscription only grants the right to
    jump ahead. There is no per-module paywall anywhere in that code (`ModuleContentModel` has no
    `requiresSubscription` field at all — only `ExamTypeModel` does, for mock exam types, a different
    product surface). So "map to Boost module ids by sort order" could not mean translating an
    existing Directus-id-keyed entitlement list into Boost ids — **there is no existing entitlement
    boundary to map**, Directus and Boost are two separate content systems with no shared identities,
    and reusing the hub's logic verbatim would have made every unit eventually reachable for free,
    which contradicts Plan decision 10's "otherwise the app shows Upgrade to Continue" (a learner who
    is *never* unblocked). Resolved by reading forward in the plan instead of guessing: §14's own
    test-account list says "one free learner (**Unit 1 only**), one entitled learner" — confirming the
    actual rule is "the first Boost unit by `content_unit.sort` is free; every other unit needs an
    active subscription," which is new design territory this task fills in, not a migration of
    existing logic. Logged here rather than silently assumed because it's a monetization-affecting
    decision a future reader would reasonably expect to be sourced from somewhere, and it isn't.
  - `TheoryEntitlement.isUnitEntitled(userId, unitId)`: subscribed → entitled to everything; free →
    entitled only to `snapshot.units().get(0)` (already sorted ascending by `sort` in `ContentSnapshot.build`).
  - **A second finding, caught before writing the caching code, not after:** `hasActiveSubscription`'s
    truth changes on its own as `expires_at` passes — there is no write event at that moment, only at
    purchase/renewal (`confirmSubscription`). An eviction-only cache (which is what "invalidated on
    subscription change" literally asks for) would keep granting paywalled access for as long as the
    cache entry lived, silently, past a lapsed subscription's expiry. Fixed by bounding
    `theorySubscriptionStatus` with a 5-minute TTL in `CacheConfig` **in addition to** an explicit
    `@CacheEvict` on `LearnSubscriptionService#confirmSubscription`, so an upgrade takes effect
    immediately while a lapse is caught within a bounded, acceptable delay rather than never.
  - Split the cached call into its own bean, `TheorySubscriptionCache` — `@Cacheable` is a Spring AOP
    proxy concern, and `TheoryEntitlement` calling a cached method on `this` would silently bypass it
    (same trap `PinnedRevisionLoader`, P3.T6, was split out to avoid).
  - `UnlockService.resolve(ContentSnapshot, Set<String> completedLessonIds, Predicate<String> unitEntitled)`:
    one pass over every unit's visible lessons in order. The first lesson not yet completed decides
    everything — `CURRENT` if its unit is entitled, `LOCKED` if not, and every lesson after it is
    `LOCKED` regardless of its own entitlement (it can't have been reached without the one before it
    completing first). A `HIDDEN` lesson needs no special case at all: it's simply never in
    `ContentSnapshot.lessonsOf(...)`, so the walk never sees the gap in `sort` numbers.
  - `ContentSnapshot` gained no new field for this — `UnlockService` reads `units()`/`lessonsOf(...)`,
    already there from P3.T6.
- **Tests:**
  - `UnlockServiceTest` (pure, 7 tests): first lesson unlocked with nothing completed; a hidden
    lesson's absence doesn't block the one after it; cross-unit with and without entitlement
    (including the "no CURRENT at all" case when blocked); retaking a completed lesson changes
    nothing; every lesson completed leaves nothing CURRENT or LOCKED; and the tracker's own
    table-driven acceptance line (completed/current/locked all exercised in one snapshot).
  - `TheoryEntitlementTest` (3 tests, Mockito, no Spring): subscribed → entitled everywhere; free →
    entitled only to the first unit by sort; no units synced yet → free learner entitled to nothing.
  - `TheorySubscriptionCacheTest` (5 tests, real Postgres + `@MockitoSpyBean`, same convention as
    `PinnedRevisionLoaderTest`): two calls for the same user hit the use case once; different users
    cache separately; the cache bean exists; and — the one that actually proves the second finding
    above — seeding a `PENDING` subscription, priming the cache to `false`, then calling
    `confirmSubscription` and confirming `isSubscribed` flips to `true` on the very next call rather
    than waiting out the TTL.
  - Full suite: `./gradlew test` → **1533 passed, 31 skipped, 0 failures, 0 errors**.
- **Deviations from the plan:** none — the entitled-unit boundary and the TTL-plus-eviction caching
  are both filling genuine gaps in the tracker's own wording, not deviating from a stated rule.
- **Issues found / open risks:** none new.
- **Ready to continue:** YES.
- **Next task:** P4.T3 (`QuestionSetSelector`, `fixed-v1`) — depends only on P4.T2, which is now done.

### 2026-11-03 · P4.T3 · QuestionSetSelector (fixed-v1)

- **Status:** DONE
- **Repo / branch / commit:** ENG · feat/theory-app-implementations · c3322bcc
- **What was done:**
  - `QuestionSetSelector` (pure port) + `SelectionContext` (snapshot, userId, lessonId, `attemptNo`) +
    `QuestionSetSelection` (ordered `QuestionRef`s + strategyId + selectionReason). `attemptNo` is
    resolved by the caller from the learner's prior attempts — the port itself stays pure, no I/O, as
    the tracker's own acceptance line requires ("no Spring context in its tests").
  - `FixedTemplateSelector` (`fixed-v1`): one formula covers both first attempt and every retake —
    `index = (hash(app_user_id, lesson_id) mod N + (attemptNo − 1)) mod N`, since attempt 1 adds zero.
    Only questions present in the snapshot (i.e. `ACTIVE` with a current revision) are kept from a
    template's membership list, in the template's own order — an excluded/invalid member is silently
    dropped rather than surfaced, since the engine already decided it's unservable at sync time.
  - **No murmur3 (or any stable-hash) dependency existed in this codebase.** Adding Guava — the
    obvious off-the-shelf source for `Hashing.murmur3_32()` — just to get one hash function felt like
    the wrong trade for a dependency with a large transitive footprint. Hand-rolled the public-domain
    `MurmurHash3_x86_32` algorithm (Austin Appleby's reference, widely reproduced verbatim in Guava,
    Cassandra, Elasticsearch, etc.) as a small package-private utility instead. It is not validated
    against an external library's exact output — bit-compatibility with another implementation was
    never the requirement, only a hash that's (a) actually stable across JVM versions, unlike
    `Object.hashCode`/`String.hashCode`, and (b) well-distributed, which the 10k-synthetic-user test
    below checks directly rather than trusting by inspection.
  - `theory.selection.strategy` gates `FixedTemplateSelector` the same way `theory.similarity.source`
    gated `MetadataSimilarQuestionProvider` (P3.T7): the only implementation that exists, so any other
    configured value fails application startup rather than silently no-op'ing.
- **Tests:**
  - `Murmur3HashTest` (4 tests, pure): determinism; the empty string doesn't throw; every tail-byte
    fall-through branch (0/1/2/3 extra bytes) is exercised; 1000 distinct inputs land in all 4 buckets
    when reduced mod 4 (not a constant or a trivial identity function).
  - `FixedTemplateSelectorTest` (7 tests, pure, no Spring context anywhere): stable across repeated
    calls; only valid questions kept, in template order; the retake reason string; six retakes across
    3 templates repeat the exact same sequence on the second lap (true rotation, not drift); a
    template count that changes between the first attempt and a retake still returns a valid in-range
    selection rather than throwing; zero visible templates returns an empty selection, not an
    exception; and the tracker's own acceptance bound — 10,000 synthetic users across 4 templates land
    within ±10% of an even split.
  - Full suite: `./gradlew test` → **1544 passed, 31 skipped, 0 failures, 0 errors**.
- **Deviations from the plan:** the hand-rolled murmur3 instead of a library dependency (above) — a
  strengthening of "use a stable hash" into "without adding a new dependency for it," not a weakening.
- **Issues found / open risks:** none new.
- **Ready to continue:** YES.
- **Next task:** P4.T4 (start, resume and read attempt) — depends only on P4.T3, which is now done.

### 2026-11-03 · P4.T4 · Start, resume and read attempt

- **Status:** DONE
- **Repo / branch / commit:** ENG · feat/theory-app-implementations · 9bd75b95
- **What was done:**
  - `AttemptService.start(userId, lessonId, requestId)`: checks `(userId, requestId)` first (true
    replay if the lesson matches, `THEORY_REQUEST_ID_CONFLICT` if it doesn't — the same `requestId`
    reused for a different lesson), then any open (non-`COMPLETED`) attempt on the lesson (resume),
    then guards (lesson exists → `THEORY_LESSON_NOT_FOUND`; locked → `THEORY_MODULE_LOCKED` if the
    unit isn't entitled, else `THEORY_LESSON_LOCKED`, reusing `UnlockService`'s `LOCKED` status and
    re-checking entitlement only to pick which of the two errors applies), then selects via
    `QuestionSetSelector`, shuffles each question's `option_keys` with `SecureRandom`, resolves the
    retry policy from the snapshot, and inserts.
  - **A real transaction-isolation bug caught before it shipped, not after:** Plan §6 says a losing
    `start()` recovers from the unique-constraint violation by re-querying for whichever row won. The
    first draft wrapped the whole method in one `@Transactional`, including the racy insert — but
    Postgres aborts a transaction block *entirely* on a constraint violation; any further statement on
    that same connection fails with "current transaction is aborted" until it's rolled back. The
    recovery re-query would have failed too, on the very connection the plan's own recovery strategy
    depends on. Fixed by splitting the insert into its own bean, `AttemptInsertTransaction`, with
    `@Transactional(propagation = REQUIRES_NEW)` — a genuinely separate connection regardless of the
    caller's own transactional state — and removing `@Transactional` from `start()` itself entirely
    (Plan §6 already says start takes no lock, so there's nothing for it to protect). This was caught
    by reasoning about Postgres's own error-recovery semantics before writing the concurrency test, not
    by watching the test fail — though the test (below) would have caught it either way, non-
    deterministically, since the race only manifests under genuine thread contention.
  - `get(userId, attemptId)`: 404 (`THEORY_ATTEMPT_NOT_FOUND`) for both an unknown id and another
    learner's attempt — the store's `findById` is unconditional, the ownership filter happens in the
    service, same "don't even confirm the id exists" shape the exception's own javadoc (from P3.T1)
    already specified.
  - `lesson_attempt`/`attempt_item` are written via hand-rolled `@Modifying @Query INSERT`, never
    `CrudRepository#save()` — `attempt_id` is a client-assigned `UUID`, and Spring Data JDBC's default
    `save()` treats an entity whose id is already set as an *update*, which would silently no-op
    against a row that doesn't exist yet. `attempt_item`'s composite key (`attempt_id`, `seq`) folds
    into `LessonAttemptRepository`, the same convention `content_question_revision`/
    `question_neighbour` already use.
  - `TheoryInternalTokenFilter`: no existing `X-Fordona-Internal-Token` mechanism existed anywhere in
    the codebase (confirmed by search before writing this). Registered via
    `addFilterAfter(filter, BearerTokenAuthenticationFilter.class)` so JWT authentication has already
    run; compares with `MessageDigest.isEqual`, never `String.equals`, per CLAUDE.md's own security
    practices. Only wired into the non-dev-mode branch of `SecurityConfig` — `security.dev-mode=true`
    already permits every path, so there's nothing for this filter to add there.
  - `lesson_progress` (P5) genuinely doesn't exist yet, so the tracker's own "upsert lesson_progress /
    leave a hook" has no hook to leave — `findCompletedLessonIds` instead derives completion directly
    from `lesson_attempt.status = 'COMPLETED'`, which already carries the fact `UnlockService` needs.
    P5 can either keep reading it this way or switch to `lesson_progress` once that table exists;
    nothing here commits to one or the other.
- **Tests:**
  - `AttemptServiceTest` (6 tests, real Postgres): happy path (3 pinned, unanswered items, shuffled
    option order); unknown lesson → 404; unit not entitled → `THEORY_MODULE_LOCKED`; previous lesson
    not completed → `THEORY_LESSON_LOCKED`; a replay with the same `requestId` returns the identical
    attempt with no second row; **two real threads racing `start()` for the same user/lesson with
    different `requestId`s produce exactly one row and both threads observe the same attempt id** —
    the tracker's own concurrency acceptance check, and the one that would have caught the transaction
    bug above if it hadn't been caught first by reasoning about it.
    **Deliberately does not use the shared `ContentSnapshotProvider`/`ContentSnapshotBuilder`
    singletons**: they read `findAllUnits()`/`findAllVisibleLessons()` unfiltered over the whole
    `IntegrationTestBase`-shared, never-rolled-back Postgres instance, so hundreds of other tests'
    leftover units/lessons (often sharing this test's own `sort` values) would sit in
    `UnlockService`'s global ordering ahead of this test's fixtures, non-deterministically locking a
    lesson that should be `CURRENT` — caught directly by running the suite, not by inspection: the
    happy-path test failed with `THEORY_LESSON_LOCKED` on a lesson with nothing before it. Fixed by
    building the `ContentSnapshot` directly from this test's own fixtures (`ContentSnapshot.build`)
    while still seeding the real content rows for `lesson_attempt`/`attempt_item`'s foreign keys, and
    mocking `TheoryEntitlement` directly rather than seeding real subscription rows per scenario.
  - `TheoryAttemptInternalControllerTest` (6 tests): no JWT and no internal token → 403 (this
    implementation's filter ordering never produces 401 — documented in the test itself, and the
    tracker's own "401/403" wording already accepts either); valid JWT but missing or wrong internal
    token → 403; valid JWT + internal token → 200, and the raw response body contains neither
    `correctOptionKey` nor `correct_option_key` anywhere (the tracker's own acceptance line, asserted
    by string search exactly as specified, not by field-presence alone); another learner's attempt →
    404.
  - Full suite: `./gradlew test` → **1556 passed, 31 skipped, 0 failures, 0 errors**.
- **Deviations from the plan:** none beyond the transaction-isolation fix above, which implements
  Plan §6's own stated recovery strategy correctly rather than deviating from it.
- **Issues found / open risks:** none new.
- **Ready to continue:** YES.
- **Next task:** P4.T5 (answer endpoint and grading) — depends only on P4.T4, which is now done.

### 2026-11-03 · P4.T5 · Answer endpoint and grading

- **Status:** DONE
- **Repo / branch / commit:** ENG · feat/theory-app-implementations · 42713700
- **What was done:**
  - `AttemptService.answer(userId, attemptId, seq, selectedOptionKey, responseId, durationMs,
    acceptLanguageHeader)`: `findByIdForShare` (new repository method, `SELECT ... FOR SHARE`) +
    ownership filter → `THEORY_ATTEMPT_NOT_FOUND` if missing or another learner's; attempt already
    `COMPLETED` → `THEORY_PHASE_CLOSED`; unknown `seq` → `THEORY_ITEM_NOT_FOUND`; the item's own
    `phase` must match the attempt's current phase (`IN_LESSON` → `LESSON`, `IN_RETRY` → `RETRY`) or
    `THEORY_PHASE_CLOSED`; the option must be one of the pinned revision's `option_keys` or
    `THEORY_OPTION_INVALID` (422).
  - **Graded from `PinnedRevisionLoader`, not the live `ContentSnapshot`.** The tracker's own wording
    ("grade from the snapshot") doesn't hold up once you ask what happens if Boost republishes the
    question between an attempt starting and the learner answering: the snapshot only ever holds the
    *current* revision, but the item is pinned to whatever revision was current when it was created.
    Grading against the snapshot would silently re-grade a still-open item against content it was
    never shown. `PinnedRevisionLoader` (P3.T6) exists for exactly this and is already keyed by
    `(questionId, version)` with an unbounded, never-expiring cache — reusing it rather than the
    snapshot was the one real correction to the tracker's literal wording this task needed. The
    snapshot is still read once, in-memory only, for the mistake ledger's `home_lesson_id`.
  - The conditional `UPDATE ... WHERE answered_at IS NULL` is exactly Plan §6's "one statement is the
    idempotency check, the already-answered-differently check and the write": `affected == 1` → graded
    and the ledger runs; `affected == 0` → re-fetch the item and compare `(responseId,
    selectedOptionKey)` against what's stored — identical → replay (200, same feedback); anything
    else → `THEORY_RESPONSE_CONFLICT` (409). A `responseId` already attached to a *different* item
    throws `DataIntegrityViolationException` on the `UPDATE` itself (globally `UNIQUE(response_id)`),
    caught and translated to the same 409 — no separate code path needed for that case.
  - `correctOptionLabel` is computed from the learner's own pinned `option_order`
    (`indexOf(correctOptionKey)` → `'A' + index`), never a fixed letter — so "the right answer is C"
    is always true against what that specific learner actually saw.
  - `TheoryLocaleResolver` (pure): resolves the feedback's explanation locale from `Accept-Language`
    against `theory.content.supported-locales`, falling back to `sv-SE`. Deliberately separate from
    `LocaleContextHolder`/`LanguageContext` (the generic i18n bundle locale, keyed by
    `app_language.id`) — a different concern, resolving which Boost-authored translation to serve,
    not which bundle to translate an error message from.
  - **Mistake ledger placement, a real decision, not an oversight:** `mistake`'s only FK points at
    `content_question`, which would suggest folding its queries into `ContentQuestionRepository`
    (the convention `question_neighbour`/`content_question_revision` already follow). Placed in
    `LessonAttemptRepository` instead — `mistake` is learner progress/answer state, the same bounded
    context as attempts and items, not theory-content-sync state, and `TheoryContentStore` has no
    business holding per-learner rows. Logged so a future reader doesn't "fix" this to match the FK.
  - `resolved_via` can only ever be `RETAKE` or `LATER` right now: it compares the resolving attempt's
    `lesson_id` against the mistake's `home_lesson_id`. `REPEAT` ("in the retry phase, straight after
    being shown the answer" per Plan §5.5) requires a retry-phase item to exist at all, which is
    P4.T6's job — every item answered today is `phase=LESSON`.
- **Tests:**
  - `AttemptServiceTest` (+11 tests, real Postgres, real `PinnedRevisionLoader`/content tables for the
    FK reasons already logged under P4.T4): correct and incorrect grading; 422 invalid option; 404
    unknown seq; 409 phase-closed on a completed attempt; a replay returns identical feedback; same
    item answered twice with a different option → 409; the same `responseId` reused on a different
    item → 409 (via the `DataIntegrityViolationException` path); the full ledger cycle
    OPEN → RESOLVED (`RETAKE`) → OPEN across three real attempts on the same lesson; two real threads
    racing to answer the same item with different options/`responseId`s — exactly one succeeds, the
    other gets `THEORY_RESPONSE_CONFLICT`, never an unhandled error; and the acceptance check itself —
    priming `PinnedRevisionLoader` once, then asserting a full `answer()` call makes zero further
    `TheoryContentStore#findRevision` calls (`@MockitoSpyBean`, same convention as
    `PinnedRevisionLoaderTest`).
  - `TheoryAttemptInternalControllerTest` (+3 tests): missing internal token on the new endpoint →
    403; a valid answer returns 200 with the real `correctOptionKey`/`correctOptionLabel` (legitimate
    here — this endpoint's whole job is returning them post-answer) while the raw body never contains
    the *field name* `correct_option_key` (snake_case) anywhere, guarding against a stray serialization
    config change rather than re-proving the pre-answer case P4.T4 already covers; 422 on an invalid
    option.
  - Full suite: `./gradlew test` → **1570 passed, 31 skipped, 0 failures, 0 errors**.
- **Deviations from the plan:** grading from `PinnedRevisionLoader` instead of the live snapshot
  (above, a correctness fix the tracker's wording glossed over); `mistake`'s repository placement
  (above, a judgment call on bounded-context ownership over FK structure).
- **Issues found / open risks:** none new.
- **Ready to continue:** YES.
- **Next task:** P4.T6 (retry composer) — depends on P4.T5 (done) and P3.T7 (done).

### 2026-11-03 · P4.T6 · Retry composer

- **Status:** DONE
- **Repo / branch / commit:** ENG · feat/theory-app-implementations · 8c7a8b31
- **What was done:**
  - `RetryComposer.compose(snapshot, lessonItems, currentLessonId, completedLessonIds, seenQuestionIds,
    unitEntitled, policy, shuffleSeed)` — pure, no I/O, no `@Component`/Spring wiring at all (it's a
    static method, like `NeighbourRanker`). Scope is deliberately narrow per the tracker's own split:
    P4.T6 is the composer and its tests only; wiring it into `AttemptService` (calling it from phase
    completion, persisting retry items, writing `retry_extras_short`) is explicitly P4.T7's job.
  - `wrongSeeds` are derived internally from a single `lessonItems` input (every lesson-phase item,
    correct and wrong) rather than taking "seeds" and "already-in-attempt" as two separate inputs —
    filter (c) needs the *full* lesson item set (a correct item's question must never resurface as a
    "similar" item either), while only the wrong ones seed the round-robin walk and become repeat
    items. One input serves both purposes without the caller needing to pre-split them.
  - **Fully deterministic, not just "item order from a seed":** the tracker's own acceptance bar
    ("deterministic order for the same attempt id") is a real test of purity, so every random choice
    inside the composer — both repeat/similar items' shuffled option orders *and* the final
    item-order shuffle — comes from one `java.util.Random` seeded from `shuffleSeed`, never
    `SecureRandom`. `SecureRandom` would have made the composer non-deterministic and literally
    impossible to pass that test; using it anywhere inside a function explicitly specified as "pure"
    would have been the error, not a stylistic choice. Plan §5.3 point 4 only asks for the *item
    order* to be seeded; extending that to option orders is this task's own correctness requirement,
    not scope creep — a "pure composer" that calls `SecureRandom` isn't pure.
  - **Filter (b) is hardcoded to "same level or one down, floor easy," not driven by
    `policy.levelDropAllowed()`.** `levelDropAllowed` is a real, range-validated (0–2), per-scope
    field on `retry_policy` (P4.T1) — so this is a genuine, visible gap: a config field a platform
    admin can edit per-unit or per-lesson that this filter never reads. Not fixed silently, because
    Plan §5.3 itself states the filter as a fixed "L or L−1" with no mention of the policy at all —
    wiring it in would be *adding* a plan requirement, not implementing one. Logged here as an open
    question for whoever next touches this filter: either the plan intends `levelDropAllowed` for
    something else entirely (nothing else in the plan currently reads it), or filter (b) should read
    it and the plan's own wording is the thing that's stale.
  - "Valid and visible" (filter a) is checked against the *current* snapshot at retry-composition
    time, not against whatever was true when `question_neighbour` was last rebuilt — a neighbour that
    existed at the last release but has since been excluded or had its lesson hidden is treated as
    absent (`snapshot.question(id)` / `snapshot.lesson(...)` both have to resolve), so a slightly
    stale neighbour list can never serve broken content even between releases.
- **Tests:**
  - `RetryComposerTest` (20 tests, pure, no Spring context): the E table via `@ParameterizedTest`
    (0→0, 1→2, 2→3, 3→5, 4→5, 10→5); every wrong item becomes exactly one repeat item at the same
    pinned revision; no wrong items → no retry phase at all; each filter (a–f) proven in isolation by
    giving a seed two neighbour candidates — one that should be rejected by that specific filter, one
    that should pass — and asserting only the valid one is picked; `similar_scope=ALL` explicitly
    allowing what `REACHED` would have blocked; the unseen-first fallback (a seen-only candidate is
    skipped on pass 1 then picked up on pass 2 rather than left as a shortfall) and unseen-preferred-
    over-seen-on-the-same-pass; the shortfall-down-to-repeats-only case with the exact `extrasShort`
    value asserted; same-seed-same-inputs reproduces identical item order *and* identical option
    orders; a 20-seed sweep confirms at least one seed reorders two repeat items differently (proving
    the seed actually matters, not just that the function runs); and the tracker's own property test
    — 20 different seeds over a deliberately overlapping 4-seed/6-candidate neighbour pool, each
    checked for zero duplicate question ids among the composed items and zero similar items that
    repeat a lesson question.
  - One genuine test-writing mistake, caught by running the suite rather than by inspection: the
    property test's first draft asserted "no composed item's question id is already in the lesson
    attempt" across *all* composed items — which is wrong for repeat items by design (a repeat item's
    whole point is reusing the wrong lesson item's own question id). Fixed by scoping that assertion to
    similar items only, where it's actually a real property.
  - Full suite: **not run to completion this session** — every `IntegrationTestBase` subclass failed
    with an `InvalidPathException: Trailing char < > at index 10: C:\Program` thrown during
    `ServiceConnectionContextCustomizerFactory`'s reflection at Spring context bootstrap. At the time
    this was (wrongly) diagnosed as a corrupted `PATH` entry on the host. **Correction (confirmed in
    the P4.T7 session):** the real cause was Docker Desktop's daemon not running at all — `docker info`
    showed the CLI client responding but the server/named-pipe connection failing
    (`open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified`), and
    `tasklist` showed zero Docker processes. The `PATH`-shaped exception is Testcontainers' own
    error-surfacing artifact when it can't reach Docker at all, not evidence of a corrupted `PATH`.
    No `PATH` entry was ever fixed; restarting Docker Desktop alone resolved it. **This commit was
    verified only by `RetryComposerTest` run in isolation (20/20 passed)** at the time — the full-suite
    regression check for P4.T6 was deferred to P4.T7, where it has since passed (see that entry).
- **Deviations from the plan:** none in the composer's own behaviour — the determinism and filter-b
  points above are documented interpretations of genuinely underspecified wording, not deviations from
  anything the plan states explicitly.
- **Issues found / open risks:**
  - `levelDropAllowed` remains completely unwired (see above) — worth raising with whoever owns the
    plan's retry-policy design before P4.T7 ships, since right now it's a config field with no effect.
    **Still open after P4.T7** — not addressed there either (P4.T7 only wires `RetryComposer` as-is).
  - ~~**Outstanding:** the full regression suite has not been re-run since before this task~~ —
    resolved in P4.T7: Docker Desktop was the actual blocker (see correction above), and the full
    suite is green as of that task.
- **Ready to continue:** YES.
- **Next task:** P4.T7 (phase completion) — depends on P4.T6, which is now done.

### 2026-11-03 · P4.T7 · Phase completion

- **Status:** DONE
- **Repo / branch / commit:** ENG · feat/theory-app-implementations · cb0a5611
- **What was done:**
  - `AttemptService.completeLessonPhase(userId, attemptId)`: `SELECT ... FOR UPDATE` on
    `lesson_attempt`, 409 `PHASE_INCOMPLETE` if any lesson-phase item is unanswered, writes the lesson
    totals. W = 0 → status `COMPLETED` directly. W > 0 → calls `RetryComposer.compose(...)` (P4.T6)
    with the lesson's own wrong items as seeds, inserts the composed items as `phase=RETRY` at the next
    `seq`, writes `retry_extras_short`, and moves the attempt to `IN_RETRY`. Calling it again once the
    attempt has left `IN_LESSON` returns the already-stored summary unchanged (natural idempotency, no
    marker column) rather than re-running the transition.
  - `AttemptService.completeRetryPhase(userId, attemptId)`: requires status `IN_RETRY` (else 409
    `PHASE_CLOSED`); 409 `PHASE_INCOMPLETE` if any retry item is unanswered; writes retry totals and
    moves the attempt to `COMPLETED`. Calling it again when already `COMPLETED` returns the stored
    summary (same idempotency pattern).
  - `RetryPolicy` is read back off `lesson_attempt.policy_snapshot` (written at `start()` in P4.T4) via
    `ObjectMapper`, not re-resolved from the live `RetryPolicyResolver` — the policy that applies to a
    retry phase is whatever was pinned when the attempt started, same pinning principle P4.T5 already
    established for question content.
  - `seenQuestionIds` for the composer's unseen-first pass comes from a new repository query
    (`findSeenQuestionIds`, all `attempt_item` rows the user has ever answered) — a genuine cross-attempt
    read, not scoped to the current attempt, since "seen" means seen by the learner at all.
  - New DTOs: `PhaseSummaryDTO(total, correct, wrong)`, `RetryPhaseDTO(total, items)`,
    `AttemptPhaseCompletionDTO(attemptId, status, lessonSummary, retrySummary, retry, next, progress)`.
    `next`/`progress` are always `null` — the contract shape P5 will fill in — and are correctly omitted
    from the JSON response by the existing global `spring.jackson.default-property-inclusion: non_null`,
    not by any new per-DTO annotation.
  - Two new endpoints on `TheoryAttemptInternalController`:
    `POST /internal/theory/v1/attempts/{attemptId}/phases/lesson/complete` and
    `.../phases/retry/complete`, both deriving the caller from the JWT as every other endpoint in this
    controller does.
- **Tests:**
  - `AttemptServiceTest` (+11 new tests, 27/27 total): W = 0 straight to `COMPLETED`; W > 0 to
    `IN_RETRY` with retry items served; 409 on unanswered lesson items; double-complete idempotency;
    a late answer attempted after the lesson phase has moved on → `PHASE_CLOSED`; retry-complete called
    before the attempt ever reached `IN_RETRY` → `PHASE_CLOSED`; 409 on unanswered retry items;
    double-complete idempotency for the retry phase; a 2-thread Testcontainers test asserting
    `FOR UPDATE` serializes two devices completing the same lesson phase at once into exactly one
    retry-item insert, not two; and the tracker's own full-flow acceptance test (start → 8 answers with
    2 wrong → lesson complete returns 5 retry items → 5 answers → retry complete → `COMPLETED`).
  - `TheoryAttemptInternalControllerTest` (+5 new tests, 13/13 total): missing internal token → 403;
    W > 0 → 200 with retry items and `next`/`progress` both absent from the JSON (`doesNotExist()`);
    unanswered items → 409; retry completion → 200 `COMPLETED`.
  - Two real test bugs found and fixed while writing the acceptance test, neither requiring any change
    to production code:
    - Seeding order: a test template's questions (`content_question`, FK'd to `home_lesson_id`) were
      seeded before the `content_lesson` row they reference existed — fixed by seeding the lesson first.
    - **Worth flagging explicitly, not just as a test fix:** `UnlockService.resolve()` walks every
      unit's lessons in **one global sort order**, not per-unit independently (Plan §1 decision 10) —
      a lesson in a later unit stays `LOCKED` regardless of that unit's own entitlement stub until every
      earlier lesson in the global walk is completed. The acceptance test's first draft gave its new
      8-question lesson's unit its own `isUnitEntitled` stub and expected that alone to unlock it; it
      instead stayed `LOCKED` because the shared fixture's own earlier lesson (unit sort 1) had never
      been completed. This is correct product behaviour, not a bug — fixed by having the test complete
      that earlier lesson for real (start → answer all correctly → `completeLessonPhase`) before
      starting the lesson under test, exactly as a real learner's sequential progression would require.
      Documented here because it is a non-obvious trap for any future test that seeds a second
      unit/lesson pair and assumes per-unit entitlement is sufficient to unlock it.
    - A secondary slip in the same test (a similar-item candidate question seeded against the wrong,
      older `unitId` instead of the new lesson's `unit8Id`) was also caught and fixed; it happened not to
      fail any assertion since both units were stubbed entitled by that point, but was corrected for
      consistency.
  - Full suite: **`./gradlew test --no-daemon -q` run to completion, exit code 0** — no cross-cutting
    regressions. Docker Desktop was confirmed running first (`docker info` → `Containers: 3`), closing
    out the P4.T6 entry's outstanding full-suite caveat (see the correction added to that entry above).
- **Deviations from the plan:** none observed.
- **Issues found / open risks:**
  - `levelDropAllowed` (flagged in P4.T6) remains unwired — `RetryComposer` is used here exactly as
    P4.T6 built it, so this task doesn't touch that gap either way. Still worth raising before the
    retry-policy UI ships.
  - None new from this task.
- **Ready to continue:** YES.
- **Next task:** P4.T8 (lesson state endpoint) — depends on P4.T7, which is now done.

### 2026-11-03 · P4.T8 · Lesson state endpoint

- **Status:** DONE
- **Repo / branch / commit:** ENG · feat/theory-app-implementations · 7645531a
- **What was done:**
  - `AttemptService.getLessonState(userId, lessonId)`, `@Transactional(readOnly = true)`, and
    `GET /internal/theory/v1/lessons/{lessonId}`. Reuses `UnlockService.resolve(...)` (P4.T2) for the
    lock/current/completed status, and `TheoryEntitlement.isUnitEntitled` a second time against the
    target lesson's own unit to distinguish *why* it's locked.
  - `status` is `UnlockService.LessonUnlockStatus`'s own name (`COMPLETED`/`CURRENT`/`LOCKED`), not the
    app-facing word ("available") the public lesson-screen example in Plan §7.3 uses for the same
    concept — see the deviation note below.
  - `questionCount`: a real open attempt's own `LESSON`-phase item count when one exists; otherwise a
    **dry run** of `QuestionSetSelector.select(...)` with `attemptNo = countAttempts + 1` (the same
    attempt number `start()` would use next), discarded without ever reaching `insertAttempt`/
    `insertItem`. A locked lesson never calls the selector at all and reports `questionCount = 0` —
    not just to save the call, but so an unentitled unit's question count is never computed or
    returned, consistent with Plan §7.3's "paid content never leaves the server" intent for the theory
    blocks (the count is a smaller leak, but the same principle).
  - `estimatedMinutes`: the lesson's authored value when set; otherwise `ceil(questionCount * 45 / 60)`.
  - New DTOs: `LessonStateDTO(status, locked, lockReason, openAttempt, questionCount, estimatedMinutes,
    lessonVersion)` and `LessonOpenAttemptRefDTO(attemptId, phase)`, where `phase` is the open attempt's
    own `status` (`IN_LESSON`/`IN_RETRY`), not the per-item `phase` field.
- **Deviations from the plan (both logged rather than guessed past):**
  1. **Locked lessons return 200, not 403.** Plan §7.3's "Locked lessons: 403 `THEORY_LESSON_LOCKED` or
     `THEORY_MODULE_LOCKED`" describes the **public** `GET /v1/lessons/{lessonId}` (BFF→app) contract.
     Plan §7.4 is explicit that the **internal** engine endpoint is different: *"The BFF never decides
     access itself: it fetches theory only when the engine says the lesson is not locked"* — which only
     makes sense if the engine reports `locked` as a field, not a thrown exception, since the BFF has to
     branch on it to decide whether to even call Boost for the theory blocks. The P4.T8 tracker entry's
     own test line ("locked → 403 with the right code") reads as carried over from `start()`'s behaviour
     and conflicts with §7.4's explicit sentence for this specific endpoint. Followed §7.4 (the more
     specific, more explicit text) over the tracker's test wording: this endpoint returns 200 with
     `locked: true` and `lockReason` set to `ErrorCode.Theory.MODULE_LOCKED`/`LESSON_LOCKED`. `start()`
     and `answer()` are unaffected and still throw as before — only this read-only state check differs,
     deliberately, because only this one is in the BFF's own access-decision path.
  2. **`estimatedMinutes`'s fallback formula is incomplete.** Plan §7.3 specifies "authored value, else
     reading time + media durations + 45 s × questions," but the module-structure table (row 72) states
     plainly that lesson theory content is "Not modelled" in the engine — it lives in Boost and is
     fetched only by the BFF (Plan §7.3's own "Composition" line for this exact endpoint lists what the
     engine supplies as "lock, status, open attempt, `questionCount` and `lessonVersion`" and does not
     include `estimatedMinutes` there, which lines up with this). The engine therefore has no reading
     time or media durations to compute with, only the question count. It returns the one component it
     can (`45s × questionCount`) rather than silently treating a partial computation as the full
     formula. Flagging for whoever builds the BFF-side theory hydration: the BFF has the actual blocks
     on every call already (it fetches them from Boost to compose the response body), so it is the
     natural place to compute or override the complete figure — this value should likely be treated as
     a floor, not the final number, until that happens.
- **Tests:**
  - `AttemptServiceTest` (+9 new tests, 36/36 total): unknown lesson → 404; unit not entitled → locked
    with `MODULE_LOCKED`; previous lesson not completed → locked with `LESSON_LOCKED`; unlocked with no
    attempt → `CURRENT` with the preview count and zero attempt rows written; the preview count matches
    what `start()` then actually creates; an open attempt's ref and its own item count; completed (no
    wrong answers) → `COMPLETED` status with no open attempt; authored `estimatedMinutes` used as-is;
    no authored value → the 45 s/question fallback.
  - `TheoryAttemptInternalControllerTest` (+4 new tests, 17/17 total): missing internal token → 403;
    unknown lesson → 404; locked → 200 with `locked: true` and the right `lockReason` (confirms the
    deviation above is what actually ships, not just what the service layer does); an open attempt's
    ref and question count round-trip through the controller.
  - No real test bugs this time — the P4.T7 fixtures (one unit/lesson/3-question-template, entitled by
    default) covered this task's scenarios without new seeding traps.
  - Full suite: `./gradlew test --no-daemon -q`, exit code 0.
- **Issues found / open risks:**
  - `levelDropAllowed` (P4.T6) still unwired — unrelated to this task, carried forward again.
  - The two deviations above are genuine, documented interpretations of a plan that is internally
    inconsistent for this one endpoint (§7.3 vs §7.4 on the 403 question; §7.3's own two sentences on
    what the engine supplies vs the full `estimatedMinutes` formula). Worth a one-line confirmation from
    whoever owns the plan before the BFF side is built against this contract, so the BFF doesn't get
    built expecting a 403 that will never come, or a complete `estimatedMinutes` the engine can't give.
- **Ready to continue:** YES.
- **Next task:** none queued in P4 — **P4 Phase exit** ("the full attempt flow passes in Testcontainers;
  no answer key appears in any pre-answer response; all concurrency tests pass") is the remaining
  checkbox before P5. All of its component pieces have passed in this session's tests across P4.T1–T8;
  worth a deliberate end-to-end pass over the tracker's P4 Phase exit checklist before calling P4 fully
  closed and starting P5.T1 (migrations: progress tables).

### 2026-11-03 · P4 Phase exit · Confirmation pass

- **Status:** DONE — ties off P4 ("phase done" + "P4 Phase exit" both ticked). No code changed.
- **Repo / branch / commit:** ENG · feat/theory-app-implementations · 7645531a (no new commit — this is
  a verification pass over work already committed through P4.T8).
- **What was checked, against the three Phase-exit criteria:**
  1. **"The full attempt flow passes in Testcontainers."** `AttemptServiceTest` is an
     `IntegrationTestBase` subclass (real Postgres via Testcontainers, not mocked), and
     `fullFlow_acceptance_eightQuestionsTwoWrong_retryPhaseOfFive_thenCompleted` (P4.T7) runs the
     tracker's own exact scenario end to end: start → 8 answers with 2 wrong → lesson-phase complete
     returns 5 retry items → 5 answers → retry-phase complete → `COMPLETED`. Passing.
  2. **"No answer key appears in any pre-answer response."** Checked at two levels, not just by test
     assertion:
     - **Structural guarantee:** `AttemptItemRefDTO` (the shape every pre-answer response — `start`,
       `get`, and a lesson-completion's `retry.items` — serializes through) has no
       `correctOptionKey`/`correctOption` field at all. It is not possible for this DTO to leak the
       answer key regardless of what the service passes it, which is a stronger guarantee than a
       string-absence test alone.
     - **Explicit regression test:** `startAttempt_validJwtAndInternalToken_returns200_andNeverLeaksCorrectOptionKey`
       additionally asserts the raw JSON body contains neither `correctOptionKey` nor
       `correct_option_key` in any casing, covering the controller/Jackson serialization layer the DTO
       shape alone doesn't (e.g. a stray field added elsewhere in the response envelope).
     - The one place the key legitimately appears — `AnswerFeedbackDTO`, returned only from the
       `answer()` endpoint *after* an item is answered — has its own test
       (`answer_validRequest_returns200_andNeverLeaksCorrectOptionKeyFieldName`) confirming the
       snake_case field name never appears even there, while the camelCase key itself is correctly
       present (it's post-answer feedback, not a pre-answer leak).
  3. **"All concurrency tests pass."** Two tests exercise real concurrent DB access (not mocked
     timing): `start_concurrentDoubleStart_createsExactlyOneAttempt` (P4.T4 — two threads racing
     `start()`, the unique-index/REQUIRES_NEW recovery path from Plan §6) and
     `concurrentDevicesCompletingTheSameLessonPhase_areSerialisedNotDoubled` (P4.T7 — two threads
     racing `completeLessonPhase()`, the `FOR UPDATE` serialization). Both pass.
  - Full suite re-run clean immediately before this entry: `./gradlew test --no-daemon -q`, exit code 0.
- **Deviations from the plan:** none — this is a verification pass, not new implementation. The two
  deviations logged under P4.T8 (locked → 200 not 403; `estimatedMinutes`'s partial fallback) stand as
  already recorded there and are not re-litigated here.
- **Issues found / open risks:** none new. Carried forward unresolved: `levelDropAllowed` (P4.T6)
  remains unwired, and the two P4.T8 deviations are still worth a one-line confirmation from whoever
  owns the plan before the BFF is built against this contract.
- **Ready to continue:** YES. P4 is fully closed.
- **Next task:** P5.T1 (migrations: progress tables) — depends on P4, which is now done. Plan §5.7, §6.

### 2026-11-03 · P5.T1 · Migrations: progress tables

- **Status:** DONE
- **Repo / branch / commit:** ENG · feat/theory-app-implementations · 07f151c9
- **What was done:**
  - `V1_0_19__theory_progress.sql` creates all four tables the tracker lists, matching Plan §6's ERD
    field-for-field: `lesson_progress` (PK `(app_user_id, lesson_id)`, `best_accuracy NUMERIC(5,4)`,
    nullable `open_attempt_id UUID REFERENCES lesson_attempt`, `updated_at`, plus the partial index
    `WHERE open_attempt_id IS NOT NULL` for home's Continue card), `learner_theory_summary` (PK
    `app_user_id`), `learner_activity_day` (PK `(app_user_id, local_date)`), and
    `learner_activity_lesson` (PK `(app_user_id, local_date, lesson_id)`).
  - `lesson_progress.lesson_id`/`unit_id` and `learner_activity_lesson.lesson_id` are real FKs to
    `content_lesson`/`content_unit`, matching how `lesson_attempt` (P4.T1) already references them.
  - CHECK constraints beyond what the plan's own table lists, added defensively in the same spirit as
    `lesson_attempt`'s counts check (P4.T1): `best_accuracy BETWEEN 0 AND 1`, non-negative counters,
    `last_lesson_correct`/`last_lesson_total` either both null or `correct <= total`, and
    `longest_streak >= current_streak`.
- **A genuine, deliberate omission — not an oversight:** the plan's ERD (the mermaid diagram) draws
  `LEARNER_THEORY_SUMMARY ||--o{ LEARNER_ACTIVITY_DAY` and `LEARNER_ACTIVITY_DAY ||--o{
  LEARNER_ACTIVITY_LESSON` as relationships, which would normally become FKs. Neither is implemented,
  for two independent reasons, both load-bearing:
  1. Plan §5.7's write-path step 3 is explicit about order: *"INSERT learner_activity_lesson … ON
     CONFLICT DO NOTHING. If a row was inserted, upsert `learner_activity_day`"* — the lesson-activity
     row is written **before** the day row. A FK from `learner_activity_lesson` to
     `learner_activity_day` would make that exact, specified sequence fail with a foreign-key violation
     on the very first write of a new day.
  2. Step 4 only ever **updates** `learner_theory_summary` — never upserts it — which only makes sense
     if the summary row is expected to already exist by the time any lesson completes (created some
     other way, not specified in this task's scope — P5.T3 presumably). A FK from either activity table
     to the summary would require the summary to exist first regardless, which the write path doesn't
     guarantee as written.
  Also: Plan §6's own "Constraints and indexes" table (the authoritative list, distinct from the
  illustrative ERD diagram) lists no FK for either relationship — only the PKs and the one partial
  index, which this migration implements exactly. Followed the explicit constraints table and the
  explicit write-order prose over the diagram's shorthand, and logged this rather than guessing past
  it, since it's exactly the kind of mismatch between a diagram and its own spec that's easy to "fix"
  wrongly in either direction.
- **Tests:** no dedicated migration test exists for any prior theory migration (V1_0_16/17/18), so this
  follows the same precedent: verified via the existing mechanism — every `IntegrationTestBase` subclass
  boots a real Spring context against Postgres, which runs Flyway on `engn_learning` and would fail
  context load on any migration syntax or constraint error. `FordonaEngineApplicationTests` (context
  load) and the full suite both passed clean: `./gradlew test --no-daemon -q`, exit code 0.
- **Deviations from the plan:** the two omitted FKs above, both logged as deliberate per-field
  decisions rather than deviations in behaviour — the resulting schema matches Plan §6's literal
  constraints table exactly.
- **Issues found / open risks:**
  - Nothing writes to these four tables yet — that's P5.T3 (ProgressService write path), which depends
    on P5.T2 (timezone handling) first. Whoever builds P5.T3 should confirm where/when
    `learner_theory_summary` rows get created, given step 4's "update, not upsert" implies some other
    creation path this task didn't need to resolve.
  - Carried forward, unrelated to this task: `levelDropAllowed` (P4.T6) still unwired; the two P4.T8
    deviations (locked → 200, partial `estimatedMinutes`) still worth a plan-owner confirmation.
- **Ready to continue:** YES.
- **Next task:** P5.T2 (timezone handling) — depends on P5.T1, which is now done. Plan §5.7.
