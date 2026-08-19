---
phase: quick-260818-sbl
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - techtrend/enrich.py
  - tests/test_enrich.py
  - README.md
  - .env.example
autonomous: true
requirements: [QUICK-260818-sbl]
must_haves:
  truths:
    - "With TECHTREND_DISABLE_LLM set truthy, enrich.main() returns 0 and calls no LLM"
    - "run_enrichment is never invoked when the switch is on"
    - "A run_manifest row (stage='enrich', status='disabled', item_count=0) records the skip"
    - "Unset/falsy values run enrichment exactly as before"
    - "Neither OPENAI_API_KEY nor ANTHROPIC_API_KEY is required when disabled"
  artifacts:
    - "techtrend/enrich.py::_llm_disabled helper"
    - "tests/test_enrich.py disabled-switch tests"
    - "README.md TECHTREND_DISABLE_LLM documentation"
    - ".env.example commented TECHTREND_DISABLE_LLM line"
  key_links:
    - "enrich.main() early-return gate placed after connect()+init_db(), before the run_enrichment try-block"
    - "record_stage(conn, ..., 'enrich', 'disabled', ...) reuses the existing single writer"
---

<objective>
Add a runtime kill-switch `TECHTREND_DISABLE_LLM` that disables the enrichment/summary
LLM stage entirely: zero LLM calls, no API key required, and the daily pipeline chain
still completes normally.

Purpose: Let the owner toggle enrichment off from Coolify env (no config-file edit) —
useful for cost control or running the collect+score pipeline without provider credentials.
Output: A one-place env gate at the top of `techtrend/enrich.py::main()`, an honest
`run_manifest` row marking the skip, tests, and docs.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.claude/CLAUDE.md
@techtrend/enrich.py
@techtrend/pipeline/orchestrator.py
@tests/test_enrich.py
@README.md

Interface notes for the executor:
- `techtrend/enrich.py::main()` sequence today: setup_logging() → load_config() →
  connect() + init_db() → set run_date/run_date_str/started_at → try: run_enrichment(...)
  → record_stage(..., status) → conn.commit() → return 0; except → record 'failed', return 1;
  finally: conn.close(). `_now_iso()` already exists in this module.
- `record_stage(conn, run_date, stage, status, item_count=None, error_detail=None,
  started_at=None, finished_at=None)` (techtrend/pipeline/orchestrator.py) upserts on
  (run_date, stage). status is free TEXT — 'disabled' inserts cleanly (schema.sql
  run_manifest.status has NO CHECK constraint; do not add one).
- Tests use the shared Postgres `db` fixture (a live connection) from tests/conftest.py;
  imports live inside each test function. Follow that pattern exactly.
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add _llm_disabled helper and the disabled gate in enrich.main()</name>
  <files>techtrend/enrich.py</files>
  <behavior>
    - _llm_disabled() returns True for env value "1","true","TRUE","yes","on" (case-insensitive, whitespace-trimmed).
    - _llm_disabled() returns False for "0","false","","maybe", and when the var is unset (None).
    - When _llm_disabled() is True, main() returns 0, does NOT call run_enrichment, writes a run_manifest row (stage='enrich', status='disabled', item_count=0), commits, and closes conn.
    - When _llm_disabled() is False, main() behaves exactly as before.
  </behavior>
  <action>
    Add `import os` to the imports. Add a module-level helper `_llm_disabled() -> bool`
    that reads `os.environ.get("TECHTREND_DISABLE_LLM")`, returns False when None, else
    strips + lowercases the value and returns True only when it is one of the truthy
    tokens (define them as a small frozenset: one, true, yes, on). Read the env var in
    this ONE place only — no other module reads it.

    In `main()`, insert the disabled gate AFTER `init_db(conn)` and AFTER computing
    `run_date`, `run_date_str`, and `started_at`, but BEFORE the existing `try:` block.
    When `_llm_disabled()` is True: emit exactly this log line via `logger.info` —
    `stage=enrich status=disabled note=TECHTREND_DISABLE_LLM set; enrichment skipped, no LLM calls` —
    then call `record_stage(conn, run_date_str, "enrich", "disabled", item_count=0,
    started_at=started_at, finished_at=_now_iso())`, then `conn.commit()`,
    `conn.close()`, and `return 0`. Because run_enrichment is never reached, no LLM
    client is built and neither API key is required. Ensure conn is closed on this path
    (the early return closes conn explicitly, mirroring the existing finally-block close).
    Do NOT gate inside pipeline/enrich.py; do NOT add the switch to config.py/Tunables.
  </action>
  <verify>
    <automated>python -c "import os; os.environ['TECHTREND_DISABLE_LLM']=' TRUE '; from techtrend.enrich import _llm_disabled; assert _llm_disabled() is True; os.environ['TECHTREND_DISABLE_LLM']='maybe'; assert _llm_disabled() is False; del os.environ['TECHTREND_DISABLE_LLM']; assert _llm_disabled() is False; print('ok')"</automated>
  </verify>
  <done>_llm_disabled parses truthy/falsy/unset correctly; main() has an early-return disabled branch that records status='disabled' and never calls run_enrichment.</done>
</task>

<task type="auto">
  <name>Task 2: Add disabled-switch tests to tests/test_enrich.py</name>
  <files>tests/test_enrich.py</files>
  <action>
    Add tests using the shared `db` fixture (function-local imports, matching the file's
    existing style). Monkeypatch env with pytest's `monkeypatch.setenv` /
    `monkeypatch.delenv`.

    Test A (disabled path): set TECHTREND_DISABLE_LLM=1; patch
    `techtrend.enrich.run_enrichment` with a Mock; also patch
    `techtrend.enrich.connect` to return the `db` fixture connection and
    `techtrend.enrich.init_db` to a no-op so main() uses the test DB (do NOT let main()
    open a second connection). Call `techtrend.enrich.main([])`; assert it returns 0,
    assert the run_enrichment mock `.assert_not_called()`, and query run_manifest for the
    row with stage='enrich' — assert status='disabled' and item_count=0.

    Test B (parametrized parsing): parametrize truthy values ("1","true","TRUE","yes","on")
    → assert `_llm_disabled()` is True; and falsy/unset ("0","false","","maybe") plus the
    unset case → assert False. Use monkeypatch.setenv / delenv per case; import
    `_llm_disabled` from techtrend.enrich.

    Test C (falsy path still runs): set TECHTREND_DISABLE_LLM=0 (or leave unset); patch
    run_enrichment to a stub returning 0 (so no real LLM), patch connect/init_db to the
    db fixture as in Test A; call main([]) and assert run_enrichment WAS called
    (`.assert_called_once()`). This proves the gate does not fire on falsy values.
    Keep every test network-free — no real provider client is constructed on any path.
  </action>
  <verify>
    <automated>python -m pytest tests/test_enrich.py -q</automated>
  </verify>
  <done>New tests pass alongside the existing suite; disabled path asserts run_enrichment not called + status='disabled' row; parsing + falsy-path tests pass.</done>
</task>

<task type="auto">
  <name>Task 3: Document TECHTREND_DISABLE_LLM in README.md and .env.example</name>
  <files>README.md, .env.example</files>
  <action>
    README.md — under the "Other configuration:" list in the `## Configure` section (after
    the alternative-LLM-provider bullet, near line 44), add a bullet for
    **`TECHTREND_DISABLE_LLM`**: a runtime env switch (truthy values 1/true/yes/on) that
    skips the enrichment LLM/summary stage entirely — when set, no LLM calls are made and
    neither `OPENAI_API_KEY` nor `ANTHROPIC_API_KEY` is required; the pipeline still
    collects and scores, and the run is recorded with a run_manifest 'disabled' status.
    Toggleable in the Coolify deploy environment without editing config files.

    .env.example — add the commented line
    `# TECHTREND_DISABLE_LLM=1  # set to skip enrichment LLM/summary calls`.
    If .env.example does not yet exist, create it containing that single commented line
    (plus a trailing newline).
  </action>
  <verify>
    <automated>python -c "import pathlib; r=pathlib.Path('README.md').read_text(encoding='utf-8'); e=pathlib.Path('.env.example').read_text(encoding='utf-8'); assert 'TECHTREND_DISABLE_LLM' in r and 'TECHTREND_DISABLE_LLM' in e; print('ok')"</automated>
  </verify>
  <done>README documents the switch under Configure; .env.example has the commented TECHTREND_DISABLE_LLM line.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| deploy env → app | TECHTREND_DISABLE_LLM is read from process env (owner-controlled Coolify config) |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-sbl-01 | Tampering | env var parsing in _llm_disabled | low | mitigate | Strict allow-list of truthy tokens (trimmed, lowercased); anything else runs enrichment normally — no ambiguous silent disable |
| T-sbl-02 | Repudiation | skipped enrichment leaves no trace | low | mitigate | Record an honest run_manifest row (status='disabled', item_count=0) so a disabled run is never mistaken for a successful enrichment |
| T-sbl-03 | Denial of Service | switch left on unnoticed | low | accept | Single-user owner-operated tool; the 'disabled' run_manifest row + log line make the state visible on inspection |
</threat_model>

<verification>
- `python -m pytest tests/test_enrich.py -q` — all pass, including the new disabled-switch tests.
- Helper parse assertion (Task 1 automated verify) confirms truthy/falsy/unset behavior.
- README.md and .env.example both mention TECHTREND_DISABLE_LLM.
- No new network calls or provider clients are constructed on any tested path.
</verification>

<success_criteria>
- `TECHTREND_DISABLE_LLM` truthy → enrich.main() returns 0, run_enrichment not called, run_manifest row status='disabled' item_count=0 written, conn closed.
- Falsy/unset → enrichment runs exactly as before.
- Both `python -m techtrend.enrich` and `python -m techtrend.daily` (which calls enrich.main([])) are covered by this single gate with no change to daily.py.
- Switch is env-only (not a config.py/Tunables value); no CHECK constraint added for the new status.
</success_criteria>

<output>
Create `.planning/quick/260818-sbl-add-techtrend-disable-llm-env-switch-to-/260818-sbl-SUMMARY.md` when done.
</output>
