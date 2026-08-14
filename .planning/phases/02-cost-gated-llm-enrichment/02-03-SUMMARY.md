---
phase: 02-cost-gated-llm-enrichment
plan: 03
subsystem: pipeline
tags: [httpx, tenacity, hishel, github-api, content-hash, anti-fabrication]

# Dependency graph
requires:
  - phase: 02-01
    provides: enrichments cache table, Tunables.grounding_char_cap, Wave 0 failing test scaffolds for pipeline.grounding
  - phase: 01-foundation
    provides: collectors/http.py::build_client()/is_retryable (GitHub auth/cache/retry layer), GITHUB_TOKEN isolation pattern
provides:
  - "techtrend/pipeline/grounding.py: extract_intro(readme_text, char_cap), normalize_for_hash(description, readme_intro), fetch_grounding(client, full_name, char_cap)"
  - "Anti-fabrication contract for enrichment: fetch_grounding returns None when there is nothing real to summarize"
  - "Stable content-hash input (normalize_for_hash) for Plan 02-04's sha256 cache key"
affects: [02-04, 02-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Grounding fetch reuses collectors/github.py's tenacity _RETRY_KWARGS + explicit httpx.HTTPStatusError 404->None handling verbatim, without re-declaring GITHUB_TOKEN (T-01-12 isolation, verified via a zero-count grep including comments)"
    - "fetch_grounding takes client as a required parameter (no lazy build_client() fallback inside the function) -- production callers construct via build_client() and pass it in; tests inject an httpx.MockTransport-backed client directly"

key-files:
  created:
    - techtrend/pipeline/grounding.py
  modified:
    - tests/test_grounding.py

key-decisions:
  - "fetch_grounding(client, full_name, char_cap) takes char_cap as a required parameter with no hardcoded default -- the single default (2000) lives in Tunables.grounding_char_cap (D-15); duplicating it as a code-level default would create two sources of truth"
  - "Wave 0 did not scaffold fetch_grounding tests (only extract_intro/normalize_for_hash were scaffolded) -- added two tests to tests/test_grounding.py in this plan, following the same RED-before-implementation discipline as Wave 0, committed as a separate test(...) commit before the feat(...) implementation commit"
  - "Docstrings referencing the GitHub auth env var are paraphrased ('the GitHub auth token env var') rather than spelling the literal name, matching github.py's own docstring convention -- the plan's acceptance-criteria grep counts the literal string anywhere in the file, including comments/docstrings, not just code"

requirements-completed: [ENR-05]

coverage:
  - id: D1
    description: "extract_intro returns the README's top section (before the first H2+ heading), truncated to char_cap, keeping the H1 title"
    requirement: "ENR-05"
    verification:
      - kind: unit
        ref: "tests/test_grounding.py::test_extract_intro_truncates_at_first_deep_heading"
        status: pass
      - kind: unit
        ref: "tests/test_grounding.py::test_extract_intro_respects_char_cap"
        status: pass
    human_judgment: false
  - id: D2
    description: "normalize_for_hash strips markdown badge images and HTML comments and collapses whitespace before hashing, so CI-badge churn never registers as a content change"
    requirement: "ENR-05"
    verification:
      - kind: unit
        ref: "tests/test_grounding.py::test_normalize_for_hash_strips_badges_and_comments_and_collapses_whitespace"
        status: pass
      - kind: unit
        ref: "tests/test_grounding.py::test_normalize_for_hash_is_stable_across_badge_only_changes"
        status: pass
    human_judgment: false
  - id: D3
    description: "fetch_grounding returns (description, extracted_intro) on a successful fetch, and returns None when description is empty AND the README is unfetchable/empty -- the anti-fabrication signal for the caller to skip the LLM entirely"
    requirement: "ENR-05"
    verification:
      - kind: unit
        ref: "tests/test_grounding.py::test_fetch_grounding_returns_description_and_intro_on_success"
        status: pass
      - kind: unit
        ref: "tests/test_grounding.py::test_fetch_grounding_returns_none_when_description_and_readme_both_empty"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-08-14
status: complete
---

# Phase 2 Plan 3: Grounding Layer Summary

**`techtrend/pipeline/grounding.py`: fetch a repo's description + README intro through the existing GitHub HTTP client, extract the top section, and normalize it into a stable content-hash input that survives CI-badge churn.**

## Performance

- **Duration:** 20 min
- **Completed:** 2026-08-14
- **Tasks:** 2
- **Files modified:** 2 (1 created, 1 test file extended)

## Accomplishments
- `extract_intro(readme_text, char_cap)`: returns the README's top section (everything before the first `## `-or-deeper heading), truncated to `char_cap`, keeping an H1 title if present.
- `normalize_for_hash(description, readme_intro)`: strips markdown badge images (`![...](...)`), strips HTML comments, collapses whitespace runs to single spaces, so a repo's badge/CI-status flipping never registers as a content change for the (entity, content_hash) cache key Plan 02-04 will compute.
- `fetch_grounding(client, full_name, char_cap)`: fetches repo metadata + README raw text via the GitHub REST API, reusing `collectors/http.py::is_retryable`/`build_client()`-constructed clients and `collectors/github.py`'s exact tenacity retry config and explicit 404-as-None README handling. Returns `(description, extracted_intro)` on success, or `None` when both the description and README are empty/unfetchable — the anti-fabrication signal (D-08) the enrichment orchestrator (Plan 02-04) uses to skip the LLM call and write a `fetch_failed` tombstone instead.
- The GitHub auth token env var is never read in this module (`grep -c "GITHUB_TOKEN" techtrend/pipeline/grounding.py` returns 0) — isolation to `collectors/http.py` (T-01-12) is preserved, and the module's own docstrings paraphrase the env var name rather than spelling it literally, to keep that grep meaningful.

## Task Commits

Each task was committed atomically:

1. **Task 1: extract_intro and normalize_for_hash pure functions** - `a4510d7` (feat)
2. **Task 2: fetch_grounding via the existing GitHub HTTP layer** - `ebf3ebd` (test, RED) + `ad081d6` (feat, GREEN)

**Plan metadata:** pending (docs: complete plan)

_Note: Task 2 required two commits (test → feat) since Wave 0 did not scaffold `fetch_grounding` tests — see Deviations below._

## Files Created/Modified
- `techtrend/pipeline/grounding.py` - New: `extract_intro`, `normalize_for_hash`, `fetch_grounding` (+ private `_get_metadata`/`_get_readme_text` tenacity-decorated fetch helpers, copied from `collectors/github.py`'s pattern)
- `tests/test_grounding.py` - Extended with two `fetch_grounding` tests (success + empty/unfetchable) driven through `httpx.MockTransport`, no live GitHub call

## Decisions Made
- `fetch_grounding`'s `char_cap` parameter is required, with no hardcoded default — the one canonical default (2000) lives in `Tunables.grounding_char_cap` (D-15); a code-level default here would be a second source of truth for the same number.
- `client` is a required parameter (not `client: httpx.Client | None = None` with an internal `build_client()` fallback) — the plan's stated intent was for tests to inject a fake/mock client directly, and the production caller (Plan 02-04's `pipeline/enrich.py`) is expected to construct the client once via `build_client()` and pass it into every `fetch_grounding` call for the run, rather than each call building its own client.
- Docstrings describing the GitHub-auth-isolation invariant paraphrase the env var name instead of spelling it literally, matching `collectors/http.py`'s own docstring convention — the plan's acceptance-criteria grep (`grep -c "GITHUB_TOKEN" techtrend/pipeline/grounding.py` == 0) counts every literal occurrence in the file, comments included.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Added the missing `fetch_grounding` Wave 0 test scaffolds**
- **Found during:** Task 2 (fetch_grounding via the existing GitHub HTTP layer)
- **Issue:** The plan's `read_first` for Task 2 references "tests/test_grounding.py (the fetch test using httpx.MockTransport / injected client)" as if it already existed, and the task has `tdd="true"`. But Wave 0 (Plan 02-01) only scaffolded `extract_intro`/`normalize_for_hash` tests — `RESEARCH.md`'s own "Wave 0 Gaps" list confirms `test_grounding.py` was scoped to `extract_intro`, `normalize_for_hash`, and badge-stripping only, with no `fetch_grounding` test mentioned. Implementing `fetch_grounding` without a RED test first would have skipped the plan's own TDD requirement for this task.
- **Fix:** Wrote two tests (`test_fetch_grounding_returns_description_and_intro_on_success`, `test_fetch_grounding_returns_none_when_description_and_readme_both_empty`) mirroring `tests/test_collect_github.py`'s `httpx.MockTransport` + `build_client()` style, confirmed they failed with `ImportError` (RED), committed them in a standalone `test(02-03)` commit, then implemented `fetch_grounding` to turn them green (GREEN), matching the plan's `tdd="true"` requirement exactly.
- **Files modified:** `tests/test_grounding.py`
- **Verification:** `pytest -q tests/test_grounding.py` — all 6 tests pass (4 Wave 0 + 2 new).
- **Committed in:** `ebf3ebd` (RED, test-only commit) and `ad081d6` (GREEN, feat commit)

---

**Total deviations:** 1 auto-fixed (Rule 2 — missing critical functionality: the TDD RED step the task itself required)
**Impact on plan:** Necessary to satisfy the task's own `tdd="true"` contract given Wave 0's actual scope. No scope creep — the two added tests cover exactly the `fetch_grounding` behavior described in the plan's `<behavior>` block, nothing beyond it.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required this plan (`GITHUB_TOKEN` is required only for a live enrichment run, same deferred-UAT pattern established in Phase 1; all tests here use `httpx.MockTransport`, no live call).

## Next Phase Readiness
- `techtrend/pipeline/grounding.py` is ready for Plan 02-04's orchestration loop (`pipeline/enrich.py`) to call `fetch_grounding` per candidate entity, feed its output through `normalize_for_hash` + `hashlib.sha256` for the cache key, and pass the (unstripped, truncated) intro to Plan 02-04/02-05's `pipeline/llm.py::enrich_item`.
- `pytest -q` full suite: `tests/test_grounding.py` fully green (6/6). Remaining failures are the pre-existing, expected Wave 0 RED tests for not-yet-implemented modules/behavior in other plans of this phase (`tests/test_llm.py` — 3, `tests/test_enrich.py` — 4, `tests/test_dashboard.py` — 2) — none caused by this plan's changes.
- No blockers.

---
*Phase: 02-cost-gated-llm-enrichment*
*Completed: 2026-08-14*

## Self-Check: PASSED
