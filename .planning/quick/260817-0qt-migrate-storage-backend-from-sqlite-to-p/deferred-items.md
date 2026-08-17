# Deferred Items — Quick Task 260817-0qt

Items discovered during execution that are out of this task's declared scope
(`files_modified` in 260817-0qt-PLAN.md) and were not modified.

## Pre-existing ruff E501 errors (unrelated to this task)

Confirmed via `git diff` that none of these lines were touched by this task's
commits (c3105b7, b56fcb5, 13d28e8):

- `techtrend/pipeline/enrich.py:238` — line-too-long (101 > 100)
- `tests/test_dashboard.py:126` — line-too-long (103 > 100)
- `tests/test_grounding.py:75` — line-too-long (105 > 100)

Same three errors were already logged as pre-existing/unrelated in quick task
260817-09l's deferred-items. Left unfixed per the scope-boundary rule.

## Test-file scope gap: SQLite-specific mechanics outside this plan's file list

260817-0qt-PLAN.md's `files_modified` lists only `tests/conftest.py` among
test files. Running `uv run pytest -q` (once local PostgreSQL binaries are
available) will still fail on the following files because they bypass the
`db` fixture and hard-code SQLite-only mechanics that Task 1 intentionally
removed/changed:

- `tests/test_paths.py` — asserts `paths.DB_PATH`, which Task 1 removed
  (storage is server-side now). `AttributeError` on collection/run.
- `tests/test_skeleton.py` — calls `sqlite3.connect(db_path)` directly,
  calls `connect(db_path)` with a positional filesystem `Path` (the
  argument is now a `conninfo: str | None` seam, not a file path), and
  monkeypatches `techtrend.db.connection.DEFAULT_DB_PATH`, a constant Task 1
  removed. `AttributeError: module 'techtrend.db.connection' has no
  attribute 'DEFAULT_DB_PATH'`.
- `tests/test_dashboard.py` — same `_seed_db(tmp_path)` → `connect(db_path)`
  positional-path pattern, same `DEFAULT_DB_PATH` monkeypatch pattern.
- `tests/test_health.py` — same `DEFAULT_DB_PATH` monkeypatch pattern.
- `tests/test_enrich.py` — `_seed_db` calls `connect(db_path)` with a
  positional `Path`.
- `tests/test_idempotency.py` — `connect(tmp_path / "reversed.db")` with a
  positional `Path`.
- `tests/test_stability.py` — calls `sqlite3.connect(db_path)` and sets
  `sqlite3.Row` directly (bypassing `techtrend.db.connection` entirely), and
  monkeypatches `DEFAULT_DB_PATH`.
- `tests/test_storage.py` — asserts `PRAGMA journal_mode`/`busy_timeout`
  (a SQLite-only concept with no Postgres equivalent), does integer
  `row[0]` indexing (incompatible with the new `dict_row` factory, which
  only supports string-key access), and queries `sqlite_master` (Postgres
  uses `information_schema`/`pg_catalog` instead).

Evidence: `uv run pytest -q` produced 34 `FAILED` (mostly
`AttributeError: ... has no attribute 'DEFAULT_DB_PATH'` or
`paths.DB_PATH`) plus 47 `ERROR` (blocked entirely by the missing
`pg_config`/`initdb` binaries — see 260817-0qt-SUMMARY.md's Blockers
section). `tests/test_llm_openai.py` and `tests/test_llm.py` (no DB
dependency) are unaffected and pass 8/8.

Per PLAN.md Task 2's own instruction — "if any test FAILS due to a
genuinely SQLite-specific assertion ... STOP and flag it in your summary
— do NOT silently rewrite the assertion" — these were flagged rather than
silently patched, since fixing them requires modifying seven test files
not listed in this plan's `files_modified`, several of which also assert
on genuinely SQLite-only behavior (WAL journal mode) that has no direct
Postgres equivalent and needs an explicit decision (delete the assertion,
or replace it with a Postgres-appropriate health check) rather than a
silent mechanical rewrite.

**Recommended next step:** a follow-up quick task or plan scoped
specifically to migrating these seven test files — updating the
`connect(db_path)`/`DEFAULT_DB_PATH` mechanics to use the same
`conninfo`-seam pattern `tests/conftest.py`'s `db` fixture now uses, and
making an explicit decision on `test_storage.py`'s WAL-mode assertions.
