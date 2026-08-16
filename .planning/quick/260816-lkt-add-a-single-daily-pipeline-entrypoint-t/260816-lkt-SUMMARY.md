---
phase: quick-260816-lkt
plan: 01
subsystem: pipeline
tags: [entrypoint, scheduling, coolify, fail-fast]
status: complete
requires: [techtrend.ingest, techtrend.score, techtrend.enrich, techtrend.logging_setup]
provides: [techtrend.daily]
affects: [Dockerfile]
tech-stack:
  added: []
  patterns: [chained-entrypoint, fail-fast-exit-code-propagation, module-ref-dispatch]
key-files:
  created:
    - techtrend/daily.py
    - tests/test_daily.py
  modified:
    - Dockerfile
decisions:
  - Entrypoint named daily.py (not pipeline.py) to avoid collision with the techtrend.pipeline package.
  - daily.STAGES holds module references, resolving module.main at call time to stay monkeypatchable and honor future stage-main swaps.
  - No broad try/except around stage calls — raised exceptions propagate as-is; only graceful non-zero returns are handled by the exit-code path.
metrics:
  duration: ~8m
  completed: 2026-08-16
  tasks: 2
  files: 3
---

# Phase quick-260816-lkt Plan 01: Daily Pipeline Entrypoint Summary

Added `python -m techtrend.daily`, a single-process chained entrypoint that runs collect -> score -> enrich in order with fail-fast exit-code propagation, and repointed the Dockerfile's Coolify scheduled-task guidance at it.

## What Was Built

- **`techtrend/daily.py`** — `main(argv: list[str] | None = None) -> int`. Calls `setup_logging()`, then iterates an ordered `STAGES` list of `(name, module)` pairs `[("collect", ingest), ("score", score), ("enrich", enrich)]`, resolving `module.main([])` at call time. On the first non-zero return it logs a failure line and returns that code immediately (later stages do not run); on all-success it returns 0. Ends with `if __name__ == "__main__": raise SystemExit(main())`. Module references (not bound `main` functions) are held so stages remain monkeypatchable by name.
- **`tests/test_daily.py`** — three tests mirroring `test_stability.py`'s monkeypatch idiom (imports inside test functions, `list.append(...) or <code>` stubs, no DB/network): (1) all-success order is exactly `["collect", "score", "enrich"]` and returns 0; (2) a score stage returning 3 short-circuits — enrich never runs, calls are `["collect", "score"]`, and 3 is returned unchanged; (3) `main` is callable with an `argv=None` default.
- **`Dockerfile`** — comment-only edits: header now describes "the daily collect->score->enrich pipeline"; the PATH comment references `python -m techtrend.daily` instead of `python -m techtrend.ingest`. `CMD ["uvicorn", ...]` unchanged (D-17: serving never triggers a pipeline run).

## Verification

- `python -m pytest tests/test_daily.py -x -q` — 3 passed.
- Full suite `python -m pytest -q` — 137 passed, no regressions.
- `python -c "import techtrend.daily"` — succeeds; no collision with the `techtrend.pipeline` package (`techtrend/pipeline.py` was NOT created).
- `ruff check techtrend/daily.py tests/test_daily.py` — All checks passed.
- Dockerfile: contains literal `python -m techtrend.daily`; no comment routes the scheduled task at `techtrend.ingest`; `CMD ["uvicorn" ...]` intact.

## TDD Gate Compliance

RED committed first (`d7545e5`, test-only, failed with `ImportError: cannot import name 'daily'` — the correct reason), then GREEN (`13f6291`). No unexpected passing test during RED.

## Deviations from Plan

None — plan executed exactly as written.

## Commits

- `d7545e5` test(quick-260816-lkt): add failing tests for daily pipeline entrypoint (RED)
- `13f6291` feat(quick-260816-lkt): add python -m techtrend.daily chained entrypoint (GREEN)
- `cbfb874` docs(quick-260816-lkt): point Coolify scheduled-task guidance at techtrend.daily

## Self-Check: PASSED

- FOUND: techtrend/daily.py
- FOUND: tests/test_daily.py
- FOUND: Dockerfile (modified)
- FOUND commit: d7545e5
- FOUND commit: 13f6291
- FOUND commit: cbfb874
