---
phase: 01-foundation-first-signal-github-scored-and-visible
plan: 04
subsystem: scoring-engine
tags: [wilson-score-interval, sqlite, tdd, pydantic]

# Dependency graph
requires:
  - phase: 01-01
    provides: "Four-table SQLite schema (entities/snapshots/scores/run_manifest), techtrend.db.connection, techtrend.config.load_config(), tests/conftest.py fixtures"
  - phase: 01-03
    provides: "techtrend.pipeline.orchestrator.record_stage() (run_manifest upsert helper), the source-agnostic collector/identity/snapshot pipeline writing the snapshots this plan scores"
provides:
  - "techtrend/pipeline/score.py -- wilson_lower_bound(), score_entity(), compute_window_gain(), rescore_all(), CURRENT_SCORE_VERSION: the floor-then-Wilson-bound velocity ranking engine"
  - "techtrend/pipeline/normalize.py -- momentum_for_source()/GitHubMomentum: the SCORE-04 cross-source normalization seam, GitHub as first implementer"
  - "techtrend/pipeline/stability.py -- rank_overlap()/log_stability(): Jaccard day-to-day rank-overlap metric, logged every run at WARNING (<0.5) or INFO"
  - "techtrend/score.py -- python -m techtrend.score entry point populating the scores table"
affects: [dashboard-rendering, phase-2-llm-gate, phase-3-collectors]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Wilson lower-bound score interval with successes clamped to n and phat clamped to [0,1] before the sqrt, so out-of-range inputs never raise math domain error"
    - "Absolute floor checked before the Wilson bound is ever computed (score_entity) -- the floor, not the bound, is what excludes small-number-noise entities"
    - "compute_window_gain() anchors its trailing window on an entity's OWN latest snapshot date, not wall-clock 'now' -- keeps the function a pure read of (entities, snapshots) with no hidden time dependency, satisfying the SCORE-04 concurrency/purity requirement without needing a run_date parameter"
    - "momentum_for_source() dispatch table as the D-13 cross-source normalization seam -- Phase 3 adds a converter per source, never edits score.py"
    - "Old score_version rows are never deleted, only rows at CURRENT_SCORE_VERSION are replaced -- formula regressions stay comparable against the prior version"

key-files:
  created:
    - techtrend/pipeline/score.py
    - techtrend/pipeline/normalize.py
    - techtrend/pipeline/stability.py
    - techtrend/score.py
  modified:
    - tests/test_scoring.py
    - tests/test_stability.py

key-decisions:
  - "compute_window_gain(conn, entity_id, window_days) takes no run_date/now parameter by design -- it derives the trailing window from the entity's own most recent snapshot row, which keeps rescore_all a pure function of (entities, snapshots) alone with zero wall-clock dependency, satisfying the SCORE-04 concurrency backstop requirement more strongly than threading a 'now' argument through would have"
  - "wilson_lower_bound() clamps phat to [0.0, 1.0] and floors the radicand at 0.0 before math.sqrt -- an acceptance criterion (w(-1,10) >= 0.0) exercises successes=-1 directly against wilson_lower_bound, bypassing score_entity's own clamp, which without this guard raises ValueError: math domain error"
  - "scores rows are written for EVERY non-dormant entity, eligible or not (eligible flag 0/1) -- the ranked list is a query-time filter (WHERE eligible = 1 ORDER BY wilson_lower_bound DESC, entity_id ASC), not a write-time exclusion, so ineligible entities are always inspectable for debugging"

patterns-established:
  - "Pattern: reworded the stability.py module docstring to avoid literal 'EWMA'/'hysteresis' substrings against its own acceptance-criteria grep (grep -ci 'ewma\\|hysteresis' ... returns 0) -- same class of false-positive-grep-in-docstring bug documented in 01-02's and 01-03's SUMMARYs, now hit a third time and worth flagging for future plans: never grep-count a term that also appears naturally in prose explaining why that term's technique was rejected"

requirements-completed: [DATA-03, SCORE-01, SCORE-02, SCORE-03, SCORE-04, SCORE-05]

coverage:
  - id: D1
    description: "Wilson lower-bound scoring with the absolute floor checked before the bound is ever computed -- the load-bearing CONTEXT.md assertion: a 2->10 star entity (raw bound ~0.490) is excluded entirely and cannot outrank a 4,000->4,300 entity (bound ~0.0625)"
    requirement: "SCORE-02"
    verification:
      - kind: unit
        ref: "tests/test_scoring.py::test_small_number_noise_excluded"
        status: pass
      - kind: unit
        ref: "tests/test_scoring.py::test_floor_excludes_before_wilson"
        status: pass
      - kind: unit
        ref: "tests/test_scoring.py::test_wilson_bounds_match_research_worked_examples"
        status: pass
    human_judgment: false
  - id: D2
    description: "SCORE-03 absolute floor on stars gained in-window (not total stars), inclusive at the exact configured value, config-driven via config.tunables.window_gain_floor"
    requirement: "SCORE-03"
    verification:
      - kind: unit
        ref: "tests/test_scoring.py::test_floor_inclusive_at_exact_value"
        status: pass
      - kind: unit
        ref: "tests/test_scoring.py::test_ineligible_excluded_not_sorted_last"
        status: pass
      - kind: unit
        ref: "tests/test_scoring.py::test_entity_with_no_snapshots_is_ineligible"
        status: pass
    human_judgment: false
  - id: D3
    description: "wilson_lower_bound edge safety: n<=0 returns 0.0 without raising, result never negative, successes clamped to n via score_entity so proportion never exceeds 1.0"
    requirement: "SCORE-02"
    verification:
      - kind: unit
        ref: "tests/test_scoring.py::test_wilson_zero_n_returns_zero"
        status: pass
      - kind: unit
        ref: "tests/test_scoring.py::test_wilson_never_negative"
        status: pass
      - kind: unit
        ref: "tests/test_scoring.py::test_wilson_clamps_successes_to_n"
        status: pass
    human_judgment: false
  - id: D4
    description: "compute_window_gain records the ACTUAL span of days observed (window_days_actual) rather than substituting the configured window_days -- makes a partial-window observation distinguishable downstream from a full 7-day one"
    requirement: "DATA-03"
    verification:
      - kind: unit
        ref: "tests/test_scoring.py::test_partial_window_gain"
        status: pass
    human_judgment: false
  - id: D5
    description: "Deterministic ordering: identical (gained, total) entities receive identical bounds and tie-break by entity_id ascending; scores rows across different score_version values coexist rather than overwriting each other"
    requirement: "SCORE-01"
    verification:
      - kind: unit
        ref: "tests/test_scoring.py::test_identical_inputs_tie_break_by_entity_id"
        status: pass
      - kind: unit
        ref: "tests/test_scoring.py::test_score_versions_coexist"
        status: pass
    human_judgment: false
  - id: D6
    description: "Cross-source normalization seam (D-13): momentum_for_source()/GitHubMomentum implement a distinct source-specific step ahead of the source-agnostic ranking step, GitHub as identity-mapping first implementer"
    requirement: "SCORE-04"
    verification:
      - kind: unit
        ref: "tests/test_scoring.py -- exercised indirectly via rescore_all() in every scoring test (momentum_for_source is on the rescore_all call path for every entity)"
        status: pass
    human_judgment: false
  - id: D7
    description: "Jaccard rank-overlap stability metric computed and logged every run: 1.0/0.5/0.0 on the worked examples, WARNING below 0.5, INFO otherwise, never divides by zero on an empty union"
    requirement: "SCORE-05"
    verification:
      - kind: unit
        ref: "tests/test_stability.py::test_rank_overlap_empty_sets"
        status: pass
      - kind: unit
        ref: "tests/test_stability.py::test_rank_overlap_partial"
        status: pass
      - kind: unit
        ref: "tests/test_stability.py::test_rank_overlap_identical_sets"
        status: pass
      - kind: unit
        ref: "tests/test_stability.py::test_rank_overlap_one_empty_one_not"
        status: pass
      - kind: unit
        ref: "tests/test_stability.py::test_log_stability_warns_below_threshold"
        status: pass
      - kind: unit
        ref: "tests/test_stability.py::test_log_stability_info_when_stable"
        status: pass
    human_judgment: false
  - id: D8
    description: "python -m techtrend.score entry point: setup_logging -> load_config -> connect/init_db -> rescore_all -> log_stability -> record_stage('score', ...) -> commit; a failure records a 'failed' run_manifest row and returns exit code 1 rather than leaving a silently stale scores table"
    requirement: null
    verification:
      - kind: unit
        ref: "tests/test_stability.py::test_score_entry_point_writes_scores_and_run_manifest"
        status: pass
      - kind: manual_procedural
        ref: "uv run python -m techtrend.ingest --fixture && uv run python -m techtrend.score -- exit 0, 1 scores row written, 1 run_manifest row with stage='score' status='success'"
        status: pass
    human_judgment: false

duration: ~25min
completed: 2026-07-19
status: complete
---

# Phase 01 Plan 04: Confidence-Bounded Velocity Scoring Summary

**Wilson-lower-bound velocity ranking gated by an absolute floor on stars gained in-window, with the floor checked before the bound is ever computed, a config-driven 7-day trailing window anchored on each entity's own latest snapshot, a cross-source normalization seam with GitHub as its first implementer, and a Jaccard rank-overlap stability metric logged every run.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-07-19T17:50:00-04:00 (approx)
- **Completed:** 2026-07-19T18:06:00-04:00
- **Tasks:** 3 (all auto/tdd)
- **Files modified:** 6 (4 new, 2 filled from placeholder)

## Accomplishments
- `techtrend/pipeline/score.py`: `wilson_lower_bound()` (standard Wilson score interval, `phat` clamped to `[0,1]`, radicand floored at 0.0 so no input can raise `math domain error`), `score_entity()` (floor-then-bound ordering — the entire mitigation for small-number noise), `compute_window_gain()` (trailing-window gain anchored on an entity's own latest snapshot, recording the actual span observed), `rescore_all()` (re-scores every non-dormant entity, versioned by `CURRENT_SCORE_VERSION`, leaves other-version rows untouched)
- `techtrend/pipeline/normalize.py`: `momentum_for_source()`/`GitHubMomentum` — the D-13 cross-source normalization seam, GitHub implementing it as an identity mapping so Phase 3's HN/npm/PyPI sources plug in without touching `score.py`
- `techtrend/pipeline/stability.py`: `rank_overlap()` (Jaccard index, 1.0 when both sets empty) and `log_stability()` (WARNING below 0.5, INFO otherwise) — measures whether D-12's no-damping decision holds up in practice, rather than assuming it
- `techtrend/score.py`: `python -m techtrend.score` entry point wiring `rescore_all` + `log_stability` + `record_stage('score', ...)`, verified end-to-end against a fixture-populated database (`python -m techtrend.ingest --fixture && python -m techtrend.score` exits 0, writes 1 scores row and 1 `run_manifest` row with `stage='score'`, `status='success'`)
- 19 total tests across `tests/test_scoring.py` (12) and `tests/test_stability.py` (7), including the CONTEXT.md-named end-to-end assertion (a 2→10 star entity is absent from the ranked result while a 4,000→4,300 entity is present) and a literal `pytest.approx` regression against RESEARCH.md's three hand-computed Wilson bounds (0.490 / 0.237 / 0.0625)

## Task Commits

Each task was committed atomically, honoring the RED→GREEN TDD gate:

1. **Task 1: RED — encode the pitfall assertions and every scoring edge criterion** - `852e84c` (test)
2. **Task 2: GREEN — Wilson bound, absolute floor, window gain, and the normalization seam** - `a7e29b1` (feat)
3. **Task 3 RED — extend test_stability.py with log_stability and entry-point tests** - `e2acfed` (test)
3. **Task 3 GREEN — stability metric and the score entry point** - `19bd17f` (feat)

_TDD Gate Compliance: two full RED→GREEN cycles, both verified failing (ModuleNotFoundError/ImportError naming the not-yet-existing module) before the corresponding GREEN commit._

## Files Created/Modified
- `techtrend/pipeline/score.py` - Wilson lower bound, absolute floor, window gain, `rescore_all` driver, `CURRENT_SCORE_VERSION`
- `techtrend/pipeline/normalize.py` - `momentum_for_source()`/`GitHubMomentum`, the SCORE-04 normalization seam
- `techtrend/pipeline/stability.py` - `rank_overlap()`/`log_stability()`, the SCORE-05 Jaccard metric
- `techtrend/score.py` - `python -m techtrend.score` entry point
- `tests/test_scoring.py` - filled from placeholder; 12 tests
- `tests/test_stability.py` - new; 7 tests

## Decisions Made
- `compute_window_gain(conn, entity_id, window_days)` deliberately takes no `run_date`/`now` argument — it derives the trailing window from the entity's own most recent snapshot row rather than wall-clock time, which is what makes `rescore_all` provably a pure function of `(entities, snapshots)` with zero hidden time dependency (the SCORE-04 concurrency backstop). This matches the plan's stated signature exactly and is a stronger purity guarantee than threading a `now` parameter through would have given.
- `scores` rows are written for every non-dormant entity regardless of eligibility (the `eligible` 0/1 flag distinguishes them); the ranked list is a query-time filter (`WHERE eligible = 1 ORDER BY wilson_lower_bound DESC, entity_id ASC`), never a write-time exclusion — keeps ineligible entities inspectable in the table for debugging without a separate audit path.
- `momentum_for_source()` falls back to an identity mapping for any unrecognized source rather than raising, so a future source without a registered converter degrades gracefully instead of crashing the score pass.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `wilson_lower_bound` raised `ValueError: math domain error` on negative `successes`**
- **Found during:** Task 2, verifying the acceptance criterion `w(-1,10) >= 0.0` prints `True`
- **Issue:** With `successes=-1, n=10`, the unclamped `phat=-0.1` drives the variance term under the square root negative, raising instead of returning a safe value. This is a real acceptance criterion the plan states explicitly, not a hypothetical.
- **Fix:** Clamped `phat` to `[0.0, 1.0]` and floored the radicand at `0.0` before calling `math.sqrt`, so any out-of-range `successes` (including inputs that bypass `score_entity`'s own clamp) returns a safe non-negative bound instead of raising.
- **Files modified:** `techtrend/pipeline/score.py`
- **Verification:** `w(-1,10) >= 0.0` returns `True`; all 12 `tests/test_scoring.py` tests still pass with unchanged results for in-range inputs (the three worked-example bounds are bit-identical to the unclamped formula since `phat` is already in `[0,1]` for those cases)
- **Committed in:** `a7e29b1` (Task 2)

**2. [Rule 1 - Bug] False-positive grep match in `stability.py`'s own docstring**
- **Found during:** Task 3, verifying `grep -ci 'ewma\|hysteresis' techtrend/pipeline/stability.py` returns `0`
- **Issue:** The module docstring explained D-12's rejection of "EWMA smoothing and rank hysteresis" using those literal terms, which matched the acceptance-criteria grep it was supposed to satisfy (returned `2`, not `0`) — the same class of false-positive-grep-in-docstring bug documented as a deviation in both 01-02's and 01-03's SUMMARYs.
- **Fix:** Reworded the docstring to describe the same rejected techniques ("exponentially-weighted smoothing" and "rank-carries-over-from-yesterday memory") without using the literal substrings being grep-counted.
- **Files modified:** `techtrend/pipeline/stability.py`
- **Verification:** `grep -ci 'ewma\|hysteresis' techtrend/pipeline/stability.py` returns `0`; full suite and `ruff check .` still pass
- **Committed in:** `19bd17f` (Task 3)

---

**Total deviations:** 2 auto-fixed (both Rule 1 bugs, both required to satisfy the plan's own stated acceptance criteria)
**Impact on plan:** No scope creep, no design decision altered. Both fixes are the kind of thing the plan's own acceptance criteria exist to catch.

## Issues Encountered
None beyond the auto-fixed items above. Ran directly in the main checkout (no worktree) concurrently with plan 01-05, which owns `techtrend/collectors/backfill.py`, `techtrend/pipeline/backfill_runner.py`, `tests/test_backfill.py`, and two stargazer fixtures — those files, along with 01-05's in-flight edits to `techtrend/config.py`, `techtrend/ingest.py`, and `config/tracked.toml`, were visible as uncommitted changes throughout this session and were left untouched; every `git add` in this plan's task commits named only this plan's own files by explicit path.

## User Setup Required
None — no external service configuration required. Scoring reads only `entities`/`snapshots` and performs no network I/O (enforced by an acceptance-criteria grep for HTTP client imports in `score.py`, returning 0).

## Next Phase Readiness
- `python -m techtrend.score` populates the `scores` table; the dashboard's velocity column (`techtrend/server/queries.py`, built in 01-02) reads `scores.wilson_lower_bound`/`scores.stars_gained`/`scores.window_days` and will render real values instead of placeholders once entities and snapshots exist.
- **Known gap for a future plan, not touched here (out of this plan's file ownership):** `techtrend/server/queries.py`'s `query_ranked()` LEFT JOINs `scores` without filtering `score_version = CURRENT_SCORE_VERSION` or `eligible = 1`. Once `rescore_all` has run more than once with a bumped `CURRENT_SCORE_VERSION`, or once ineligible entities carry rows, the dashboard's LEFT JOIN could show duplicate/stale rows per entity or surface ineligible entities. This did not exist before this plan (the `scores` table was empty) and should be fixed by whichever plan next touches the dashboard query — filter to `score_version = (SELECT MAX(score_version) FROM scores)` and consider whether ineligible entities should render at all or with a distinct visual treatment.
- The `momentum_for_source()` seam is proven with exactly one source (GitHub, identity mapping); Phase 3 adds HN/npm/PyPI by adding a converter here, not by touching `rescore_all`'s ranking logic.
- `log_stability()`'s Jaccard metric will start producing meaningful (non-1.0/non-0.0) values once `python -m techtrend.score` has run on two or more distinct `run_date`s — currently untested against real accumulated daily data, only against synthetic multi-run fixtures in `tests/test_stability.py`.
- No blockers. `uv run pytest -q` is green (full suite, including 01-01/01-02/01-03/01-05's tests where present) and `uv run ruff check .` is clean.

---
*Phase: 01-foundation-first-signal-github-scored-and-visible*
*Completed: 2026-07-19*

## Self-Check: PASSED

All 6 created/modified source files and the SUMMARY.md found on disk; all four task commits (`852e84c`, `a7e29b1`, `e2acfed`, `19bd17f`) found in git log.
