# Learning service migration: fordona-engine → fordona-connect

Status: **in progress** on branch `feat/learning-service` (started 2026-11-09).
This file is the plan and tracker for the move. It overrides the parts of
`fordona-theory-first-shipment-architecture.md` and `BFF_IMPLEMENTATION_PROGRESS.md` that say
fordona-connect "never holds learner state, grades, chooses questions or sees an answer key".

## Decision

The learning domain moves out of fordona-engine into fordona-connect, in Python, so the AI features
can live next to the learning logic.

| Service | Owns |
|---|---|
| **fordona-connect** (learning service) | Boost content (the only Boost caller), question selection, attempts, **grading**, retry phase, progress, streaks, readiness, home, learning path, mock exams, learning journeys, AI |
| **fordona-engine** (platform) | Users and identity, timezone/locale, subscriptions, payments and the entitlement *source*, schools, staff, driving lessons, notifications, chat |

### Dependency rule

```
fordona-connect ──GET──▶ fordona-engine      synchronous, only this direction
fordona-connect ◀─events─ fordona-engine      the engine never calls fordona-connect
```

- Events use an **outbox the engine writes and fordona-connect pulls**
  (`GET /internal/events?after={cursor}`): at-least-once, consumers idempotent, events carry ids
  only. Initial events: `subscription.changed`, `user.updated`, `user.deleted`.
- If the platform later needs learning facts (notifications, instructor views), fordona-connect
  POSTs narrow facts to the engine. The engine never GETs from fordona-connect.
- Entitlement and learner context are cached briefly; engine unreachable and nothing cached means
  **deny** paid content (fail closed).

### Answer keys

Answer keys and explanations now live in fordona-connect, in the content store only. They are
never part of a public schema; leak tests assert no public response can carry them.

### Content sync (simpler than the engine's)

Published Boost revisions are immutable, so:

1. **Current versions**: list endpoints give the current `(id, version)` of every module, lesson,
   question, mock exam and journey. Refreshed on a poll (and later a Boost publish webhook).
2. **Revisions are fetched once**: a question's grading revision is fetched only when its
   `(id, version)` is not stored yet, then kept forever.
3. A daily full resync stays as a safety net.

The engine's version fetched every grading revision every 30 s; that is not ported.

## Phases

Each phase ends green (pytest, ruff, mypy) and is committed on its own.

- [x] **L1 Content layer** (2026-11-09): content tables (migration 0004), Boost client additions
  (grading revisions with their own credential, mock exams, learning journeys), sync service with
  fetch-once answer keys, question/lesson validation, background runner with an advisory lock.
  Code: `learning/content/`. Off by default (`CONTENT_SYNC_INTERVAL_SECONDS=0`).
  Deviations from the engine, on purpose:
  - Content Boost stops publishing is handled: units/lessons `HIDDEN`, questions `EXCLUDED`
    (`REMOVED`), mock exams/journeys and memberships deleted. The engine kept them forever.
  - A question counts as present in a locale only if it has a translation there, not just a row.
  - Membership rows (journey/mock exam → question/lesson) carry no foreign key: one unknown id
    from Boost must not fail the whole sync.
  - No templates, no topic-vocabulary check (both gone from Boost), no neighbour table yet (L3).
  - The in-memory content snapshot moves to L2, next to its first reader.
- [x] **L2 Selection and attempts** (2026-11-09): attempt tables + mistake ledger + retry policy
  table with its GLOBAL seed (migration 0005), in-memory content snapshot, unlock rules,
  entitlement (subscribed, or the first unit), selectors (`lesson-bank-v1` default, `challenge-v1`),
  and `AttemptService`: start (idempotent per request id, resumes the open attempt, recovers a
  concurrent double start), read, lesson state, answer + grading (replay-safe, conflicts,
  mistake ledger). Code: `learning/attempts/`, `learning/{selection,unlock,entitlement,errors}.py`,
  `learning/content/snapshot.py`, `learning/retry/policy.py`.
  - Learners are keyed by their **Kinde subject** (`learner_id`), not the engine's numeric user id.
  - Responses reuse the `Engine*` models, so L7 swaps the engine client for this service.
  - Subscription status comes through `SubscriptionSource` (implemented against the engine in L6).
  - Progress side effects go through `ProgressRecorder` (no-op until L4).
  - No templates (`TEMPLATE` item source and `fixed-v1` selector are gone with Boost's templates).
  - A correct answer in the retry phase resolves a mistake as `REPEAT` (the engine never got there).
- [x] **L3 Retry phase** (2026-11-09): metadata neighbours (top 20, rebuilt by the sync after
  every release), retry composer (REPEAT + SIMILAR with the engine's six filters), lesson and retry
  phase completion under an exclusive lock, idempotent on replay. `retry_enabled: false` now
  completes the attempt directly (the engine ignored that key).
- [x] **L4 Progress and screens** (2026-11-09): migration 0006 (`question_neighbour`,
  `lesson_progress`, `learner_summary`, `learner_activity_day/lesson`), progress recorder
  (timezone-aware streaks, daily activity, best accuracy), home, learning path (+ ETag), readiness,
  completion `next`/`progress` (computed after the completion commits), mock exam catalogue.
  The learner's name comes through `ProfileSource` (engine-backed in L6).
- [x] **L5 Mock exams and learning journeys** (2026-11-09): mock exam catalogue (L4). The 11
  journey endpoints now read content from Boost (`learning_journey/boost_content.py`: structure from
  the synced journey tables, answer keys from the snapshot, question text/options from the body
  cache) through `JourneyContentSource`. The mock seed and its seven tables are gone (migration
  0002 is now a no-op, 0003 lost its content foreign keys); the seed JSON survives only as a test
  fixture. The free tier is the journey's first milestone; the journey is the first published one.
- [x] **L6 Platform client** (2026-11-09): `learning/platform.py`. `PlatformClient` reads
  `GET /internal/learning/v1/learners/{kindeSubject}` (internal token only), caches it in Redis,
  fails closed. `PlatformEventConsumer` pulls `GET /internal/learning/v1/events?after=` with the
  cursor in `platform_event_cursor` (migration 0007), behind an advisory lock;
  `subscription.changed`/`user.updated` clear the cache, `user.deleted` deletes learning data.
- [x] **L7 Switch the public routes** (2026-11-09): `THEORY_BACKEND=local` (default) serves the
  theory routes from `learning/backend.py`, a drop-in for the engine theory client; `engine` keeps
  the legacy path for the mapping tests and a rollback. Journeys use Boost content and the
  platform client. **Not yet ported**: the engine's admin endpoints (manual sync trigger, content
  report, retry-policy edits); the sync runs on its timer and policies are rows in `retry_policy`.
- [x] **L8 Engine side** (2026-11-09, fordona-engine branch `feat/learning-platform-api`):
  `learn/connect` with `GET /internal/learning/v1/learners/{kindeSubject}` and
  `GET /internal/learning/v1/events?after=&limit=`, authenticated by the internal token alone
  (`InternalTokenFilter`, renamed from `TheoryInternalTokenFilter`, now guarding all `/internal/`).
  Outbox `learning_outbox_event` (V1_0_25), written by `LearningEventRecorder` on subscription
  activation and on account erasure. `learn/theory`, the theory admin controller, both sync jobs,
  the theory caches, error codes and config are removed; V1_0_26 drops the Boost-era tables.
  `user.updated` is defined but not emitted yet (names change rarely; the 60 s cache covers it).

## Rollout

1. Deploy fordona-engine first (new endpoints are additive; theory removal only matters once
   fordona-connect no longer calls `/internal/theory/**`, which `THEORY_BACKEND=local` ensures).
2. Deploy fordona-connect with `BOOST_GRADING_TOKEN`, `CONTENT_SYNC_INTERVAL_SECONDS` (e.g. 60),
   `PLATFORM_EVENTS_INTERVAL_SECONDS` (e.g. 5) and `THEORY_BACKEND=local`. The first sync fills the
   content tables; until then lessons are empty.
3. Learner history in the engine's old theory tables is not migrated (pre-launch: test data only).

## Source mapping (engine → connect)

| Engine (`learn/theory`) | fordona-connect |
|---|---|
| `client/Boost*`, `ContentSyncService`, `TheoryContentSyncScheduler` | `learning/content/` (client additions in `clients/boost/`) |
| `Content*` tables (V1_0_16/21/22/24), `TheoryContentStore*`, `ContentSnapshot*`, validators | `learning/content/` |
| selectors, `PinnedRevisionLoader` | `learning/selection/` (L2) |
| `AttemptService`, attempt tables (V1_0_17/20/23) | `learning/attempts/` (L2) |
| `RetryComposer`, `Neighbour*`, `similarity/*`, `RetryPolicy*` (V1_0_18) | `learning/retry/` (L3) |
| `Progress*`, `StreakResolver`, `UnlockService`, `Home*`, `LearningPath*`, `Readiness*` (V1_0_19) | `learning/progress/` (L4) |
| `MockExamTheoryService` | `learning/mock_exams/` (L5) |

The Java implementation and its tests are the behavioural spec for each phase.
