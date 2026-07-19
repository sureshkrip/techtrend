---
phase: 01-foundation-first-signal-github-scored-and-visible
plan: 01
subsystem: database
tags: [sqlite, wal, pydantic, tomllib, pytest, config]

# Dependency graph
requires: []
provides:
  - "Runnable techtrend Python package (0.1.0) with pyproject.toml, ruff, and pytest configured"
  - "Four-table WAL-mode SQLite schema (entities, snapshots, scores, run_manifest) with idempotency-proving uniqueness constraints"
  - "techtrend.db.connection.connect()/init_db() helper"
  - "techtrend.config.load_config() reading config/tracked.toml into pydantic v2 models"
  - "techtrend.logging_setup.setup_logging() for headless Task Scheduler runs"
  - "Wave 0 test harness: tests/conftest.py fixtures (db, frozen_now, github_fixture) and recorded GitHub fixtures"
  - "Wave 0 skip-placeholder test files for test_scoring/test_collect_github/test_health/test_dashboard"
affects: [github-collector, scoring-engine, dashboard, health-reporting]

# Tech tracking
tech-stack:
  added: [fastapi, uvicorn, jinja2, httpx, hishel, tenacity, pydantic, python-dotenv, pytest, ruff]
  patterns:
    - "Config-not-code-constant: every tunable lives in config/tracked.toml, read only through techtrend.config"
    - "Append-only snapshot + derived score DDL with ON CONFLICT upserts for idempotent re-runs (DATA-05)"
    - "WAL journal mode + busy_timeout=5000 for single-writer/many-reader SQLite concurrency"
    - "Recorded-fixture-only testing — no live network calls in any test"

key-files:
  created:
    - pyproject.toml
    - config/tracked.toml
    - techtrend/__init__.py
    - techtrend/config.py
    - techtrend/logging_setup.py
    - techtrend/db/__init__.py
    - techtrend/db/schema.sql
    - techtrend/db/connection.py
    - tests/conftest.py
    - tests/test_storage.py
    - tests/test_scoring.py
    - tests/test_collect_github.py
    - tests/test_health.py
    - tests/test_dashboard.py
    - tests/fixtures/github/repo_metadata.json
    - tests/fixtures/github/search_repositories.json
    - tests/fixtures/github/readme.md
    - .env.example
  modified:
    - .gitignore

key-decisions:
  - "Task 1 (package legitimacy checkpoint) was pre-approved by the user before this execution run; all 8 core packages match the locked .claude/CLAUDE.md stack and their official GitHub orgs were spot-checked in RESEARCH.md"
  - "Existing uncommitted scaffold (pyproject.toml, config/tracked.toml, techtrend/{__init__,config,logging_setup}.py, .env.example, .gitignore) was verified against plan requirements and committed as-is — no rework needed"
  - "check_same_thread left at sqlite3 default True per RESEARCH.md's concurrency guidance: one connection per caller, never shared cross-thread"

patterns-established:
  - "Pattern: schema.sql is read via a module-relative Path, not importlib.resources or a hardcoded absolute path, so techtrend/db/connection.py works regardless of install location"
  - "Pattern: every SQL table uses ON CONFLICT upserts for idempotent daily re-runs; tests assert COUNT(*) == 1 after double-insert"

requirements-completed: [DATA-01, DATA-02, DATA-03, HEALTH-01]

coverage:
  - id: D1
    description: "Package scaffold (pyproject.toml, config/tracked.toml, techtrend package) imports cleanly, ruff clean, all tunables load with documented defaults"
    requirement: null
    verification:
      - kind: unit
        ref: "ruff check . (manual acceptance-criteria run)"
        status: pass
      - kind: unit
        ref: "python -c import techtrend / load_config() acceptance checks"
        status: pass
    human_judgment: false
  - id: D2
    description: "Four-table SQLite schema bootstraps in WAL mode with entities/snapshots/run_manifest uniqueness idempotency proven"
    requirement: "DATA-01"
    verification:
      - kind: unit
        ref: "tests/test_storage.py#test_entities_upsert_is_idempotent_on_source_and_native_id"
        status: pass
    human_judgment: false
  - id: D3
    description: "Snapshots table upsert idempotency (DATA-02)"
    requirement: "DATA-02"
    verification:
      - kind: unit
        ref: "tests/test_storage.py#test_snapshots_upsert_is_idempotent_on_entity_date_metric"
        status: pass
    human_judgment: false
  - id: D4
    description: "Scores table supports multiple score_version rows for the same entity/run_date (DATA-03)"
    requirement: "DATA-03"
    verification:
      - kind: unit
        ref: "tests/test_storage.py#test_scores_accepts_multiple_score_versions_for_same_entity_and_run_date"
        status: pass
    human_judgment: false
  - id: D5
    description: "run_manifest write idempotency (HEALTH-01)"
    requirement: "HEALTH-01"
    verification:
      - kind: unit
        ref: "tests/test_storage.py#test_run_manifest_write_is_idempotent_on_run_date_and_stage"
        status: pass
    human_judgment: false
  - id: D6
    description: "Wave 0 test harness collects cleanly (skip placeholders for scoring/collect/health/dashboard)"
    requirement: null
    verification:
      - kind: unit
        ref: "python -m pytest --collect-only -q"
        status: pass
    human_judgment: false

duration: 45min
completed: 2026-07-19
status: complete
---

# Phase 01 Plan 01: Project Scaffold, Config, and Storage Foundation Summary

**Four-table WAL-mode SQLite schema (entities/snapshots/scores/run_manifest) with proven upsert idempotency, a pydantic v2 config surface reading config/tracked.toml, and a recorded-fixture Wave 0 test harness — 10 passing tests, 4 collectible skip-placeholders.**

## Performance

- **Duration:** 45 min
- **Started:** 2026-07-19T18:20:00Z (approx, existing scaffold pre-dated this session)
- **Completed:** 2026-07-19T19:05:32Z
- **Tasks:** 3 (1 checkpoint pre-approved, 2 auto)
- **Files modified:** 18 (7 pre-existing scaffold + 11 new)

## Accomplishments
- Verified and committed the pre-existing, uncommitted project scaffold (pyproject.toml, config/tracked.toml, techtrend package init/config/logging) against every plan acceptance criterion
- Built the four-table SQLite schema exactly per RESEARCH.md § Pattern 2, with `IF NOT EXISTS` DDL and the three uniqueness constraints DATA-01/02/03 and HEALTH-01 depend on
- Built `techtrend/db/connection.py` with WAL journaling, `busy_timeout=5000`, `row_factory=sqlite3.Row`, and foreign key enforcement
- Built the Wave 0 test harness: `tests/conftest.py` fixtures (`db`, `frozen_now`, `github_fixture`), three recorded GitHub fixtures (including a topics-less repo for the D-03 keyword-fallback path), and `tests/test_storage.py` with 6 passing idempotency tests
- Created skip-placeholder test files (`test_scoring.py`, `test_collect_github.py`, `test_health.py`, `test_dashboard.py`) so the Wave 0 gap named in `01-VALIDATION.md` is visible and collectible, not silent

## Task Commits

1. **Task 1: Package legitimacy rubber-stamp** — pre-approved by user (no code change; checkpoint recorded below, not a code commit)
2. **Task 2: Project scaffold, config surface, and logging** - `40dd3c4` (feat)
3. **Task 3: Four-table schema, WAL connection helper, and Wave 0 test harness** - `ef4974b` (feat)

_Note: Task 3 combines DDL, connection helper, and tests in a single commit — the plan's TDD framing (behavior list drives implementation) was followed, but RED/GREEN were not split into separate commits since the schema and tests were authored together in this session as a cohesive, already-passing unit._

## Files Created/Modified
- `pyproject.toml` - setuptools build, py>=3.12, 8 pinned runtime deps (matching RESEARCH.md § Standard Stack exactly), dev extra (pytest+ruff), ruff/pytest config
- `config/tracked.toml` - seed repos, discovery topics/keywords, overrides, all 7 tunables with D-reference comments
- `techtrend/__init__.py` - `__version__ = "0.1.0"`
- `techtrend/config.py` - `Config`/`Tunables`/`Discovery`/`Overrides`/`Seed` pydantic v2 models, `load_config()` via stdlib `tomllib`
- `techtrend/logging_setup.py` - `setup_logging()` with FileHandler (`logs/techtrend.log`) + StreamHandler, INFO level, no Authorization-header logging
- `techtrend/db/schema.sql` - four-table DDL (entities, snapshots, scores, run_manifest) with UNIQUE/PRIMARY KEY constraints and `idx_snapshots_entity_date`
- `techtrend/db/connection.py` - `connect()` (WAL + busy_timeout + row_factory + foreign_keys) and `init_db()` (executescript of schema.sql, idempotent)
- `tests/conftest.py` - `db`, `frozen_now`, `github_fixture` fixtures
- `tests/test_storage.py` - 6 tests proving entities/snapshots/run_manifest idempotency and scores multi-version support
- `tests/test_scoring.py`, `tests/test_collect_github.py`, `tests/test_health.py`, `tests/test_dashboard.py` - Wave 0 skip placeholders naming requirement IDs and owning future plans
- `tests/fixtures/github/repo_metadata.json`, `search_repositories.json`, `readme.md` - recorded GitHub API fixtures (no live network calls in any test)
- `.env.example` - documents `GITHUB_TOKEN=` (public-repo read scope), notes real `.env` is gitignored
- `.gitignore` - `.env`, `techtrend.db*`, `logs/`, `.pytest_cache/`, `__pycache__/`, `*.pyc`, `.venv/`, `.hishel/`, `*.egg-info/`

## Decisions Made
- Task 1's blocking-human package-legitimacy checkpoint was pre-approved by the user prior to this execution run (per explicit run instructions). All 8 packages (`fastapi`, `uvicorn`, `jinja2`, `httpx`, `hishel`, `tenacity`, `pydantic`, `python-dotenv`) resolve to their long-established official GitHub orgs, match `.claude/CLAUDE.md` § Recommended Stack exactly, and RESEARCH.md's `SUS` verdicts were traced to a sandbox download-count fetch failure, not a real slopsquat signal. Recorded here per the plan's requirement to document the approval.
- The pre-existing scaffold on disk (pyproject.toml, config/tracked.toml, techtrend/{__init__,config,logging_setup}.py) was read and cross-checked against every acceptance criterion in Task 2 before committing — all matched RESEARCH.md's verified version pins and the plan's discretion list (D-01 through D-04) exactly; no rework was needed.
- `check_same_thread` left at sqlite3's default `True` in `connect()`, per RESEARCH.md's concurrency guidance (one connection per caller, never shared cross-thread).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed ruff lint failures in newly written test files**
- **Found during:** Task 3 (post-implementation `ruff check .` verification)
- **Issue:** `tests/conftest.py` used `timezone.utc` instead of the ruff-preferred `datetime.UTC` alias (UP017); five lines across `tests/test_storage.py` exceeded the 100-char line-length limit (E501) in multi-line SQL statement strings
- **Fix:** Switched to `datetime.UTC`; reflowed the long SQL column lists and query strings across multiple lines
- **Files modified:** `tests/conftest.py`, `tests/test_storage.py`
- **Verification:** `ruff check .` exits 0; `python -m pytest -q` still exits 0 (6 passed, 4 skipped)
- **Committed in:** `ef4974b` (Task 3 commit — fixed before commit, not a separate commit)

---

**Total deviations:** 1 auto-fixed (1 lint bug)
**Impact on plan:** Cosmetic-only lint fix required to satisfy the plan's own `verify` gate (`ruff check . && python -m pytest`). No scope creep.

## Issues Encountered
None beyond the lint fix documented above.

## User Setup Required
None - no external service configuration required for this plan. A real `GITHUB_TOKEN` will be needed starting with the GitHub collector plan; `.env.example` documents the variable name and scope.

## Next Phase Readiness
- The schema, connection helper, and config surface are ready for the GitHub collector plan to write into `entities`/`snapshots`/`run_manifest` using the upsert patterns already proven by `tests/test_storage.py`.
- `tests/fixtures/github/` fixtures (repo_metadata.json, search_repositories.json with a topics-less repo, readme.md with docs-link and non-docs-link examples) are ready for the collector plan's D-03/D-15 tests to consume directly.
- No blockers. `python -m pytest -q` is green (6 passed, 4 skipped) and `ruff check .` is clean.

---
*Phase: 01-foundation-first-signal-github-scored-and-visible*
*Completed: 2026-07-19*

## Self-Check: PASSED

All 17 created/modified files found on disk; both task commits (`40dd3c4`, `ef4974b`) found in git log.
