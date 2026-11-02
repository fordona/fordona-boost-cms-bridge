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
