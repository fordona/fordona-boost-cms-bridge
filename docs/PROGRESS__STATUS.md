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
