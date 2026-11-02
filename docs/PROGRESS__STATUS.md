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
