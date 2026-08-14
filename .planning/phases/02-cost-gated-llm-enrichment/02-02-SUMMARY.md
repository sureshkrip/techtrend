---
phase: 02-cost-gated-llm-enrichment
plan: 02
subsystem: api
tags: [anthropic, llm, structured-outputs, pydantic, haiku-4-5]

# Dependency graph
requires:
  - phase: 02-cost-gated-llm-enrichment
    provides: "Wave 0 test_llm.py contract (EnrichmentResult, enrich_item, build_section_result_model signatures), seven-section taxonomy in config, enrichment Tunables (02-01)"
provides:
  - "techtrend/pipeline/llm.py: EnrichmentResult/Confidence schema, build_llm_client() optional-injection seam, build_section_result_model() per-request section-enum builder, enrich_item() single messages.parse() call"
  - "anthropic==0.122.0 pinned dependency, installed in project .venv"
  - "ANTHROPIC_API_KEY declared in .env.example, isolated to pipeline/llm.py"
affects: [02-04, 02-05]

# Tech tracking
tech-stack:
  added: ["anthropic==0.122.0"]
  patterns:
    - "Per-request StrEnum built from config-driven ids and bound via a dynamic Pydantic subclass (build_section_result_model), so the JSON-schema enum enforcement always tracks the current config/tracked.toml section list"
    - "Env-var secret isolation for ANTHROPIC_API_KEY, mirroring collectors/http.py's GITHUB_TOKEN pattern (custom MissingAnthropicKeyError, optional-client injection)"

key-files:
  created:
    - techtrend/pipeline/llm.py
  modified:
    - pyproject.toml
    - .env.example
    - uv.lock

key-decisions:
  - "T-02-SC package-legitimacy checkpoint (Task 1) approved by user before this continuation began -- anthropic confirmed as the official anthropics/anthropic-sdk-python SDK, the CLAUDE.md-locked LLM choice"
  - "build_section_result_model() exposed as a public top-level function (not inlined in enrich_item) per the Wave 0 test contract, so the per-request section-enum enforcement is unit-testable via a fake client with no live API call"
  - "Confidence modeled as a three-value StrEnum (high/medium/low), not a numeric range -- Anthropic structured-outputs JSON Schema has no minimum/maximum support (RESEARCH.md Pitfall 2)"
  - "No tenacity wrapper around client.messages.parse() -- the anthropic SDK already retries 429/5xx internally, matching CLAUDE.md's 'What NOT to Use' guidance"

requirements-completed: [ENR-03, ENR-04]

coverage:
  - id: D1
    description: "enrich_item() returns an EnrichmentResult with fixed-role summary_line_1 (what)/summary_line_2 (why) and a config-enforced section id for a valid (non-refusal) structured-output response"
    requirement: "ENR-03"
    verification:
      - kind: unit
        ref: "tests/test_llm.py::test_enrich_item_returns_two_line_summary"
        status: pass
    human_judgment: false
  - id: D2
    description: "build_section_result_model(section_ids) constrains the section field to exactly the given ids via a JSON-schema enum -- a value outside the set raises a Pydantic ValidationError, not a fuzzy/free-text match"
    requirement: "ENR-04"
    verification:
      - kind: unit
        ref: "tests/test_llm.py::test_section_constrained_to_enum"
        status: pass
    human_judgment: false
  - id: D3
    description: "enrich_item() checks stop_reason == 'refusal' before reading parsed_output and returns None on refusal -- never fabricates a summary or section (D-08/SC3)"
    verification:
      - kind: unit
        ref: "tests/test_llm.py::test_refusal_returns_none"
        status: pass
    human_judgment: false
  - id: D4
    description: "anthropic==0.122.0 pinned in pyproject.toml, installed in the project .venv, and importable"
    verification:
      - kind: other
        ref: "python -c \"import anthropic; assert anthropic.__version__=='0.122.0'\""
        status: pass
    human_judgment: false
  - id: D5
    description: "ANTHROPIC_API_KEY literal confined to techtrend/pipeline/llm.py; no tenacity wrapper around the LLM call"
    verification:
      - kind: other
        ref: "grep -rln ANTHROPIC_API_KEY techtrend/ | grep -v pipeline/llm.py (no output); grep -c tenacity techtrend/pipeline/llm.py (0)"
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-08-14
status: complete
---

# Phase 2 Plan 2: LLM Layer Summary

**Anthropic Messages API wrapper turning fetched README/description text into a grounded two-line summary and a schema-forced one-of-seven section via a single `client.messages.parse()` call.**

## Performance

- **Duration:** 12 min (this continuation, from checkpoint approval to completion; Task 1's checkpoint wait is excluded)
- **Completed:** 2026-08-14
- **Tasks:** 3 (Task 1 checkpoint approved by prior session; Tasks 2-3 executed this session)
- **Files modified:** 4 (pyproject.toml, .env.example, uv.lock, techtrend/pipeline/llm.py)

## Accomplishments
- `anthropic==0.122.0` pinned in `pyproject.toml`, installed into the project `.venv` via `uv sync`, and confirmed importable at the pinned version.
- `ANTHROPIC_API_KEY=` entry added to `.env.example`, mirroring the existing `GITHUB_TOKEN` entry's format and comment style; no real key committed.
- `techtrend/pipeline/llm.py` created: `Confidence` StrEnum, `EnrichmentResult` Pydantic model, `MissingAnthropicKeyError`, `build_llm_client()`, `build_section_result_model()`, and `enrich_item()` -- the single structured Haiku 4.5 call that returns `{summary_line_1, summary_line_2, section, confidence}`.
- All three Wave 0 RED tests in `tests/test_llm.py` now pass (two-line summary, section-enum enforcement, refusal handling), with no live API call made anywhere in the test file.

## Task Commits

Each task was committed atomically:

1. **Task 1: Anthropic package legitimacy checkpoint (T-02-SC)** - checkpoint approved by user; no commit (gate-only task)
2. **Task 2: Pin and install anthropic; declare ANTHROPIC_API_KEY** - `9c13994` (chore)
3. **Task 3: LLM client wrapper, structured schema, and grounded prompt** - `9cd1d56` (feat)

**Plan metadata:** pending (docs: complete plan)

## Files Created/Modified
- `techtrend/pipeline/llm.py` - New: Anthropic Messages API client wrapper, `EnrichmentResult`/`Confidence` schema, `build_llm_client`/`build_section_result_model`/`enrich_item`
- `pyproject.toml` - Added `anthropic==0.122.0` to `[project].dependencies`
- `.env.example` - Added `ANTHROPIC_API_KEY=` entry mirroring `GITHUB_TOKEN`
- `uv.lock` - Regenerated by `uv sync` to include `anthropic` + its transitive deps (`distro`, `docstring-parser`, `jiter`, `sniffio`)

## Decisions Made
- `build_section_result_model()` is exposed as a public function (per the Wave 0 test contract from 02-01) rather than an inline class inside `enrich_item`, so the per-request section-enum enforcement is directly unit-testable.
- Confidence stays a three-value enum, not a numeric range -- Anthropic's structured-outputs JSON Schema has no `minimum`/`maximum` support (RESEARCH.md Pitfall 2); the numeric threshold requirement is satisfied instead by `Tunables.confidence_flag_threshold` (already added in 02-01).
- `enrich_item()`'s system prompt wraps `description`/`readme_intro` in `<repo_description>`/`<readme_excerpt>` XML tags and explicitly instructs the model to treat their contents as untrusted data, not instructions (T-02-03 mitigation, defense-in-depth against prompt injection from a malicious README).
- No `tenacity` wrapper around the `messages.parse()` call -- the `anthropic` SDK already retries 429/5xx internally, per CLAUDE.md's "What NOT to Use" table and RESEARCH.md's "Don't Hand-Roll" guidance.

## Deviations from Plan

None - plan executed exactly as written. This was a continuation agent picking up after Task 1's blocking-human checkpoint was approved; Tasks 2 and 3 were executed per the plan with no auto-fixes needed.

## Issues Encountered
None.

## User Setup Required
None this plan beyond the already-approved Task 1 checkpoint -- the user still needs to populate a real `ANTHROPIC_API_KEY` in their local `.env` before any live enrichment run (no live call is made by this plan or its tests; a real key is only needed once Plan 02-04 wires `enrich_item` into the orchestration loop and Plan 02-05 or later actually executes `python -m techtrend.enrich` against real data).

## Next Phase Readiness
- `techtrend/pipeline/llm.py`'s `enrich_item(client, *, model, sections, description, readme_intro) -> EnrichmentResult | None` signature is locked and ready for Plan 02-04's `pipeline/enrich.py` orchestration loop to call via its `llm_call_fn` injection seam (per 02-01's Wave 0 contract).
- `pytest -q` full suite: `tests/test_llm.py` fully green (3/3); remaining failures are the pre-existing, out-of-scope Wave 0 RED tests for `tests/test_enrich.py` (Plan 02-04) and the two `test_dashboard.py` scaffolds (Plan 02-05) -- unchanged by this plan, exactly the expected state per 02-01-SUMMARY.md.
- No blockers.

---
*Phase: 02-cost-gated-llm-enrichment*
*Completed: 2026-08-14*

## Self-Check: PASSED

All files verified present on disk (`techtrend/pipeline/llm.py`, updated `pyproject.toml`/`.env.example`/`uv.lock`); both task commits (`9c13994`, `9cd1d56`) verified present in git history.
