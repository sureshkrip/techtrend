---
phase: quick-260816-lkt
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - techtrend/daily.py
  - tests/test_daily.py
  - Dockerfile
autonomous: true
requirements:
  - QUICK-daily-pipeline-entrypoint
must_haves:
  truths:
    - "`python -m techtrend.daily` runs collect -> score -> enrich in that exact order in one process."
    - "A non-zero exit from any stage halts the chain immediately and becomes the process exit code; later stages do not run."
    - "The Coolify scheduled-task guidance in the Dockerfile points at the full-pipeline command, not the collect-only one."
  artifacts:
    - techtrend/daily.py
    - tests/test_daily.py
  key_links:
    - "daily.main() dispatches to the existing ingest.main / score.main / enrich.main via module references (so it reuses stage logic and stays monkeypatchable)."
    - "Dockerfile comment string `python -m techtrend.daily` matches the actual entrypoint module name."
---

<objective>
Add a single daily-pipeline entrypoint so a Coolify Scheduled Task can invoke one command that runs the whole daily job.

Today `python -m techtrend.ingest` only collects + backfills (its own docstring: "Does not write to `scores`"). Scoring and enrichment are separate modules (`python -m techtrend.score`, `python -m techtrend.enrich`) that must be run afterward, in order. This plan introduces `python -m techtrend.daily` which chains all three in sequence with fail-fast exit-code propagation, and corrects the Dockerfile guidance that currently points the scheduled task at the collect-only command.

Purpose: One command for the daily scheduled run; no partial/stale downstream work when an upstream stage fails.
Output: `techtrend/daily.py` (new entrypoint), `tests/test_daily.py` (new test), corrected `Dockerfile` comments.
</objective>

<naming_decision>
The scout flagged a collision risk: `techtrend/pipeline/` is a **package** (confirmed — it contains `__init__.py`, `score.py`, `enrich.py`, `orchestrator.py`, etc.). A top-level module `techtrend/pipeline.py` cannot coexist with that package. Therefore the entrypoint is named **`techtrend/daily.py`** → `python -m techtrend.daily`. Do NOT create `techtrend/pipeline.py`.
</naming_decision>

<context>
@techtrend/ingest.py
@techtrend/score.py
@techtrend/enrich.py
@techtrend/logging_setup.py
@tests/test_stability.py
@Dockerfile
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Create techtrend/daily.py chained entrypoint + tests</name>
  <read_first>
    - techtrend/ingest.py (lines 1-32, 132-195) — entrypoint idiom: `def main(argv: list[str] | None = None) -> int:`, `setup_logging()` first, `if __name__ == "__main__": raise SystemExit(main())`. Note ingest.main returns 0.
    - techtrend/score.py (whole file) — returns 0 on success, 1 on failure. `main(argv=None) -> int`.
    - techtrend/enrich.py (whole file) — returns 0 on success, 1 on failure. `main(argv=None) -> int`.
    - techtrend/logging_setup.py — `setup_logging()` is idempotent (replaces handlers, does not stack). Safe for daily.main to call even though each stage also calls it.
    - tests/test_stability.py (lines 187-209) — test idiom: `monkeypatch.setattr(...)`, call `ingest.main([...])`, assert exit code; `from techtrend import ingest, score` module-level imports.
    - tests/test_enrich.py (lines 1-14) — house style: imports inside test functions so `pytest --collect-only` stays clean at Wave 0.
  </read_first>
  <behavior>
    - Test 1 (order on success): with all three stage `main` functions monkeypatched to record their name and return 0, `daily.main([])` returns 0 and the recorded call order is exactly `["collect", "score", "enrich"]`.
    - Test 2 (short-circuit + propagate): with the score stage monkeypatched to return a non-zero code (e.g. 3), `daily.main([])` returns 3, the recorded order is `["collect", "score"]`, and enrich is never called.
    - Test 3 (idiom sanity): `techtrend.daily.main` is callable with signature `main(argv=None) -> int` and the module runs via `python -m techtrend.daily` (guarded `raise SystemExit(main())`).
  </behavior>
  <action>
    Create `techtrend/daily.py` following the exact entrypoint idiom used by ingest/score/enrich. Module docstring states: entrypoint `python -m techtrend.daily`; runs collect (ingest) -> score -> enrich in order for the Coolify Scheduled Task; reuses the existing stage `main()` functions rather than reimplementing collection/scoring/enrichment; fail-fast — the first stage returning a non-zero exit code halts the chain and that code becomes the process exit code (a failed score stage must never be followed by enrich running on stale or partial data).

    Import the three stage MODULES (`from techtrend import enrich, ingest, score`) plus `setup_logging` and `logging`. Define an ordered sequence of `(stage_name, module)` pairs: `("collect", ingest)`, `("score", score)`, `("enrich", enrich)`. IMPORTANT: hold MODULE references, not the bound `main` functions — resolve `module.main` at call time inside the loop so the stages remain monkeypatchable by name in tests and so a future stage-main swap is honored.

    `def main(argv: list[str] | None = None) -> int:` — call `setup_logging()` first (matching every other entrypoint). Then iterate the sequence in order: log a starting line (e.g. `stage=pipeline:<name> status=starting`), call `code = module.main([])` (pass an empty argv list so each stage parses no flags), and if `code != 0` log a failure line including the stage name and exit code and note the chain halted, then `return code` immediately (do NOT run later stages, do NOT swallow the code). On stage success log a completion line and continue. After all stages succeed, log `stage=pipeline status=complete` and `return 0`. End the file with `if __name__ == "__main__": raise SystemExit(main())`.

    Do NOT wrap stage calls in a broad try/except that swallows exceptions — a raised exception from a stage should propagate normally (SystemExit-style), matching the constraint "do not silently swallow errors." Exit-code propagation covers the graceful non-zero-return path; exceptions propagate as-is.

    Create `tests/test_daily.py` mirroring test_stability.py's monkeypatch style. Import `from techtrend import daily, enrich, ingest, score` inside each test function (house style). For each test, monkeypatch `ingest.main`, `score.main`, `enrich.main` with small lambdas/closures that append the stage name to a shared `calls` list and return the desired exit code (use the `list.append(...) or <code>` idiom since `append` returns None: `lambda argv=None: calls.append("collect") or 0`). Assert as described in the behavior block. No real DB, no network, no fixture needed — the stage mains are fully stubbed.
  </action>
  <verify>
    <automated>cd C:/Users/sures/dev/repos/techtrend && python -m pytest tests/test_daily.py -x -q && python -c "import techtrend.daily as d; assert callable(d.main)" && ruff check techtrend/daily.py tests/test_daily.py</automated>
  </verify>
  <acceptance_criteria>
    - `techtrend/daily.py` exists and defines `def main(argv: list[str] | None = None) -> int:` and ends with `if __name__ == "__main__": raise SystemExit(main())`.
    - `python -c "import techtrend.daily"` succeeds (no collision with the `techtrend.pipeline` package; `techtrend/pipeline.py` was NOT created).
    - daily.main resolves each stage via a MODULE reference at call time (grep confirms it calls `ingest`, `score`, `enrich` module mains in that source order; enrich referenced after score, score after ingest).
    - `tests/test_daily.py` exists with a test asserting call order `["collect", "score", "enrich"]` on all-success, and a test asserting a non-zero score-stage code short-circuits (enrich not called) and is returned unchanged.
    - `python -m pytest tests/test_daily.py -x -q` exits 0.
    - `ruff check techtrend/daily.py tests/test_daily.py` exits 0.
  </acceptance_criteria>
  <done>The single command `python -m techtrend.daily` runs collect -> score -> enrich in order, halts on the first non-zero stage and propagates that code, and is covered by passing unit tests.</done>
</task>

<task type="auto">
  <name>Task 2: Point Dockerfile scheduled-task guidance at python -m techtrend.daily</name>
  <read_first>
    - Dockerfile (lines 1-4 and 22-24) — two comment references to the daily scheduled task: line 2-3 "the daily ingest+score job runs as a Coolify Scheduled Task", and line 22-23 "Put the venv on PATH so `uvicorn` / `python -m techtrend.ingest` resolve directly (the Coolify scheduled task calls the latter)." The CMD (line 37) runs uvicorn and must stay unchanged (D-17: serving never triggers a pipeline run).
  </read_first>
  <action>
    Edit the Dockerfile comments only (no CMD/behavior change). Update the header comment (lines 2-3) so it describes the full daily job — replace the "daily ingest+score job" phrasing with wording that reflects collect + score + enrich (e.g. "the daily collect->score->enrich pipeline runs as a Coolify Scheduled Task inside this same container"). Update the PATH comment (lines 22-23) so the referenced command is `python -m techtrend.daily` instead of `python -m techtrend.ingest` — keep the meaning that the venv-on-PATH is what lets the Coolify scheduled task resolve that command directly. Do NOT change the `CMD ["uvicorn", ...]` line and do NOT add a new CMD/ENTRYPOINT for the scheduled task (the scheduled command is configured in Coolify, not baked into the image).
  </action>
  <verify>
    <automated>cd C:/Users/sures/dev/repos/techtrend && grep -q "python -m techtrend.daily" Dockerfile && ! grep -E "scheduled task calls|ingest\+score" Dockerfile | grep -q "techtrend.ingest" && grep -q 'CMD \["uvicorn"' Dockerfile</automated>
  </verify>
  <acceptance_criteria>
    - Dockerfile contains the literal string `python -m techtrend.daily`.
    - No Dockerfile comment still presents `python -m techtrend.ingest` as the command the Coolify scheduled task calls.
    - The `CMD ["uvicorn", "techtrend.server.app:app", ...]` line is unchanged (uvicorn still serves the read-only dashboard; D-17 preserved).
  </acceptance_criteria>
  <done>The Dockerfile guidance directs the Coolify scheduled task to `python -m techtrend.daily`, and the dashboard CMD is untouched.</done>
</task>

</tasks>

<artifacts_this_phase_produces>
- **New module:** `techtrend/daily.py` — exposes `main(argv: list[str] | None = None) -> int`; runnable as `python -m techtrend.daily`. Chains `ingest.main` -> `score.main` -> `enrich.main` with fail-fast exit-code propagation.
- **New test:** `tests/test_daily.py` — covers (a) all three stages run in order on success, (b) a failing early stage short-circuits and its non-zero code propagates without running later stages.
- **Modified:** `Dockerfile` — comments (lines ~2-3 and ~22-23) now reference `python -m techtrend.daily` as the daily scheduled-task command.
</artifacts_this_phase_produces>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Coolify scheduler -> container | The scheduled task invokes `python -m techtrend.daily`; input is a fixed command string, no untrusted external data crosses at this layer. |

## STRIDE Threat Register

No new dependencies are installed (the entrypoint imports only existing first-party modules), no new external input is parsed, and no new network/data surface is introduced. This is an internal orchestration wrapper over already-reviewed stage entrypoints.

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-daily-01 | Denial of Service | daily.main stage chain | low | mitigate | Fail-fast: a non-zero stage halts the chain and propagates the code, so a failed upstream stage cannot drive downstream work on stale/partial data. Covered by the short-circuit unit test. |
| T-daily-02 | Tampering | Dockerfile scheduled-task guidance | low | accept | Comment-only change; the actual scheduled command is configured in Coolify. No image behavior (CMD) changes. |
</threat_model>

<verification>
- `python -m pytest tests/test_daily.py -x -q` exits 0 (order + short-circuit behavior).
- Full suite unaffected: `python -m pytest -q` exits 0.
- `python -c "import techtrend.daily"` succeeds (no package/module collision).
- `ruff check techtrend/daily.py tests/test_daily.py` exits 0.
- `grep "python -m techtrend.daily" Dockerfile` matches; no comment still routes the scheduled task at `techtrend.ingest`.
</verification>

<success_criteria>
- One command (`python -m techtrend.daily`) runs the full daily job: collect -> score -> enrich, in order.
- First non-zero stage halts the chain and its exit code is the process exit code; later stages do not run.
- Stage logic is reused (imports existing `main()` functions), not reimplemented.
- Dockerfile scheduled-task guidance points at the new command; dashboard CMD unchanged.
- New test proves both ordering and fail-fast short-circuit.
</success_criteria>

<output>
Create `.planning/quick/260816-lkt-add-a-single-daily-pipeline-entrypoint-t/260816-lkt-SUMMARY.md` when done.
</output>
