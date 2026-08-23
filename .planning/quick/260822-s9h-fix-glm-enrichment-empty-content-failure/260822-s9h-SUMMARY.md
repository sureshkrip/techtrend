---
phase: quick-260822-s9h
plan: 01
subsystem: llm-integration
tags: [pydantic, openai-sdk, glm, config, enrichment]

# Dependency graph
requires:
  - phase: quick-260822-mfu
    provides: env-override pattern in load_config() for enrichment_provider/base_url/model
  - phase: quick-260817-jii
    provides: GLM-4.7-Flash selected as the openai-provider enrichment model in tracked.toml
provides:
  - "Config-driven enrichment_max_tokens (int, default 1024, gt=0) and enrichment_disable_thinking (bool, default False) Tunables"
  - "Env overrides TECHTREND_ENRICHMENT_MAX_TOKENS / TECHTREND_ENRICHMENT_DISABLE_THINKING"
  - "enrich_item_openai(max_tokens=, disable_thinking=) replacing the hardcoded max_tokens=512"
  - "Conditional extra_body={'thinking': {'type': 'disabled'}} sent only when disable_thinking is True"
affects: [enrichment, llm-integration, glm-provider]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Conditional create() kwargs dict (extra_body added only when a flag is set) instead of always-present optional param"]

key-files:
  created: []
  modified:
    - techtrend/config.py
    - config/tracked.toml
    - tests/test_config.py
    - techtrend/pipeline/llm_openai.py
    - techtrend/pipeline/enrich.py
    - tests/test_llm_openai.py

key-decisions:
  - "enrichment_max_tokens defaults to 1024 (2x the old hardcoded 512) as a safety net even when disable_thinking is on"
  - "enrichment_disable_thinking defaults False at the Pydantic field level but True in tracked.toml -- the safe/inert default lives in code, the production choice lives in config"
  - "extra_body is added to the create() kwargs dict conditionally (never present when disable_thinking is False) rather than always sending {'thinking': {'type': 'enabled'}}/{'disabled'} -- keeps non-GLM OpenAI-compatible providers (Kimi) byte-identical to their pre-fix call shape"

requirements-completed: []

coverage:
  - id: D1
    description: "load_config() exposes enrichment_max_tokens=1024 (int) and enrichment_disable_thinking=True from tracked.toml, both env-overridable"
    verification:
      - kind: unit
        ref: "tests/test_config.py#test_all_unset_falls_back_to_tracked_toml"
        status: pass
      - kind: unit
        ref: "tests/test_config.py#test_enrichment_max_tokens_env_override"
        status: pass
      - kind: unit
        ref: "tests/test_config.py#test_enrichment_disable_thinking_env_override"
        status: pass
    human_judgment: false
  - id: D2
    description: "enrich_item_openai sends extra_body={'thinking': {'type': 'disabled'}} only when disable_thinking is True, and uses the passed max_tokens instead of a hardcoded 512"
    verification:
      - kind: unit
        ref: "tests/test_llm_openai.py#test_enrich_item_openai_sends_extra_body_and_max_tokens_when_disable_thinking_true"
        status: pass
      - kind: unit
        ref: "tests/test_llm_openai.py#test_enrich_item_openai_omits_extra_body_when_disable_thinking_false"
        status: pass
      - kind: unit
        ref: "tests/test_llm_openai.py#test_enrich_item_openai_default_max_tokens_and_no_extra_body"
        status: pass
    human_judgment: false
  - id: D3
    description: "enrich.py's openai branch threads tunables.enrichment_max_tokens/enrichment_disable_thinking into enrich_item_openai without touching the anthropic branch (llm.py)"
    verification:
      - kind: integration
        ref: "tests/test_enrich.py (full suite, 26 tests)"
        status: pass
      - kind: other
        ref: "git diff --stat HEAD~2 HEAD -- techtrend/pipeline/llm.py (no output = untouched)"
        status: pass
    human_judgment: false

duration: 5min
completed: 2026-08-22
status: complete
---

# Quick Task 260822-s9h: Fix GLM Enrichment Empty-Content Failure Summary

**Config-driven max_tokens (1024) and GLM thinking-disabled extra_body fix the empty-content 'fetch_failed' tombstones GLM-4.7-Flash produced under the old hardcoded max_tokens=512.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-08-23T00:25:53Z
- **Completed:** 2026-08-23T00:30:37Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Added `enrichment_max_tokens` (int, default 1024, `gt=0`) and `enrichment_disable_thinking` (bool, default False) to `Tunables`, with `TECHTREND_ENRICHMENT_MAX_TOKENS`/`TECHTREND_ENRICHMENT_DISABLE_THINKING` env overrides following the existing 260822-mfu pattern
- Set `enrichment_max_tokens = 1024` and `enrichment_disable_thinking = true` in `config/tracked.toml [tunables]`, restoring working GLM-4.7-Flash enrichment (no more empty-content `finish_reason='length'` failures)
- Parameterized `enrich_item_openai` with `max_tokens`/`disable_thinking` kwargs, replacing the hardcoded `max_tokens=512`; `extra_body={"thinking": {"type": "disabled"}}` is sent only when `disable_thinking` is True, so Kimi/other OpenAI-compatible providers get byte-identical call shapes to before
- Threaded both tunables through `enrich.py`'s `openai` branch `llm_call_fn`; the `anthropic` branch (`llm.py`) is completely untouched

## Task Commits

Each task was committed atomically:

1. **Task 1: Add config-driven max_tokens + disable_thinking tunables with env overrides** - `1c182e2` (feat)
2. **Task 2: Parameterize enrich_item_openai and thread the two values through the enrichment loop** - `4c843b2` (feat)

_Note: implementation and tests for each task were written and verified together per task, consistent with this plan's stated "Two atomic commits" success criterion (config layer; call layer)._

## Files Created/Modified
- `techtrend/config.py` - Two new Tunables fields (`enrichment_max_tokens`, `enrichment_disable_thinking`) + two new env-override entries
- `config/tracked.toml` - `enrichment_max_tokens = 1024`, `enrichment_disable_thinking = true` with rationale comments
- `tests/test_config.py` - Coverage for both new fields, their env overrides, and empty-string-treated-as-unset behavior
- `techtrend/pipeline/llm_openai.py` - `enrich_item_openai` now accepts `max_tokens`/`disable_thinking`; conditional `extra_body` construction
- `techtrend/pipeline/enrich.py` - `openai` branch's `llm_call_fn` passes `tunables.enrichment_max_tokens`/`tunables.enrichment_disable_thinking`
- `tests/test_llm_openai.py` - Three new tests asserting recorded `create()` kwargs via the existing `_FakeCompletions.last_call_kwargs` seam

## Decisions Made
- `enrichment_max_tokens` mirrors `enrichment_cap`'s `gt=0` guard/comment style — a non-positive token cap would defeat the safety net
- `extra_body` is built conditionally into a kwargs dict rather than always passed with a variant "enabled"/"disabled" shape — guarantees zero call-shape change for providers with `disable_thinking=False` (Kimi/Moonshot)
- Left `enrich_item_openai`'s Pydantic-level default (`disable_thinking: bool = False`) inert/safe, with the production-facing True value living only in `tracked.toml` — keeps code defaults conservative while config drives the actual behavior

## Deviations from Plan

None — plan executed exactly as written. Both tasks' behavior, files-touched list, and verification commands match the plan precisely.

## Issues Encountered

None. `tests/test_enrich.py` required extending `PATH` with the local PostgreSQL 17 `bin` directory for the ephemeral-cluster pytest harness (per the plan's stated constraint); this was anticipated in the constraints, not an issue.

## User Setup Required

None - no external service configuration required. The fix is fully config-driven within the existing `.env`/`tracked.toml` mechanism; no new environment variables are required (the two new ones are optional overrides with safe defaults already baked into `tracked.toml`).

## Next Phase Readiness

- GLM-4.7-Flash enrichment is unblocked: `load_config().tunables` now exposes `enrichment_max_tokens=1024, enrichment_disable_thinking=True` verified live against the real `config/tracked.toml`
- Full network-free/DB-free verification gate passes: `tests/test_llm_openai.py tests/test_config.py tests/test_enrich.py` — 36 passed
- No blockers. Live-GLM UAT (confirming a real production `python -m techtrend.enrich` run against the actual Z.ai endpoint produces `complete` rows instead of `fetch_failed` tombstones) remains a deploy-time verification the user can perform on the next scheduled/manual run — no test-suite work can substitute for that live check.

---
*Phase: quick-260822-s9h*
*Completed: 2026-08-22*

## Self-Check: PASSED

All 6 modified source files and 2 task commits (1c182e2, 4c843b2) verified present on disk and in git log.
