---
phase: 02-cost-gated-llm-enrichment
plan: 01
subsystem: database
tags: [sqlite, pydantic, pytest, anthropic, tdd-scaffold]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: entities/scores/run_manifest schema, query_ranked's eligible-set seam, Tunables/Config pattern, GitHubCollector's optional-client injection pattern
provides:
  - enrichments cache table (composite UNIQUE(entity_id, content_hash) key, MAX(computed_at) join index)
  - four enrichment Tunables (enrichment_cap, grounding_char_cap, enrichment_model, confidence_flag_threshold)
  - seven-section taxonomy in config (SectionDef + Config.sections, config/tracked.toml [[sections]])
  - Wave 0 failing test scaffolds locking the contract for techtrend.pipeline.grounding/llm/enrich and query_ranked's section param
affects: [02-02, 02-03, 02-04, 02-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Composite-key (entity_id, content_hash) cache table with MAX(computed_at) correlated-subquery 'current row' join, matching the codebase's existing scores/MAX(run_date) idiom"
    - "Wave 0 RED test scaffolds with imports inside function bodies (not module-level) so pytest --collect-only succeeds while running the tests still fails against not-yet-implemented modules"
    - "Fake-client dependency injection for LLM tests (mirrors GitHubCollector.__init__(config=None, client=None))"

key-files:
  created:
    - tests/test_grounding.py
    - tests/test_llm.py
    - tests/test_enrich.py
    - tests/fixtures/github/readme_with_badges.md
    - tests/fixtures/anthropic/enrichment_success.json
    - tests/fixtures/anthropic/enrichment_refusal.json
  modified:
    - techtrend/db/schema.sql
    - techtrend/config.py
    - config/tracked.toml
    - tests/test_dashboard.py
    - tests/test_storage.py

key-decisions:
  - "enrichments uses a composite (entity_id, content_hash) UNIQUE key (append-only, MAX(computed_at)-joined for 'current row'), not upsert-in-place, matching A5's recommendation and the codebase's existing scores/MAX(run_date) idiom"
  - "Section taxonomy lands in config/tracked.toml as [[sections]], extending the existing Config model rather than a separate config file (A4)"
  - "Wave 0 test contract for techtrend.pipeline.enrich: select_candidates(conn, score_version, cap) as a pure query function, run_enrichment(conn, config, run_date, fetch_grounding_fn=, content_hash_fn=, llm_call_fn=) as the injectable orchestration loop -- downstream plans (02-02..02-05) implement against this signature"
  - "Wave 0 test contract for techtrend.pipeline.llm: enrich_item(client, *, model, sections, description, readme_intro) -> EnrichmentResult | None, plus build_section_result_model(section_ids) exposed publicly so the per-request section-enum enforcement is unit-testable without a live call"

patterns-established:
  - "Forward-only CREATE TABLE IF NOT EXISTS migrations with one inline decision-id comment per column, appended to schema.sql without touching db/connection.py"
  - "Every new Tunables field carries an inline '# purpose (D-XX)' comment -- no enrichment number lives as a code constant"

requirements-completed: [DATA-04, ENR-02]

coverage:
  - id: D1
    description: "Wave 0 failing test scaffolds (test_grounding.py, test_llm.py, test_enrich.py) plus extended test_dashboard.py (test_unenriched_item_still_renders, test_section_filter) and fixtures -- collectible, and failing only against not-yet-implemented modules/columns"
    verification:
      - kind: other
        ref: "pytest -q tests/test_grounding.py tests/test_llm.py tests/test_enrich.py tests/test_dashboard.py --collect-only"
        status: pass
      - kind: unit
        ref: "pytest -q (full suite) -- confirms only the 2 dashboard scaffolds + the grounding/llm/enrich Wave 0 tests fail (ModuleNotFoundError / intentional RED), zero pre-existing regressions"
        status: pass
    human_judgment: false
  - id: D2
    description: "enrichments cache table created idempotently by init_db() with the exact ten-column set and UNIQUE(entity_id, content_hash), permitting multiple NULL-content_hash rows per entity"
    requirement: "DATA-04"
    verification:
      - kind: unit
        ref: "python -c PRAGMA table_info(enrichments) assertion + two NULL-content_hash inserts for one entity"
        status: pass
    human_judgment: false
  - id: D3
    description: "Four enrichment Tunables and the seven-section taxonomy load from config/tracked.toml with the exact defaults and declared-order ids"
    requirement: "ENR-02"
    verification:
      - kind: unit
        ref: "python -c load_config() assertion on tunables.enrichment_cap/grounding_char_cap/enrichment_model/confidence_flag_threshold and c.sections id order"
        status: pass
    human_judgment: false

duration: 45min
completed: 2026-08-14
status: complete
---

# Phase 2 Plan 1: Cost-Gated Enrichment Substrate Summary

**Enrichments cache table (composite content-hash key), four config-driven enrichment Tunables, seven-section taxonomy, and the Wave 0 failing test harness that Plans 02–05 turn green.**

## Performance

- **Duration:** 45 min
- **Completed:** 2026-08-14
- **Tasks:** 3
- **Files modified:** 9

## Accomplishments
- `enrichments` table added to `techtrend/db/schema.sql`: composite `UNIQUE(entity_id, content_hash)` cache key, `idx_enrichments_entity_computed` index for the future dashboard `MAX(computed_at)` join, forward-only `CREATE TABLE IF NOT EXISTS` migration with no change needed to `db/connection.py`.
- Four enrichment `Tunables` (`enrichment_cap=15`, `grounding_char_cap=2000`, `enrichment_model="claude-haiku-4-5"`, `confidence_flag_threshold="low"`) and a `SectionDef`/`Config.sections` model added to `techtrend/config.py`, each field citing its decision id inline — no enrichment number lives as a code constant.
- Seven `[[sections]]` entries seeded into `config/tracked.toml` from PROJECT.md's taxonomy table, in the exact declared order downstream plans' LLM section enum will be built from.
- Wave 0 failing test scaffolds: `tests/test_grounding.py` (extract_intro/normalize_for_hash + a badge-churn cache-stability regression test), `tests/test_llm.py` (two-line summary, section-enum enforcement, refusal handling — all via a fake Anthropic client, no live call), `tests/test_enrich.py` (eligible-set gate, hard cap, cache-hit skip, fetch-failure skip), plus two new scaffolds appended to `tests/test_dashboard.py` (`test_unenriched_item_still_renders`, `test_section_filter`) and three new fixtures.

## Task Commits

Each task was committed atomically:

1. **Task 1: Wave 0 failing test scaffolds and fixtures** - `ee318b2` (test)
2. **Task 2: enrichments cache table migration** - `4e1fe69` (feat)
3. **Task 3: enrichment Tunables and seven-section taxonomy in config** - `45aa30e` (feat)

**Plan metadata:** pending (docs: complete plan)

## Files Created/Modified
- `techtrend/db/schema.sql` - Added the `enrichments` table + index, updated the file-level "five tables" header comment
- `techtrend/config.py` - Added four `Tunables` fields + `SectionDef` + `Config.sections`
- `config/tracked.toml` - Added four `[tunables]` entries + seven `[[sections]]` array-of-tables
- `tests/test_grounding.py` - New: `extract_intro`/`normalize_for_hash` Wave 0 contract
- `tests/test_llm.py` - New: `enrich_item`/`build_section_result_model` Wave 0 contract, fake Anthropic client
- `tests/test_enrich.py` - New: `select_candidates`/`run_enrichment` Wave 0 contract
- `tests/test_dashboard.py` - Extended with `test_unenriched_item_still_renders` (ENR-06) and `test_section_filter` (DASH-02), plus an `_insert_enrichment` seed helper
- `tests/test_storage.py` - Updated `test_init_db_is_idempotent`'s hardcoded table list to include `enrichments` (direct regression from the additive schema change)
- `tests/fixtures/github/readme_with_badges.md` - New: badges + HTML comment + H1/intro/H2 fixture for extraction tests
- `tests/fixtures/anthropic/enrichment_success.json`, `enrichment_refusal.json` - New: recorded structured-output-shaped fixtures for the fake client to replay

## Decisions Made
- Composite `(entity_id, content_hash)` key for `enrichments` (append-only, `MAX(computed_at)`-joined "current row"), matching RESEARCH.md's A5 recommendation and the codebase's existing `scores`/`MAX(run_date)` idiom — preserves the audit trail of a repo's section changing over time.
- Section taxonomy extends `config/tracked.toml` rather than a new file (A4) — one canonical config surface, consistent with the existing `[seed]`/`[discovery]` pattern.
- Wave 0 test contracts fix the exact function signatures later plans (02-02 grounding, 02-03 llm, 02-04 enrich orchestration, 02-05 dashboard) must implement against: `techtrend.pipeline.grounding.{extract_intro, normalize_for_hash}`; `techtrend.pipeline.llm.{EnrichmentResult, enrich_item, build_section_result_model}`; `techtrend.pipeline.enrich.{select_candidates, run_enrichment}` (the latter accepting `fetch_grounding_fn`/`content_hash_fn`/`llm_call_fn` injection seams so the gate/cap/cache-hit/fetch-failure logic is unit-testable without a live GitHub or Anthropic call).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed `test_storage.py::test_init_db_is_idempotent`'s stale hardcoded table list**
- **Found during:** Task 2 (enrichments cache table migration)
- **Issue:** The pre-existing Phase 1 test hardcoded `tables == ["entities", "run_manifest", "scores", "snapshots"]` (four tables); adding `enrichments` (Task 2's whole purpose) broke this assertion — a direct, in-scope regression from the additive schema change, not a pre-existing unrelated failure.
- **Fix:** Updated the expected list to `["enrichments", "entities", "run_manifest", "scores", "snapshots"]` (alphabetical sort order — `enrichments` sorts before `entities`) and the comment from "four" to "five" user tables.
- **Files modified:** `tests/test_storage.py`
- **Verification:** `pytest -q tests/test_storage.py` — all 6 tests pass.
- **Committed in:** `4e1fe69` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — bug)
**Impact on plan:** Necessary correctness fix directly caused by Task 2's additive migration. No scope creep.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required this plan (the `ANTHROPIC_API_KEY`/`anthropic` package setup RESEARCH.md flags is deferred to whichever later plan (02-02/02-03) first implements `pipeline/llm.py`).

## Next Phase Readiness
- The schema, config, and Wave 0 test harness are in place for Plans 02–05 to implement `techtrend/pipeline/grounding.py`, `techtrend/pipeline/llm.py`, `techtrend/pipeline/enrich.py`, `techtrend/enrich.py`, and the dashboard's `section` filter against a locked, unit-tested contract.
- Full suite (`pytest -q`) is green except for the 13 intentional Wave 0 RED tests (4 in `test_grounding.py`, 3 in `test_llm.py`, 4 in `test_enrich.py`, 2 in `test_dashboard.py`), which fail only on `ModuleNotFoundError` for not-yet-created modules or on not-yet-implemented dashboard behavior — exactly the intended state for Plan 02-02 onward to turn green.
- No blockers.

---
*Phase: 02-cost-gated-llm-enrichment*
*Completed: 2026-08-14*

## Self-Check: PASSED

All 9 created/modified files verified present on disk; all 3 task commits (`ee318b2`, `4e1fe69`, `45aa30e`) verified present in git history.
