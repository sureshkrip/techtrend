---
phase: 03-source-breadth-discourse-downloads-changelogs
plan: 01
subsystem: scoring
tags: [scoring, wilson-score, postgres, normalize]

# Dependency graph
requires:
  - phase: 01-foundation-first-signal-github-scored-and-visible
    provides: entities/snapshots/scores schema, Wilson-bounded score_entity/rescore_all, normalize.py's momentum_for_source converter seam
provides:
  - "score.py::compute_window_gain parameterized by metric_name (default 'stars', fully back-compatible)"
  - "normalize.py::PRIMARY_METRIC map + primary_metric_for_source(source) resolving each source's snapshots.metric_name"
  - "normalize.py identity converters for hn/npm/pypi/changelog (D-13: seam built, not calibrated)"
  - "regression test proving a non-'stars' source ranks (and does NOT rank if its metric is misfiled under 'stars')"
affects: [03-02, 03-03, 03-04, dashboard-labels-plan]

# Tech tracking
tech-stack:
  added: []
  patterns: ["per-source metric_name resolution colocated with the existing per-source momentum-converter seam in normalize.py"]

key-files:
  created: []
  modified:
    - techtrend/pipeline/normalize.py
    - techtrend/pipeline/score.py
    - tests/test_scoring.py

key-decisions:
  - "compute_window_gain's metric_name parameter defaults to 'stars' (keyword, not positional) so every pre-Phase-3 caller and test kept working unchanged with zero edits to call sites other than rescore_all"
  - "PRIMARY_METRIC and _CONVERTERS both fall back to 'stars'/identity for an unrecognized source, mirroring momentum_for_source's existing fallback-not-raise behavior"
  - "hn/npm/pypi/changelog converters are identity mappings per D-13 -- no cross-source calibration attempted; will be revisited once Wave-2 collectors produce real observed data"

requirements-completed: [COLL-03, COLL-04, COLL-05]

coverage:
  - id: D1
    description: "PRIMARY_METRIC map + primary_metric_for_source resolve each of github/hn/npm/pypi/changelog to its correct snapshots.metric_name, falling back to 'stars' for unknown sources"
    requirement: COLL-03
    verification:
      - kind: unit
        ref: "python -c metric-map assertion (Task 1 verify block)"
        status: pass
    human_judgment: false
  - id: D2
    description: "compute_window_gain reads whichever metric_name is bound in, and rescore_all resolves it per entity's source via primary_metric_for_source -- the Wilson math, floor-before-bound ordering, and momentum_for_source wiring are unchanged"
    requirement: COLL-04
    verification:
      - kind: unit
        ref: "tests/test_scoring.py -x (all 16 tests, including 14 pre-existing GitHub-path tests)"
        status: pass
    human_judgment: false
  - id: D3
    description: "A source='changelog' entity with a rising 'releases' snapshot series scores eligible=1 with wilson_lower_bound > 0 after rescore_all; the same series stored under 'stars' for that entity does NOT rank"
    requirement: COLL-05
    verification:
      - kind: unit
        ref: "tests/test_scoring.py::test_multi_source_non_stars_entity_ranks_after_rescore, tests/test_scoring.py::test_multi_source_entity_with_metric_stored_under_stars_does_not_rank"
        status: pass
    human_judgment: false

duration: 10min
completed: 2026-08-22
status: complete
---

# Phase 3 Plan 01: Source-Agnostic Scorer Metric Selection Summary

**Parameterized `score.py::compute_window_gain` by `metric_name` and added a `normalize.py::PRIMARY_METRIC` per-source lookup so non-GitHub entities (HN points, npm/PyPI downloads, changelog releases) score against their own metric instead of silently reading absent `'stars'` rows and staying `eligible=0` forever.**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-08-22T17:23:00-04:00 (approx, first commit)
- **Completed:** 2026-08-22T17:27:00-04:00
- **Tasks:** 3 completed
- **Files modified:** 3

## Accomplishments
- `normalize.py` now exposes `PRIMARY_METRIC: dict[str, str]` (github->stars, hn->points, npm/pypi->downloads, changelog->releases) and `primary_metric_for_source(source)`, plus one identity converter dataclass per new source (`HackerNewsMomentum`, `PackageDownloadsMomentum`, `ChangelogMomentum`) registered in `_CONVERTERS`
- `score.py::compute_window_gain` gained a `metric_name: str = "stars"` keyword parameter; the SQL `WHERE metric_name = 'stars'` literal was replaced with a bound `%s` parameter
- `score.py::rescore_all` resolves each entity's real metric via `primary_metric_for_source(entity["source"])` and passes it into `compute_window_gain`, closing the D3-5 touch #1 gap (RESEARCH Pitfall 2: non-GitHub entities silently scoring `eligible=0` forever)
- Added a positive/negative regression pair in `tests/test_scoring.py` proving a `source='changelog'` entity with a `'releases'` series ranks, and the identical series stored under `'stars'` for that same entity does NOT rank — proving the fix depends on per-source metric selection, not merely on snapshot rows existing
- Generalized `_insert_entity`/`_insert_snapshot`/`_seed_series` test helpers to accept `source` and `metric_name` parameters (previously hardcoded to `'github'`/`'stars'`)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add PRIMARY_METRIC lookup + per-source identity converters to normalize.py** - `516a7d8` (feat)
2. **Task 2: Parameterize compute_window_gain by metric_name and wire rescore_all per source** - `b5b9479` (feat)
3. **Task 3: Regression test — a non-'stars' source ranks after rescore_all** - `26177ea` (test)

_Note: Tasks 2 and 3 were tagged `tdd="true"` in the plan, but the plan's own structure sequenced implementation (Task 2) before the dedicated regression-test task (Task 3) rather than a strict per-task RED-then-GREEN split — each task still produced exactly one atomic, verified commit per the plan's own `<verify>`/`<done>` blocks._

## Files Created/Modified
- `techtrend/pipeline/normalize.py` - `PRIMARY_METRIC` map, `primary_metric_for_source()`, and `HackerNewsMomentum`/`PackageDownloadsMomentum`/`ChangelogMomentum` identity converters
- `techtrend/pipeline/score.py` - `compute_window_gain(..., metric_name="stars")`; `rescore_all` resolves and passes the per-source metric
- `tests/test_scoring.py` - generalized helpers + two new `multi_source` regression tests

## Decisions Made
- `metric_name` is a keyword-default parameter (not positional) on `compute_window_gain` so every existing call site (all of `score.py` plus every pre-existing test) needed zero edits — only `rescore_all`'s own call site was changed to pass it explicitly
- Converters for hn/npm/pypi/changelog stay pure identity mappings (D-13) — no attempt was made to weight or calibrate points/downloads/releases against stars; that is explicitly deferred until Wave-2 collectors produce real observed data
- `npm` and `pypi` share one `PackageDownloadsMomentum` class (both are raw downloads counts, same shape) rather than two near-duplicate classes

## Deviations from Plan

None - plan executed exactly as written. All three tasks matched their `<action>`/`<verify>`/`<done>` blocks; no Rule 1-4 fixes were needed.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The scorer-side half of D3-5's deviation surface (touch #1) is closed. The remaining two named D3-5 touches — dashboard label generalization (`queries.py`/`table.html`) and the unauthenticated HTTP client for the three new sources — are explicitly out of scope for this plan and belong to other plans in this phase.
- Wave-2 collectors (HN, npm/PyPI, changelog) can now write `snapshots` rows under their own `metric_name` (`points`/`downloads`/`releases`) and have `rescore_all` correctly pick them up — no further scorer changes are required to onboard those sources.
- Full project test suite (`pytest -q`, all files) passes green (exit code 0) after this plan's changes, confirming no regression outside the touched files.

---
*Phase: 03-source-breadth-discourse-downloads-changelogs*
*Completed: 2026-08-22*

## Self-Check: PASSED

All created/modified files confirmed present on disk; all three task commit hashes (516a7d8, b5b9479, 26177ea) confirmed present in `git log --oneline --all`.
