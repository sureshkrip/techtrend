---
phase: 02-cost-gated-llm-enrichment
plan: 04
subsystem: pipeline
tags: [sqlite, cost-gate, orchestration, anthropic, sha256-cache]

# Dependency graph
requires:
  - phase: 02-01
    provides: enrichments cache table, enrichment Tunables (enrichment_cap, grounding_char_cap, enrichment_model, confidence_flag_threshold), Wave 0 test contract for select_candidates/run_enrichment
  - phase: 02-02
    provides: "techtrend/pipeline/llm.py: build_llm_client, enrich_item(client, *, model, sections, description, readme_intro) -> EnrichmentResult | None"
  - phase: 02-03
    provides: "techtrend/pipeline/grounding.py: fetch_grounding(client, full_name, char_cap) -> tuple | None, normalize_for_hash"
provides:
  - "techtrend/pipeline/enrich.py: select_candidates(conn, score_version, cap), run_enrichment(conn, config, run_date, fetch_grounding_fn=, content_hash_fn=, llm_call_fn=), _content_hash, _cache_hit -- the cost gate, cap, cache-check, and per-candidate failure isolation"
  - "techtrend/enrich.py: standalone `python -m techtrend.enrich` entry point recording an 'enrich' run_manifest stage"
affects: [02-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Candidate-selection SQL mirrors query_ranked's eligible-set WHERE clause verbatim, with the hard per-run cap applied as a SQL LIMIT on the candidate SET itself -- before any grounding fetch, so a cache-hit-heavy run never fetches more than enrichment_cap entities"
    - "run_enrichment's fetch_grounding_fn/content_hash_fn/llm_call_fn injection seams: production builds real GitHub/Anthropic clients once up front (skipped entirely on a zero-candidate run); tests inject fakes with no live network call"
    - "Per-candidate try/except/continue mirrors run_collection's per-collector isolation -- one dead candidate is logged and skipped, never aborts run_enrichment, never drops the entity's ranked scores row"

key-files:
  created:
    - techtrend/pipeline/enrich.py
    - techtrend/enrich.py
  modified:
    - tests/test_enrich.py

key-decisions:
  - "select_candidates/run_enrichment implemented against the exact Wave 0 test contract fixed in 02-01-SUMMARY.md (injectable fetch_grounding_fn/content_hash_fn/llm_call_fn kwargs), not the plan's <action> prose which described building both clients unconditionally -- the committed tests/test_enrich.py is the authoritative contract"
  - "Both an LLM refusal (result is None) and a grounding fetch failure write the identical 'fetch_failed' tombstone shape (content_hash NULL) -- preserves the schema invariant 'content_hash is NULL only when status=fetch_failed' and lets the LLM be retried against the same content on the next run"
  - "Real GitHub/Anthropic clients are built lazily inside run_enrichment only when the injection seams are unset AND the candidate set is non-empty -- a zero-candidate run never requires GITHUB_TOKEN/ANTHROPIC_API_KEY to be configured"
  - "Each per-candidate write (tombstone or complete) commits immediately, mirroring run_collection's per-stage commit granularity, so a mid-run crash leaves already-enriched candidates durable"

patterns-established:
  - "Per-candidate cost-gate orchestration: SQL LIMIT on the candidate SET (not the LLM-call count) is the cap enforcement point for any future per-run LLM-cost-bounded stage"

requirements-completed: [ENR-01, ENR-02, ENR-05, ENR-06, DATA-04]

coverage:
  - id: D1
    description: "select_candidates returns only entities with scores.eligible=1 at CURRENT_SCORE_VERSION and the latest run_date -- the same eligible-set seam query_ranked reads; a stale-score-version or ineligible entity is never a candidate"
    requirement: "ENR-01"
    verification:
      - kind: unit
        ref: "tests/test_enrich.py::test_gate_reads_eligible_seam"
        status: pass
    human_judgment: false
  - id: D2
    description: "The hard per-run cap is applied as a SQL LIMIT on the candidate SET, velocity-first (wilson_lower_bound DESC, entities.id ASC tie-break) -- overflow entities are never fetched this run and stay first-in-line next run"
    requirement: "ENR-02"
    verification:
      - kind: unit
        ref: "tests/test_enrich.py::test_cap_limits_candidate_set"
        status: pass
    human_judgment: false
  - id: D3
    description: "A matching (entity_id, content_hash) status='complete' row skips the LLM call entirely (cache hit) -- unchanged content is never re-summarized"
    requirement: "DATA-04"
    verification:
      - kind: unit
        ref: "tests/test_enrich.py::test_cache_hit_skips_llm_call"
        status: pass
    human_judgment: false
  - id: D4
    description: "A None grounding fetch (both description and README unavailable) skips the LLM entirely and writes a status='fetch_failed' tombstone with content_hash NULL -- never fabricates a summary"
    requirement: "ENR-05"
    verification:
      - kind: unit
        ref: "tests/test_enrich.py::test_fetch_failure_skips_llm"
        status: pass
    human_judgment: false
  - id: D5
    description: "A per-candidate exception (fetch error, LLM error, refusal) is caught and logged; run_enrichment returns normally and still enriches the remaining candidates -- one dead item never aborts the run or drops a ranked row"
    requirement: "ENR-06"
    verification:
      - kind: unit
        ref: "tests/test_enrich.py::test_per_candidate_failure_does_not_abort_run"
        status: pass
    human_judgment: false
  - id: D6
    description: "python -m techtrend.enrich mirrors score.py's shape exactly: records a success/zero_items/failed enrich run_manifest row via the reused record_stage, exits 0 on success/zero_items, exits 1 only on an unhandled exception; a zero-candidate run needs no external credentials"
    verification:
      - kind: other
        ref: "manual run against a seeded empty DB (TECHTREND_DB=<tmp>.db python -m techtrend.enrich) -- exit 0, run_manifest row status=zero_items; injected run_enrichment exception -- exit 1, run_manifest row status=failed with error_detail"
        status: pass
    human_judgment: false

duration: 8min
completed: 2026-08-14
status: complete
---

# Phase 2 Plan 4: Cost Gate and Enrichment Orchestration Loop Summary

**`techtrend/pipeline/enrich.py`'s cost-gated orchestration loop (SQL-LIMIT cap on the candidate set, content-hash cache check, per-candidate failure isolation) plus the standalone `python -m techtrend.enrich` entry point mirroring `score.py`.**

## Performance

- **Duration:** 8 min
- **Completed:** 2026-08-14
- **Tasks:** 2
- **Files modified:** 3 (2 created, 1 test file extended)

## Accomplishments
- `select_candidates(conn, score_version, cap)`: reuses `query_ranked`'s exact eligible-set WHERE clause (`eligible=1 AND score_version=CURRENT AND run_date=MAX(...)`), ordered `wilson_lower_bound DESC, entities.id ASC`, capped via a bound `LIMIT :enrichment_cap` on the candidate SET itself -- overflow entities are never even fetched this run (ENR-01, ENR-02/D-05/A6).
- `run_enrichment(conn, config, run_date, fetch_grounding_fn=, content_hash_fn=, llm_call_fn=)`: per candidate, fetches grounding, skips the LLM on an empty fetch or a content-hash cache hit, calls the LLM on a genuine miss, and writes a `complete` row or a `fetch_failed` tombstone (content_hash NULL) -- never fabricating, never re-calling on unchanged content (ENR-05, DATA-04).
- Per-candidate `try/except/continue` mirrors `run_collection`'s per-collector isolation: one candidate's fetch/LLM/refusal failure is logged and skipped, never aborts the run and never removes the entity's ranked `scores` row (ENR-06/D-10) -- verified by a new test exercising two candidates where one's LLM call raises.
- `techtrend/enrich.py`: standalone `python -m techtrend.enrich` entry point, structurally identical to `score.py` -- `setup_logging -> load_config -> connect+init_db -> run_enrichment -> record_stage('enrich', success|zero_items|failed) -> commit -> return 0/1`. Verified live against a seeded empty DB (zero_items, exit 0, no credentials required) and an injected `run_enrichment` exception (failed, exit 1, `error_detail` recorded).

## Task Commits

Each task was committed atomically:

1. **Task 1: run_enrichment — gate, cap, grounding, cache, LLM, failure isolation** - `ad190fe` (feat) + `114b6e6` (fix)
2. **Task 2: techtrend/enrich.py standalone entry point** - `e4ce148` (feat)

**Plan metadata:** pending (docs: complete plan)

_Note: Task 1 required a follow-up fix commit -- see Deviations below._

## Files Created/Modified
- `techtrend/pipeline/enrich.py` - New: `select_candidates`, `_content_hash`, `_cache_hit`, `_write_tombstone`, `_write_complete`, `run_enrichment` (the cost gate + orchestration loop)
- `techtrend/enrich.py` - New: standalone `python -m techtrend.enrich` entry point, mirrors `score.py`
- `tests/test_enrich.py` - Extended with `test_per_candidate_failure_does_not_abort_run` (ENR-06/D-10)

## Decisions Made
- Implemented `select_candidates`/`run_enrichment` against the exact Wave 0 test contract already fixed and committed in `tests/test_enrich.py` (02-01) -- injectable `fetch_grounding_fn`/`content_hash_fn`/`llm_call_fn` kwargs -- rather than the plan's `<action>` prose, which described building both real clients unconditionally inside the loop. The committed test file is the authoritative, already-locked signature; the prose was directional guidance.
- An LLM refusal (`enrich_item` returns `None`) writes the identical `fetch_failed` tombstone shape as a grounding fetch failure (`content_hash` NULL), rather than persisting the already-computed content hash -- this preserves the schema's documented invariant ("content_hash is NULL only when status='fetch_failed'") and means the LLM is retried against the same content on the next run rather than permanently silently skipped.
- Real GitHub/Anthropic clients (`build_client()`/`build_llm_client()`) are constructed lazily inside `run_enrichment`, and only when the candidate set is non-empty -- a zero-candidate run (the common steady-state case once the eligible set is fully enriched) never requires `GITHUB_TOKEN`/`ANTHROPIC_API_KEY` to be configured, matching `score.py`'s "no external dependency unless actually needed" precedent.
- Each per-candidate write (`fetch_failed` tombstone or `complete` row) is followed by an immediate `conn.commit()`, mirroring `run_collection`'s per-collector-stage commit granularity -- a mid-run crash after N candidates leaves those N candidates' results durable rather than losing all progress for the run.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Added the per-candidate-failure-isolation test the acceptance criteria required**
- **Found during:** Task 1
- **Issue:** The plan's acceptance criteria for Task 1 explicitly requires "a test where enrich_item raises for one entity still returns and still enriches the others," but the fixed Wave 0 `tests/test_enrich.py` (committed in 02-01) only scaffolds the 4 tests listed in the task's `<behavior>` block (gate, cap, cache-hit, fetch-failure) -- no exception-isolation test existed.
- **Fix:** Added `test_per_candidate_failure_does_not_abort_run` (two eligible candidates, one entity's `llm_call_fn` raises) confirming `run_enrichment` returns normally, the failing entity has no enrichments row, and the healthy entity's row is written.
- **Files modified:** `tests/test_enrich.py`
- **Verification:** `pytest -q tests/test_enrich.py` -- all 5 tests pass.
- **Committed in:** `ad190fe` (Task 1 commit)

**2. [Rule 1 - Bug] Fixed unconditional real-client construction breaking the zero_items path**
- **Found during:** Task 2, while manually verifying `python -m techtrend.enrich`'s zero_items acceptance criterion
- **Issue:** `run_enrichment` built the real `build_client()`/`build_llm_client()` clients before the per-candidate loop unconditionally, even when `select_candidates` returned zero rows -- so a zero-eligible-entity run (the exact scenario the plan's Task 2 acceptance criteria exercises) would raise `MissingGithubTokenError`/`MissingAnthropicKeyError` on a machine with no credentials configured, instead of exiting cleanly with `zero_items`.
- **Fix:** Added an early `if not candidates: return 0` before any client construction.
- **Files modified:** `techtrend/pipeline/enrich.py`
- **Verification:** `pytest -q tests/test_enrich.py` unaffected (all fakes-injected paths); live run against a seeded empty DB with no `GITHUB_TOKEN`/`ANTHROPIC_API_KEY` set now exits 0 with a `zero_items` run_manifest row.
- **Committed in:** `114b6e6` (standalone fix commit)

---

**Total deviations:** 2 auto-fixed (1 missing critical functionality, 1 bug)
**Impact on plan:** Both auto-fixes directly required to satisfy the plan's own stated acceptance criteria (the exception-isolation test) and correctness (the zero_items path never touching external credentials). No scope creep.

## Issues Encountered
None.

## User Setup Required
None this plan -- `python -m techtrend.enrich` was verified end-to-end without requiring `GITHUB_TOKEN`/`ANTHROPIC_API_KEY` (the zero_items path only). A live enrichment run against real eligible entities still requires both env vars populated (deferred UAT, consistent with 01-03/01-05/02-02's precedent).

## Next Phase Readiness
- `techtrend/pipeline/enrich.py::run_enrichment` writes `enrichments` rows the dashboard's `query_ranked` LEFT JOIN (Plan 02-05) will read, keyed on `MAX(computed_at)` per entity.
- `pytest -q` full suite: green except the two pre-existing, out-of-scope Wave 0 RED tests for Plan 02-05 (`tests/test_dashboard.py::test_unenriched_item_still_renders`, `::test_section_filter`) -- unchanged by this plan, exactly the expected state per 02-01/02-03-SUMMARY.md.
- No blockers.

---
*Phase: 02-cost-gated-llm-enrichment*
*Completed: 2026-08-14*

## Self-Check: PASSED

Both created files (`techtrend/pipeline/enrich.py`, `techtrend/enrich.py`) verified present on disk; all 3 task commits (`ad190fe`, `114b6e6`, `e4ce148`) verified present in git history.
