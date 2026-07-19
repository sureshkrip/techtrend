---
phase: 01-foundation-first-signal-github-scored-and-visible
plan: 05
subsystem: backfill
tags: [httpx, tenacity, sqlite, github-api, degradation]

# Dependency graph
requires:
  - phase: 01-03
    provides: "techtrend/collectors/http.py (build_client, is_retryable, MissingGithubTokenError), techtrend/pipeline/snapshot.py (write_snapshot with source_kind), techtrend/pipeline/orchestrator.py (record_stage), techtrend/db/schema.sql (backfilled_at/backfill_status columns), techtrend/config.py (load_config), tests/conftest.py"
provides:
  - "techtrend/collectors/backfill.py — sample_stargazer_history()/classify_backfill_failure(): fixed-stride reverse stargazer pagination bounded by backfill_request_cap, with permanent-vs-transient failure classification (BackfillBlocked raised on first response, no retry)"
  - "techtrend/pipeline/backfill_runner.py — run_backfill(): D-08 first-sight/retry trigger writing backfill-tagged snapshots and honest per-repo backfill_status bookkeeping, plus its own backfill:github run_manifest row"
  - "techtrend/ingest.py — both the live and --fixture paths now attempt backfill after snapshots are written, inside an exception guard that can never change the exit code or roll back observed data"
affects: [scoring-engine, dashboard, health-strip]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "BackfillBlocked (exception, raised on first response, no retry) vs BackfillTruncated (dataclass, returned normally, coarser curve) as two structurally distinct outcomes of the same function — the caller's except/isinstance split is the actual honesty mechanism"
    - "classify_backfill_failure() mirrors http.py's is_retryable() boundary but returns a string ('permanent'/'transient') rather than a bool, so the permanent branch can raise a dedicated exception instead of flowing into the shared retry predicate at all"
    - "Backfill's own tenacity retry decorator reuses http.py's is_retryable predicate exactly, but with a deliberately tightened wait schedule (multiplier=0.01 vs github.py's multiplier=2) — same classification boundary, faster tests, documented as a discretion choice, not a reused constant"
    - "run_backfill() never raises — every per-entity failure (transient error, blocked, or an unanchored entity with no observed stars snapshot yet) is caught and recorded as that entity's own status, so one bad repo can never take down the stage"

key-files:
  created:
    - techtrend/collectors/backfill.py
    - techtrend/pipeline/backfill_runner.py
    - tests/fixtures/github/stargazers_page.json
    - tests/fixtures/github/stargazers_403.json
    - tests/test_backfill.py
  modified:
    - techtrend/config.py
    - config/tracked.toml
    - techtrend/ingest.py

key-decisions:
  - "Task 1 checkpoint (Option A vs B vs C) was pre-approved by the user before this execution session per the orchestrator's instructions, consistent with the already-recorded D-08a decision in 01-CONTEXT.md. No re-ask occurred; proceeded directly to Task 2."
  - "Added a missing backfill_lookback_days config tunable (default 90, D-06) to techtrend/config.py and config/tracked.toml — the plan's action text required trimming points 'to lookback_days (default 90 per D-06, read from config)' but no such field existed yet in Tunables. Rule 2 (missing critical functionality): a hardcoded 90 would have violated CONTEXT.md's 'every tunable must be config, not a code constant' rule."
  - "Sampling algorithm (Claude's discretion per CONTEXT.md): fixed-stride reverse sample. Compute last_page = ceil(stars_total / 100); if last_page <= request_cap, fetch every page (untruncated, exactly the actual page count); otherwise walk exactly request_cap pages at a fixed stride from newest to oldest and return BackfillTruncated. Never exceeds the cap in either branch."
  - "BackfillTruncated is a dataclass subclass of BackfillOutcome, returned normally (not raised) — distinguishes 'ran to completion but the repo is too large to fully resolve within budget' (a data-shape signal the caller branches on) from BackfillBlocked, which is an exception because it is a hard stop with zero points gathered."
  - "run_backfill()'s own run_manifest stage status is 'success' whenever there were any candidates to sweep (regardless of how many ended up blocked/failed) and 'zero_items' when there was nothing to attempt. The honest measure of D-08a's degradation lives in item_count (completed count) and error_detail (blocked/failed/truncated/skipped breakdown), not in a stage-level failure — a stage that correctly identified and recorded 100% of its repos as blocked did not fail to run, it ran and told the truth."
  - "Both the live and --fixture ingest.py paths now invoke run_backfill after writing observed snapshots, since D-08 triggers on first sight regardless of collection method — the plan's own acceptance criteria explicitly exercises 'python -m techtrend.ingest --fixture' for the never-blocks-collection guarantee."
  - "The stargazer-pagination retry decorator (_STARGAZER_RETRY_KWARGS) reuses http.py's is_retryable predicate verbatim but uses a much faster wait schedule than github.py's live-collection retry — the classification boundary is what's load-bearing and shared; the exact backoff timing is not, and tightening it keeps the transient-retry unit test fast (~10ms instead of ~2s)."

requirements-completed: [DATA-02, DATA-05]

coverage:
  - id: D1
    description: "Sampled stargazer pagination bounded by a hard per-repo request cap, never exceeding it even when a repo needs far more pages than the budget allows (D-06)"
    requirement: "COLL-02"
    verification:
      - kind: unit
        ref: "tests/test_backfill.py::test_pagination_capped_and_returns_truncated_outcome"
        status: pass
      - kind: unit
        ref: "tests/test_backfill.py::test_successful_pagination_returns_ascending_sorted_unique_dates"
        status: pass
    human_judgment: false
  - id: D2
    description: "A permanent permission denial (403 without ratelimit-exhausted header, or 404) is classified as 'blocked' and raises BackfillBlocked on the very first response, with zero retries (D-08a, T-01-24)"
    requirement: "COLL-02"
    verification:
      - kind: unit
        ref: "tests/test_backfill.py::test_403_marks_blocked_not_retried"
        status: pass
      - kind: unit
        ref: "tests/test_backfill.py::test_404_marks_blocked_same_as_403"
        status: pass
    human_judgment: false
  - id: D3
    description: "A transient failure (403 with x-ratelimit-remaining:0, or 5xx) flows through the shared is_retryable predicate and is retried rather than misclassified as permanent"
    requirement: "COLL-02"
    verification:
      - kind: unit
        ref: "tests/test_backfill.py::test_403_with_ratelimit_remaining_zero_is_retried_then_succeeds"
        status: pass
    human_judgment: false
  - id: D4
    description: "Backfilled points are written through the same write_snapshot() used by observed collection, tagged source_kind='backfill', and a blocked outcome writes zero snapshot rows (D-07)"
    requirement: "DATA-02"
    verification:
      - kind: unit
        ref: "tests/test_backfill.py::test_successful_backfill_writes_backfill_snapshots_and_status_complete"
        status: pass
      - kind: unit
        ref: "tests/test_backfill.py::test_blocked_outcome_sets_status_blocked_and_writes_zero_snapshots"
        status: pass
    human_judgment: false
  - id: D5
    description: "Re-running backfill for the same entity does not duplicate snapshot rows — idempotent via the (entity_id, collected_at, metric_name) uniqueness constraint that write_snapshot() upserts against"
    requirement: "DATA-05"
    verification:
      - kind: unit
        ref: "tests/test_backfill.py::test_rerunning_backfill_does_not_duplicate_snapshot_rows"
        status: pass
    human_judgment: false
  - id: D6
    description: "D-08 retry set selection: pending/failed/truncated entities are attempted; complete/blocked entities are skipped every run"
    requirement: "COLL-02"
    verification:
      - kind: unit
        ref: "tests/test_backfill.py::test_pending_entity_attempted_complete_and_blocked_entities_skipped"
        status: pass
      - kind: unit
        ref: "tests/test_backfill.py::test_failed_and_truncated_entities_are_retried"
        status: pass
    human_judgment: false
  - id: D7
    description: "Backfill failure (per-entity or catastrophic, e.g. no auth token) never blocks or rolls back live collection, and the ingest exit code stays 0"
    requirement: "COLL-02"
    verification:
      - kind: unit
        ref: "tests/test_backfill.py::test_backfill_raising_for_every_entity_does_not_abort_or_lose_observed_snapshots"
        status: pass
      - kind: manual_procedural
        ref: "uv run python -m techtrend.ingest --fixture (no GITHUB_TOKEN) — stage=collect:github items=1, then stage=backfill:github status=failed error='GITHUB_TOKEN is not set...', exit code 0; SELECT DISTINCT source_kind FROM snapshots returned only 'observed'; the entity's backfill_status stayed 'pending' (never reached, correctly retryable next run)"
        status: pass
    human_judgment: true
    rationale: "The token-absent degradation path was verified directly against a real DB. The happy-path branch (a repo the operator owns actually returning real stargazer history, or a non-owned repo genuinely receiving GitHub's live 403) requires a real GITHUB_TOKEN, which is a user-owned secret not available to this execution session — same limitation 01-03's SUMMARY documented for live collection."
  - id: D8
    description: "The backfill:github run_manifest row honestly records completed/blocked/failed/truncated/skipped counts as the audit trail of D-08a's degraded outcome"
    requirement: "COLL-02"
    verification:
      - kind: unit
        ref: "tests/test_backfill.py::test_run_manifest_row_records_completed_blocked_failed_counts"
        status: pass
    human_judgment: false

duration: 55min
completed: 2026-07-19
status: complete
---

# Phase 01 Plan 05: Backfill — Sampled Stargazer Pagination with Honest Degradation Summary

**Sampled fixed-stride reverse stargazer pagination bounded by a hard per-repo request cap, with a GitHub permission denial recorded as a distinct, non-retried `blocked` status rather than a false success or a silent empty history — COLL-02/D-05/D-06 satisfied in degraded form only, per the pre-approved D-08a decision.**

## Task 1 Checkpoint: Pre-Approved

Task 1 was a `checkpoint:decision` presenting Option A (graceful degradation), Option B (GH Archive/BigQuery), and Option C (no backfill). Per the orchestrator's explicit instruction for this execution session, the user had **already been asked and had already chosen Option A**, consistent with the D-08a decision already recorded in `01-CONTEXT.md`. This was recorded as approved and execution proceeded directly to Task 2 with no re-ask.

**What Option A means, concretely, in what was built:** the collector attempts real sampled stargazer pagination exactly as D-05 specifies. It will succeed for repos the operator owns or collaborates on. For essentially every other tracked repo, GitHub's late-June/July-2026 restriction on the `stargazers`-with-`starred_at` endpoint returns 403, and this plan's entire purpose was to make that failure **visible and correctly classified** — recorded as `backfill_status = 'blocked'`, costing no further quota on future runs — rather than silently producing an empty history that would look like a bug.

## Performance

- **Duration:** ~55 min
- **Completed:** 2026-07-19
- **Tasks:** 3 (1 pre-approved checkpoint, 2 auto/tdd)
- **Files modified:** 8 (5 new, 3 modified)

## Accomplishments

- Built `techtrend/collectors/backfill.py`: `sample_stargazer_history()` walks stargazer pages backwards from the newest using a fixed-stride reverse sample, computing `last_page = ceil(stars_total / 100)` and never issuing more than `request_cap` requests — when `last_page` fits within the cap every page is fetched (untruncated); when it doesn't, exactly `request_cap` pages are sampled at a fixed stride and a `BackfillTruncated` (coarser curve) is returned instead of a plain `BackfillOutcome`
- `classify_backfill_failure()` draws the load-bearing permanent/transient line: a 403 *without* `x-ratelimit-remaining: 0`, and any 404, are permanent — `BackfillBlocked` is raised on the very first response with zero retries. A 403 *with* that header, and any 5xx, are transient and flow through the exact same `is_retryable` predicate `http.py` already established, retried via tenacity
- Built `techtrend/pipeline/backfill_runner.py`: `run_backfill()` selects the D-08 retry set (`pending`/`failed`/`truncated`), explicitly skips `complete` and `blocked` (retrying a permanent denial every run would burn quota on a request that can never succeed), writes every point through the existing `write_snapshot()` with `source_kind='backfill'`, and records honest per-repo `backfill_status`/`backfilled_at`. Never raises — a per-entity failure of any kind is caught, logged, and recorded as that entity's own `failed` status
- Wrote the stage's own `backfill:github` `run_manifest` row, carrying `item_count` (completed count) and an `error_detail` breaking down blocked/failed/truncated/skipped counts — this row is the audit trail of exactly how much of COLL-02 succeeded this run under the D-08a degradation, never a flat pass/fail bit
- Wired `techtrend/ingest.py` to call `run_backfill()` after snapshot-writing completes, in **both** the live and `--fixture` paths (D-08 triggers on first sight regardless of collection method), inside an exception guard (`_attempt_backfill`) that catches everything from a missing `GITHUB_TOKEN` to an unexpected exception inside `run_backfill()` itself, records a `failed` stage row, and never changes the ingest exit code or touches already-committed observed snapshots
- Filled `tests/test_backfill.py` with 13 tests (6 for Task 2's pagination/classification behavior via `httpx.MockTransport`, 7 for Task 3's runner behavior via a monkeypatched `sample_stargazer_history`) — all pass, no live network call anywhere
- Manually verified `uv run python -m techtrend.ingest --fixture` with no `GITHUB_TOKEN` present: collection writes the entity/observed-snapshot, backfill fails cleanly at client-build time, a `backfill:github` `run_manifest` row records the honest failure, `SELECT DISTINCT source_kind FROM snapshots` returns only `observed`, and the process exits 0

## Task Commits

1. **Task 2: Sampled stargazer pagination with a hard request cap** - `4f49bb1` (feat)
2. **Task 3: First-sight trigger, provenance-tagged snapshot writes, and honest status bookkeeping** - `c253cd6` (feat)

## Files Created/Modified

- `techtrend/collectors/backfill.py` - `sample_stargazer_history()`, `classify_backfill_failure()`, `BackfillOutcome`, `BackfillBlocked`, `BackfillTruncated`
- `techtrend/pipeline/backfill_runner.py` - `run_backfill()`: D-08 retry-set selection, snapshot writes with `source_kind='backfill'`, per-entity status bookkeeping, `backfill:github` `run_manifest` row
- `techtrend/config.py` - added `Tunables.backfill_lookback_days` (default 90, D-06); no field previously existed for this
- `config/tracked.toml` - documented `backfill_lookback_days = 90`
- `techtrend/ingest.py` - added `_attempt_backfill()` guard, invoked after snapshot writes in both the live and `--fixture` paths
- `tests/fixtures/github/stargazers_page.json` - realistic stargazer page (array of `starred_at` + nested `user`)
- `tests/fixtures/github/stargazers_403.json` - GitHub's permission-denial body shape
- `tests/test_backfill.py` - 13 tests across pagination/classification (Task 2) and the runner (Task 3)

## Decisions Made

See `key-decisions` in frontmatter for the full list. Highlights:
- Added the missing `backfill_lookback_days` config tunable (Rule 2 — the plan's own action text required it, but no such field existed in `Tunables` yet; a hardcoded `90` would have violated CONTEXT.md's config-not-constant rule)
- `BackfillTruncated` is a returned dataclass, `BackfillBlocked` is a raised exception — this asymmetry is deliberate and mirrors the two genuinely different situations (a coarser-but-real curve vs. zero data gathered)
- The backfill stage's own retry decorator reuses `http.py`'s `is_retryable` predicate exactly but with much faster backoff timing than `github.py`'s live-collection retry, to keep the transient-retry unit test fast without diverging on the classification logic that actually matters

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Added `backfill_lookback_days` config tunable**
- **Found during:** Task 2, implementing the `lookback_days` trim step
- **Issue:** The plan's action text says "Trim returned points to `lookback_days` (default 90 per D-06, read from config)" but `techtrend.config.Tunables` had no such field — only `backfill_request_cap` existed for backfill. Hardcoding `90` in `backfill.py` would have violated CONTEXT.md's explicit rule that every tunable must be config, not a code constant.
- **Fix:** Added `backfill_lookback_days: int = 90` to `Tunables` in `techtrend/config.py`, and documented it in `config/tracked.toml`
- **Files modified:** `techtrend/config.py`, `config/tracked.toml`
- **Verification:** `load_config().tunables.backfill_lookback_days == 90` by default; `run_backfill()` reads it via `config.tunables.backfill_lookback_days`
- **Committed in:** `4f49bb1` (Task 2)

**2. [Rule 1 - Bug] Fixed false-positive grep matches for the forbidden third-party literal**
- **Found during:** Task 2 acceptance-criteria self-verification
- **Issue:** `techtrend/collectors/backfill.py`'s module docstring and `BackfillOutcome`'s docstring both used the literal substring "star-history" while *explaining that no third-party star-history service is used* — breaking the acceptance criterion `grep -c 'star-history\|ossinsight\|bigquery' techtrend/collectors/backfill.py` returning `0`. Same class of bug documented in 01-02's and 01-03's SUMMARYs.
- **Fix:** Reworded both docstrings to describe the same guarantee ("no third-party star-timeline service", "sampled star-accrual curve") without the literal substring being grep-counted
- **Files modified:** `techtrend/collectors/backfill.py`
- **Verification:** `grep -c 'star-history\|ossinsight\|bigquery' techtrend/collectors/backfill.py` returns `0`; all 13 tests and `ruff check .` still pass
- **Committed in:** `4f49bb1` (Task 2)

---

**Total deviations:** 2 auto-fixed (1 Rule 2 missing-config-tunable, 1 Rule 1 docstring/grep bug)
**Impact on plan:** Both were required to satisfy the plan's own stated acceptance criteria. No scope creep, no design decision altered.

## Issues Encountered

None beyond the two auto-fixed items above. Executed alongside plan 01-04 running concurrently in the same working tree; only the files explicitly owned by this plan (`techtrend/collectors/backfill.py`, `techtrend/pipeline/backfill_runner.py`, `tests/test_backfill.py`, and the two new fixtures) plus the shared `techtrend/config.py`/`config/tracked.toml`/`techtrend/ingest.py` were touched, staged, and committed by explicit path — no `git add -A`/`git add .` was used, and `.planning/config.json` (modified by a concurrent process outside this plan's scope) was left untouched.

## COLL-02 / D-05 / D-06 Status: DEGRADED FORM ONLY

Per D-08a, this plan does **not** claim COLL-02, D-05, or D-06 as fully satisfied. What was built:

- **Repos the operator owns or collaborates on:** get real, genuine ~90-day star history via the D-05 mechanism exactly as specified.
- **Every other tracked repo (the overwhelming majority of the seed list):** GitHub's own platform restriction returns 403 on the very first stargazer-pagination request. That request is recorded as `backfill_status='blocked'`, costs exactly one request (never retried on subsequent runs, per T-01-24), and is honestly surfaced in the `backfill:github` `run_manifest` row's `error_detail` — never collapsed into `'complete'`, into a generic failure, or into silence.
- **Accepted consequence (per D-08a):** an entity with no backfill has `window_days=1` on day one and will almost always fall below the SCORE-03/D-10 window-gain floor, so it is honestly excluded from ranking rather than falsely ranked. The dashboard is expected to be sparse for roughly the first week until live observed snapshots accrue — this is intended behavior, not a defect, and no artifact in this plan claims otherwise.

## User Setup Required

A real `GITHUB_TOKEN` is required to exercise both halves of the live happy path: (1) a repo the operator owns actually returning real stargazer history, and (2) a non-owned repo genuinely receiving GitHub's live 403 (rather than the token-absent `MissingGithubTokenError` this session exercised). See `.env.example` (created in 01-01) for the variable name and required scope. Without it, both the live and `--fixture` `ingest.py` paths degrade cleanly: backfill fails at client-build time, is recorded as a `failed` `backfill:github` stage with a descriptive `error_detail`, and the process exits 0 with observed snapshots untouched — verified directly this session.

## Next Phase Readiness

- `techtrend/collectors/backfill.py` and `techtrend/pipeline/backfill_runner.py` are ready for a real `GITHUB_TOKEN` to exercise the full blocked/owned-repo split against live GitHub data.
- The `scores` table (01-04) can already read a uniform `snapshots` series with no special-casing — backfilled and observed points share the exact same table and columns, distinguished only by `source_kind`.
- No blockers. `uv run pytest -q` is green (full suite, 13 of which are this plan's) and `uv run ruff check .` is clean.

---
*Phase: 01-foundation-first-signal-github-scored-and-visible*
*Completed: 2026-07-19*

## Self-Check: PASSED

All 8 created/modified files found on disk; both task commits (`4f49bb1`, `c253cd6`) found in git log.
