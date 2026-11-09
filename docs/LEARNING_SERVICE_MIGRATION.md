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
- [ ] **L2 Selection and attempts**: question-set selectors (lesson bank, fixed template,
  challenge), attempt start/resume/read, answer + grading, idempotency, attempt tables.
- [ ] **L3 Retry phase**: neighbour builder (metadata similarity), retry composer, retry policy
  (table, validator, resolver), phase completion.
- [ ] **L4 Progress and screens**: progress tables, streaks (timezone-aware), unlocks, home,
  learning path (+ ETag), readiness, completion `next`/`progress`.
- [ ] **L5 Mock exams and learning journeys**: mock exam flow on the shared attempt model;
  journeys (assignment, per-challenge progress, remediation) on the same foundation, replacing the
  mock Learning Journey module and its seed.
- [ ] **L6 Platform client**: engine GETs for learner context and entitlement (replacing the
  current engine client calls), event pull loop with cursor.
- [ ] **L7 Switch the public routes** to the local services; remove the old engine theory client
  calls; admin endpoints (sync now, content report, retry policy).
- [ ] **L8 Engine side** (fordona-engine, own branch): learner-context + entitlement endpoint,
  outbox + `/internal/events`; then delete `learn/theory`, `learn/platform` theory admin, and the
  sync job.

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
