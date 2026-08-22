---
phase: 03-source-breadth-discourse-downloads-changelogs
plan: 02
subsystem: config-and-http
tags: [config, pydantic, httpx, hn, npm, pypi, changelog]

# Dependency graph
requires:
  - phase: 03-source-breadth-discourse-downloads-changelogs
    plan: 01
    provides: normalize.py::PRIMARY_METRIC lookup + identity converters for hn/npm/pypi/changelog (scorer already accepts these sources)
provides:
  - "config.hn.keywords / config.hn.lookback_days (D3-4 HN source list)"
  - "config.packages.npm / config.packages.pypi (D3-4 package source list)"
  - "config.changelogs: list[ChangelogFeed] (D3-4 curated feed list, label+url)"
  - "techtrend.collectors.http.build_public_client() -- unauthenticated httpx.Client, no GITHUB_TOKEN lookup"
  - "techtrend.collectors.http.is_retryable_public() -- 429/5xx retry, 4xx permanent"
affects: [03-03, 03-04, 03-05, 03-06]

# Tech tracking
tech-stack:
  added: []
  patterns: ["unauthenticated public-API client builder as a sibling to the existing GitHub-token client builder in http.py, keeping GITHUB_TOKEN confined to one file"]

key-files:
  created:
    - tests/test_collect_public_http.py
  modified:
    - techtrend/config.py
    - config/tracked.toml
    - techtrend/collectors/http.py
    - tests/test_config.py

key-decisions:
  - "HackerNews/Packages/ChangelogFeed models each carry field defaults (mirroring the existing Tunables discipline) so a partial tracked.toml still validates"
  - "build_public_client() is a wholly separate builder from build_client(), not a parameterization of it -- GitHub's fail-loud token requirement and _default_headers() are untouched"
  - "No hishel caching for the public client -- these APIs are polled at most once/day, so a plain httpx.HTTPTransport() is sufficient; caching stays a GitHub-only concern for now"
  - "is_retryable_public() is a new sibling predicate, not a reuse of GitHub's is_retryable -- it never treats 403 as transient (even with x-ratelimit-remaining:0), since these public APIs don't use GitHub's rate-limit-header convention"
  - "Changelog feeds seed GitHub Releases .atom for Anthropic/Ollama in place of their nonexistent blog RSS (both confirmed 404 in RESEARCH.md) -- documented inline in tracked.toml"

requirements-completed: [COLL-03, COLL-04, COLL-05]

coverage:
  - id: D1
    description: "load_config() returns validated curated source lists for HN keywords, npm+PyPI package names, and changelog feed URLs; real tracked.toml seeds no known-404 feed"
    requirement: COLL-03
    verification:
      - kind: unit
        ref: "tests/test_config.py::test_real_tracked_toml_exposes_hn_packages_changelogs"
        status: pass
      - kind: unit
        ref: "tests/test_config.py::test_partial_toml_with_only_hn_section_still_validates"
        status: pass
    human_judgment: false
  - id: D2
    description: "A new collector can obtain an httpx.Client for unauthenticated public APIs without GITHUB_TOKEN being set; GitHub client's token requirement is unchanged"
    requirement: COLL-04
    verification:
      - kind: unit
        ref: "tests/test_collect_public_http.py::test_build_public_client_works_with_github_token_unset"
        status: pass
      - kind: unit
        ref: "tests/test_collect_public_http.py::test_build_public_client_sends_no_authorization_header"
        status: pass
      - kind: static
        ref: "grep -n GITHUB_TOKEN techtrend/collectors/*.py -- only http.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "The public retry predicate retries 429 + 5xx and treats other 4xx (including a GitHub-style 403 rate-limit header) as permanent"
    requirement: COLL-05
    verification:
      - kind: unit
        ref: "tests/test_collect_public_http.py::test_is_retryable_public_500_is_retried, test_is_retryable_public_429_is_retried, test_is_retryable_public_404_not_retried, test_is_retryable_public_403_not_retried"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-08-22
status: complete
---

# Phase 3 Plan 02: Source Breadth — Config & Public HTTP Client Substrate Summary

**Added curated `[hn]`/`[packages]`/`[[changelogs]]` config sections with matching Pydantic models (D3-4), and a separate unauthenticated `httpx.Client` builder + public-API retry predicate in `http.py` that never touches `GITHUB_TOKEN` — the shared substrate the three Wave-2 collectors (HN, npm/PyPI, changelog) depend on.**

## Performance

- **Duration:** ~20 min
- **Tasks:** 3 completed
- **Files modified:** 4 (1 created)

## Accomplishments
- `techtrend/config.py`: new `HackerNews` (`keywords`, `lookback_days=7`), `Packages` (`npm`, `pypi`), and `ChangelogFeed` (`label`, `url`) Pydantic models, hung off `Config` as `hn`, `packages`, `changelogs` — each with a default so a partial config still validates
- `config/tracked.toml`: `[hn]` seeded from an extended `[discovery].keywords` list (14 terms, including a few HN-specific ones like "claude code"/"cursor"/"aider"), `[packages]` with a starter npm (4) + pypi (5) AI-coding package list, and 8 `[[changelogs]]` entries seeded only from RESEARCH's verified-live feed URLs — GitHub Releases `.atom` used for Anthropic (`claude-code`) and Ollama in place of their nonexistent blog RSS, with an inline comment explaining the substitution; neither known-404 URL (`anthropic.com/rss.xml`, `ollama.com/blog/rss`) was seeded
- `techtrend/collectors/http.py`: added `build_public_client(*, transport=None, timeout=30.0)` — a plain `httpx.Client` with only a `User-Agent` header, no token lookup, callable with `GITHUB_TOKEN` entirely unset — and `is_retryable_public(exc)`, a sibling retry predicate (429 + 5xx retryable; 403/404/other 4xx permanent) distinct from GitHub's `is_retryable`. `build_client()`, `_default_headers()`, and `MissingGithubTokenError` were not modified.
- `tests/test_config.py` (extended) and `tests/test_collect_public_http.py` (new): 15 tests total covering config-load against the real `tracked.toml`, a partial-TOML validation case, the public client's `GITHUB_TOKEN`-unset path via `httpx.MockTransport`, absence of an `Authorization` header, presence of a `User-Agent`, and `is_retryable_public` parametrized over 500/429/404/403 (explicitly including a 403 with `x-ratelimit-remaining: 0` to prove it does NOT reuse GitHub's convention)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add curated config sections + Pydantic models for the three sources (D3-4)** - `12c2945` (feat)
2. **Task 2: Add an unauthenticated public HTTP client + public retry predicate to http.py** - `0b5bc41` (feat)
3. **Task 3: Tests for config loading and the public client/predicate** - `15f7180` (test)

_Note: Task 3 is tagged `tdd="true"` in the plan, but its own `<action>` describes writing tests for behavior already built in Tasks 1-2 (config models, public client) — there is no separate RED-then-GREEN split within Task 3 itself; the task's single commit is both the test addition and its passing verification, matching the plan's own `<verify>`/`<done>` blocks._

## Files Created/Modified
- `techtrend/config.py` - `HackerNews`/`Packages`/`ChangelogFeed` models + `hn`/`packages`/`changelogs` fields on `Config`
- `config/tracked.toml` - `[hn]`, `[packages]`, `[[changelogs]]` curated sections
- `techtrend/collectors/http.py` - `build_public_client()` + `is_retryable_public()`
- `tests/test_config.py` - two new tests for the D3-4 config sections
- `tests/test_collect_public_http.py` (new) - 8 tests for the public client + retry predicate

## Decisions Made
- HN keywords extend (not replace) `[discovery].keywords` — same AI-coding vocabulary, since Algolia search matches free text against story titles rather than a GitHub name/description scan; a few HN-specific terms ("claude code", "cursor", "aider") were added since those tool names are unlikely to appear in GitHub topic/description text the way they appear in HN story titles
- `build_public_client()` has no caching seam (no hishel) — these three APIs are polled at most once/day per the project's daily cadence, so a bare `httpx.HTTPTransport()` is sufficient; this keeps the builder minimal and avoids sharing GitHub's `.hishel/github.db` cache state with unrelated sources
- `is_retryable_public` explicitly does NOT retry 403 even with GitHub's `x-ratelimit-remaining: 0` header present — Algolia/npm/pypistats don't use that convention, and silently reusing GitHub's predicate would risk retrying a permission-denied response from a different API in a way that has no defined meaning there

## Deviations from Plan

None - plan executed exactly as written. All three tasks matched their `<action>`/`<verify>`/`<done>` blocks; no Rule 1-4 fixes were needed.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required. `GITHUB_TOKEN` remains required only for the existing GitHub collector path; the three new sources this plan unblocks are unauthenticated.

## Next Phase Readiness
- Wave-2 collectors (HN, npm/PyPI, changelog) can now call `load_config()` for their curated source lists and `build_public_client()`/`is_retryable_public()` for their HTTP needs — both shared blockers named in this plan's objective are closed.
- `registry.py`, `normalize.py`'s converter wiring (already done in 03-01), and the three collector modules themselves remain out of scope for this plan and belong to the Wave-2 plans (03-03 through 03-06).
- Full project test suite (`pytest -q`, all files, Postgres-backed) passes green (exit code 0) after this plan's changes, confirming no regression outside the touched files.

---
*Phase: 03-source-breadth-discourse-downloads-changelogs*
*Completed: 2026-08-22*

## Self-Check: PASSED

All created/modified files confirmed present on disk; all three task commit hashes (12c2945, 0b5bc41, 15f7180) confirmed present in `git log --oneline --all`.
