---
phase: quick-260817-0qt
plan: "01"
subsystem: storage
tags: [postgresql, psycopg, migration, sqlite, testing, pytest-postgresql]

requires:
  - phase: 01-01
    provides: techtrend.db.connection's connect()/init_db() contract and the five-table schema all pipeline/server modules read and write
provides:
  - psycopg3-based storage layer (techtrend/db/connection.py) reading discrete PG* env vars with a conninfo injection seam and dict_row row factory
  - Postgres DDL (techtrend/db/schema.sql) with IDENTITY PKs, DOUBLE PRECISION wilson bound, and default NULL-distinct composite UNIQUE semantics preserved
  - Every application SQL statement across ingest/pipeline/server converted to psycopg paramstyle (%s / %(name)s)
  - tests/conftest.py db fixture backed by pytest-postgresql (ephemeral per-test Postgres database, no Docker)
affects: [ingest, pipeline, server, tests, docs]

tech-stack:
  added: ["psycopg[binary]==3.3.4", "pytest-postgresql==8.1.0 (dev)"]
  patterns: ["conninfo injection seam on connect() so tests never read PG* env vars", "dict_row factory replacing sqlite3.Row for all query results"]

key-files:
  created:
    - .planning/quick/260817-0qt-migrate-storage-backend-from-sqlite-to-p/deferred-items.md
  modified:
    - pyproject.toml
    - uv.lock
    - techtrend/db/connection.py
    - techtrend/db/schema.sql
    - techtrend/paths.py
    - tests/conftest.py
    - techtrend/ingest.py
    - techtrend/pipeline/identity.py
    - techtrend/pipeline/snapshot.py
    - techtrend/pipeline/orchestrator.py
    - techtrend/pipeline/backfill_runner.py
    - techtrend/pipeline/score.py
    - techtrend/pipeline/stability.py
    - techtrend/pipeline/enrich.py
    - techtrend/server/queries.py
    - techtrend/server/health.py
    - techtrend/server/app.py
    - README.md
    - .claude/CLAUDE.md

key-decisions:
  - "connect() gains a conninfo: str | None = None parameter as the ONLY new parameter; the zero-arg connect() production call form is preserved unchanged"
  - "PGPASSWORD is read exactly once, in techtrend/db/connection.py, mirroring the ANTHROPIC_API_KEY/OPENAI_API_KEY isolation pattern already established for llm.py/llm_openai.py (grep-verified: only techtrend/db/connection.py matches)"
  - "conftest.py's db fixture derives conninfo from pytest-postgresql's postgresql_client fixture info (host/port/dbname/user/password) rather than using that fixture's own already-open connection directly, so it exercises the exact connect(conninfo=...) seam production code paths could use for a future non-env-var deployment"
  - "Superseded SQLite-vs-Postgres rows in CLAUDE.md's Alternatives Considered / What NOT to Use tables were annotated (strikethrough + supersession note) rather than deleted, preserving decision history per the plan's own 'stays honest about decision history' instruction"

requirements-completed: []

coverage:
  - id: T1
    description: "psycopg3 connection layer + Postgres DDL + ephemeral-PG test harness"
    verification:
      - kind: unit
        ref: "uv run python -c \"import techtrend.db.connection as c; import inspect; assert 'conninfo' in inspect.signature(c.connect).parameters; assert 'sqlite3' not in inspect.getsource(c)\" — pass"
        status: pass
      - kind: other
        ref: "grep -c 'GENERATED ALWAYS AS IDENTITY' techtrend/db/schema.sql == 3 — pass"
        status: pass
      - kind: other
        ref: "rg -n 'PRAGMA|journal_mode|executescript|NULLS NOT DISTINCT|sqlite3' techtrend/db — no matches, pass"
        status: pass
      - kind: other
        ref: "rg -n 'paths\\.DB_PATH|DB_PATH =' techtrend — no matches, pass"
        status: pass
    human_judgment: false
  - id: T2
    description: "Every parameterized query rewritten to psycopg paramstyle; no sqlite3 remains in techtrend/**; PGPASSWORD confined to connection.py; full suite passes"
    verification:
      - kind: other
        ref: "grep -rn 'import sqlite3|sqlite3\\.' techtrend — no matches, pass"
        status: pass
      - kind: other
        ref: "grep -rl PGPASSWORD techtrend — only techtrend/db/connection.py, pass"
        status: pass
      - kind: unit
        ref: "uv run pytest tests/test_llm_openai.py tests/test_llm.py -q — 8/8 pass, no regression"
        status: pass
      - kind: unit
        ref: "uv run pytest -q (full 146-test suite against ephemeral Postgres)"
        status: fail
        note: "Could not execute — see Blockers. 47 tests error on missing pg_config/initdb; 34 tests fail on SQLite-specific test-file mechanics outside this plan's file scope (see deferred-items.md)."
    human_judgment: false
  - id: T3
    description: "README + CLAUDE.md document the Postgres migration and its deliberate reversal of the prior SQLite recommendation"
    verification:
      - kind: other
        ref: "rg -n 'PostgreSQL|psycopg|pytest-postgresql|PGDATABASE' README.md — 7 matches, pass"
        status: pass
      - kind: other
        ref: "rg -n 'PostgreSQL|psycopg' .claude/CLAUDE.md — 5 matches, pass"
        status: pass
    human_judgment: false

duration: 55min
completed: 2026-08-17
status: incomplete
---

# Quick Task 260817-0qt: Migrate storage backend from SQLite to PostgreSQL Summary

**Full psycopg3/Postgres replacement of the SQLite storage layer — connection, DDL, every parameterized query across ingest/pipeline/server, and an ephemeral-Postgres pytest harness — implemented and committed exactly per plan; the full-suite pass claim could not be verified because no local PostgreSQL binaries are installed on this machine, and a separate, plan-scope test-file gap was discovered during verification.**

## Performance

- **Duration:** ~55 min
- **Started:** 2026-08-17 (session start)
- **Completed:** 2026-08-17T04:54:47Z (last commit)
- **Tasks:** 3
- **Files modified:** 18 (+ 1 new deferred-items.md)

## Accomplishments

- Added `psycopg[binary]==3.3.4` (runtime) and `pytest-postgresql==8.1.0` (dev) via `uv add`
- Rewrote `techtrend/db/connection.py`: `connect(conninfo: str | None = None)` builds from discrete `PGHOST`/`PGPORT`/`PGDATABASE`/`PGUSER`/`PGPASSWORD` env vars when `conninfo` is `None`, or uses `conninfo` verbatim (the test injection seam) when provided; `dict_row` row factory; all WAL/PRAGMA/`sqlite3` code removed; `init_db(conn)` signature unchanged
- Ported `techtrend/db/schema.sql` to Postgres DDL: 3 `GENERATED ALWAYS AS IDENTITY` primary keys, `BIGINT` for integer FK/value columns, `DOUBLE PRECISION` for `wilson_lower_bound`, every ISO8601 TEXT column preserved as `TEXT`, and the `UNIQUE(entity_id, content_hash)` composite key's default NULL-distinct semantics preserved (no `NULLS NOT DISTINCT`)
- Removed `paths.DB_PATH` (storage is server-side now); `CACHE_DIR`/`CACHE_DB`/`LOG_FILE`/`CONFIG_PATH` untouched
- Rewrote `tests/conftest.py`'s `db` fixture to provision an ephemeral per-test Postgres database via `pytest_postgresql.factories` (`postgresql_proc` + `postgresql("postgresql_proc")`), deriving a `conninfo` string from the client fixture's connection info and passing it through `connect()`'s injection seam — tests never read `PGPASSWORD`
- Converted every parameterized SQL statement across `ingest.py`, `pipeline/identity.py`, `pipeline/snapshot.py`, `pipeline/orchestrator.py`, `pipeline/backfill_runner.py`, `pipeline/score.py`, `pipeline/stability.py`, `pipeline/enrich.py`, `server/queries.py`, `server/health.py` to psycopg paramstyle (`?` → `%s`, `:name` → `%(name)s`); doubled the three `LIKE 'collect:%%'` literals in `health.py`
- Replaced `sqlite3` imports/type hints with `psycopg`/`dict` across `server/queries.py`, `server/health.py`, `server/app.py`
- Updated README.md (Prerequisites, Configure, Tests, Deploy) and `.claude/CLAUDE.md` (Technology Stack, Constraints, and annotated the now-superseded SQLite-vs-Postgres rows in Alternatives Considered / What NOT to Use) to document the migration and its deliberate reversal of the original SQLite recommendation

## Task Commits

Each task was committed atomically:

1. **Task 1: Swap the DB layer + test harness** — `c3105b7` (feat)
2. **Task 2: Rewrite every parameterized query to psycopg paramstyle + scrub sqlite3** — `b56fcb5` (refactor)
3. **Task 3: Update docs (README + CLAUDE.md)** — `13d28e8` (docs)

**Plan metadata:** (pending — orchestrator handles the docs commit)

## Files Created/Modified

- `pyproject.toml`, `uv.lock` — `psycopg[binary]` runtime dep, `pytest-postgresql` dev dep
- `techtrend/db/connection.py` — full psycopg3 rewrite
- `techtrend/db/schema.sql` — Postgres DDL
- `techtrend/paths.py` — `DB_PATH` removed
- `tests/conftest.py` — `db` fixture now Postgres-backed via `pytest-postgresql`
- `techtrend/ingest.py`, `techtrend/pipeline/identity.py`, `techtrend/pipeline/snapshot.py`, `techtrend/pipeline/orchestrator.py`, `techtrend/pipeline/backfill_runner.py`, `techtrend/pipeline/score.py`, `techtrend/pipeline/stability.py`, `techtrend/pipeline/enrich.py` — paramstyle conversion
- `techtrend/server/queries.py`, `techtrend/server/health.py`, `techtrend/server/app.py` — paramstyle conversion + `sqlite3` → `psycopg` type hints
- `README.md`, `.claude/CLAUDE.md` — migration documentation
- `.planning/quick/260817-0qt-migrate-storage-backend-from-sqlite-to-p/deferred-items.md` — new; catalogs the two out-of-scope findings below

## Decisions Made

- `connect()`'s new `conninfo` parameter is the only signature change; the zero-arg production call form (`connect()` in `ingest.py`, `score.py`, `enrich.py`, `app.py`) needed no changes.
- Followed the plan's explicit instruction not to silently rewrite SQLite-specific test assertions — see Blockers below for what that surfaced.
- Left `DB_UNREADABLE_MESSAGE` in `server/app.py` untouched (still says "check `techtrend.db` exists") per the plan's instruction to leave it unless a test asserts on the exact string; confirmed no test does.

## Deviations from Plan

### Auto-fixed Issues

None — Rule 1/2/3 auto-fixes were not needed; the plan's Task 1/Task 2 file-level instructions were followed exactly as written and all listed verification gates that do not require a live Postgres connection pass cleanly.

### Discovered but NOT auto-fixed (flagged per the plan's own instruction)

**1. [Scope gap] Seven test files outside `files_modified` hard-depend on removed SQLite mechanics**

- **Found during:** Task 2 verification (`uv run pytest -q`)
- **Issue:** `tests/test_paths.py`, `test_skeleton.py`, `test_dashboard.py`, `test_health.py`, `test_enrich.py`, `test_idempotency.py`, `test_stability.py`, and `test_storage.py` were not in the plan's declared `files_modified` list (only `tests/conftest.py` was), but several call `connect(db_path)` with a positional filesystem `Path` (now a `conninfo` string seam), monkeypatch `techtrend.db.connection.DEFAULT_DB_PATH` (a constant Task 1 removed), call `sqlite3.connect()` directly, assert `paths.DB_PATH` (removed), or assert genuinely SQLite-only behavior (`PRAGMA journal_mode`, integer `row[0]` indexing incompatible with `dict_row`, `sqlite_master`).
- **Why not fixed:** PLAN.md Task 2 explicitly instructs: "if any test FAILS due to a genuinely SQLite-specific assertion ... STOP and flag it in your summary — do NOT silently rewrite the assertion." Several of these are exactly that (the WAL-mode test in particular has no direct Postgres equivalent and needs an explicit human/planner decision on what to do with it), and fixing the rest would mean modifying seven files never authorized in this plan's scope.
- **Evidence:** `uv run pytest -q` → 34 `FAILED` (mostly `AttributeError: ... has no attribute 'DEFAULT_DB_PATH'` / `paths.DB_PATH`), full detail in `deferred-items.md`.
- **Files:** none modified; documented in `deferred-items.md`.
- **Recommended next step:** a follow-up quick task/plan scoped to migrate these seven files' DB mechanics to the `conninfo`-seam pattern, with an explicit decision on the WAL-mode assertions.

## Blockers

**Local PostgreSQL binaries (`initdb`/`pg_ctl`/`pg_config`) are not on `PATH` on this machine.**

- `command -v initdb pg_ctl postgres` → not found (exit 127)
- `pg_config --bindir` → `pg_config: command not found`
- `uv run pytest -q` → 47 tests `ERROR` with `pytest_postgresql.exceptions.ExecutableMissingException: Could not find pg_config executable. Is it in system $PATH?`

Per the honesty guard, this task's code changes were fully implemented and committed regardless (they are correct by construction against the plan's paramstyle/schema mapping rules), but **the full 146-test suite was never actually run against a live Postgres** and this SUMMARY does not claim it passed. What WAS verified without a database:

- `uv run ruff check techtrend tests` — clean except 3 pre-existing, unrelated E501 errors (confirmed via `git diff` that none of the 3 flagged lines were touched by this task's commits): `techtrend/pipeline/enrich.py:238`, `tests/test_dashboard.py:126`, `tests/test_grounding.py:75`.
- `rg -n 'import sqlite3|sqlite3\.' techtrend` → no matches (pass).
- `rg -l PGPASSWORD techtrend` → only `techtrend/db/connection.py` (pass).
- `grep -c 'GENERATED ALWAYS AS IDENTITY' techtrend/db/schema.sql` → 3 (pass).
- `uv run pytest tests/test_llm_openai.py tests/test_llm.py -q` → **8/8 passed** (these tests have no DB dependency, so this genuinely ran and genuinely passed — no Kimi/Anthropic regression).

**Remediation:** Install PostgreSQL locally and ensure its `bin/` directory (containing `initdb`, `pg_ctl`, `postgres`, `pg_config`) is on `PATH`, then re-run `uv run pytest -q`. Once that passes, separately address the test-file scope gap above before this migration can be considered fully verified end-to-end.

## User Setup Required

1. Install PostgreSQL locally (any recent version) and add its `bin/` directory to `PATH` so `initdb`/`pg_ctl`/`pg_config` are resolvable — required to run `pytest`.
2. For real (non-test) runs: stand up a PostgreSQL server with a `techtrend` database and `techuser` role, and set `PGPASSWORD` (plus `PGHOST`/`PGPORT`/`PGDATABASE`/`PGUSER` if they differ from the documented defaults) in `.env`.
3. Re-run `uv run pytest -q` once PG binaries are available, and review `deferred-items.md`'s test-file scope gap before treating this migration as fully verified.

## Next Phase Readiness

Application code (`techtrend/**`) is fully migrated to PostgreSQL/psycopg3 with no `sqlite3` remaining and PGPASSWORD correctly isolated. This quick task should be treated as **incomplete** until (a) the full suite is actually run green against a real ephemeral Postgres, and (b) the seven out-of-scope test files are migrated. Phase 3 (Source Breadth) work should not proceed against this branch until both are resolved, since Phase 3 will add new collectors that also write through this same storage layer.

---
*Quick task: 260817-0qt*
*Completed: 2026-08-17*

## Self-Check: PASSED

- FOUND: techtrend/db/connection.py
- FOUND: techtrend/db/schema.sql
- FOUND: techtrend/paths.py
- FOUND: tests/conftest.py
- FOUND: .planning/quick/260817-0qt-migrate-storage-backend-from-sqlite-to-p/deferred-items.md
- FOUND commit: c3105b7
- FOUND commit: b56fcb5
- FOUND commit: 13d28e8
