---
phase: 03-source-breadth-discourse-downloads-changelogs
verified: 2026-08-22T00:00:00Z
status: human_needed
score: 6/6 must-haves verified
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "Open the deployed dashboard after the daily Coolify scheduled task has run for several consecutive days and confirm HN/npm/PyPI/changelog rows actually appear ranked alongside GitHub rows with plausible momentum ordering."
    expected: "Rows with source='hn'/'npm'/'pypi'/'changelog' render in the table with correct labels ('Gained'/'Total' or em-dash), sorted sensibly, and are not visibly broken by real-world data shapes (e.g. a changelog feed with zero releases in a window, an npm package with a 0 first-week baseline)."
    why_human: "This requires live, multi-day scheduled collection against real external APIs (Algolia HN, npm registry, pypistats, vendor RSS/Atom feeds) and a running Coolify deployment — outside what a network-free code verification can exercise. All verification below confirms the code path is real and wired (not a stub); only live multi-day ranked data on the deployed dashboard remains unverified."
---

# Phase 3: Source Breadth — Discourse, Downloads & Changelogs Verification Report

**Phase Goal:** The dashboard reflects the project's full multi-source premise — Hacker News discourse, npm/PyPI download traction, and vendor changelog releases all appear alongside GitHub, flowing through the same identity-resolution, scoring, and enrichment pipeline with no changes to that pipeline's code (as revised per D3-5: minimal, documented deviations to the scorer, dashboard labels, and HTTP client only).

**Verified:** 2026-08-22
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | An HN collector, npm+PyPI collectors, and a changelog collector each exist, implement the `Collector` protocol, and are registered in `registry.py` (5 source_ids total) | ✓ VERIFIED | `techtrend/collectors/hn.py::HNCollector` (source_id="hn"), `techtrend/collectors/packages.py::NpmCollector`/`PyPiCollector` (source_id="npm"/"pypi"), `techtrend/collectors/changelog.py::ChangelogCollector` (source_id="changelog") each define `fetch()`/`normalize()`. `registry.py::COLLECTORS` = `[GitHubCollector(), HNCollector(), NpmCollector(), PyPiCollector(), ChangelogCollector()]` — 5 entries. `tests/test_collect_github.py::test_collectors_registry_has_all_five_phase3_entries_satisfying_protocol` asserts `len(COLLECTORS)==5`, `isinstance(c, Collector)` for each, and `source_ids == {"github","hn","npm","pypi","changelog"}` — ran green. |
| 2 | The scorer is source-parameterized (`compute_window_gain` takes `metric_name` resolved via `normalize.py::PRIMARY_METRIC`), so a non-'stars' metric can produce eligible scores | ✓ VERIFIED | `score.py::compute_window_gain(..., metric_name: str = "stars")` binds `metric_name` as a SQL parameter (no hardcoded `'stars'` literal). `rescore_all` resolves `primary_metric_for_source(entity["source"])` per entity and passes it through. `normalize.py::PRIMARY_METRIC` maps github→stars, hn→points, npm/pypi→downloads, changelog→releases. Regression pair in `tests/test_scoring.py`: `test_multi_source_non_stars_entity_ranks_after_rescore` (a changelog entity with a 'releases' series scores eligible=1, wilson_lower_bound>0) and `test_multi_source_entity_with_metric_stored_under_stars_does_not_rank` (identical series stored under 'stars' for the same entity does NOT rank) — both ran green, proving the fix is metric-selection-dependent, not just row-existence-dependent. |
| 3 | Cross-source dedup (COLL SC2) is deferred, and this descope is recorded honestly (dated note) rather than silently dropped | ✓ VERIFIED | `ROADMAP.md` Phase 3 SC2 is struck through with **"Deferred 2026-08-22 (D3-2)"** naming the reason (cross-source identity resolution hard/low-frequency) and pointing to REQUIREMENTS.md's v2 list. `REQUIREMENTS.md` line 20 carries a matching dated descope note cross-referencing D3-2 and clarifying it does not affect COLL-09 (within-source resolution, already satisfied). `REQUIREMENTS.md` line 77 extends the v2 "Cross-source entity resolution" bullet to explicitly cover this. Separate rows per source (no entity merging) is confirmed as intended v1 behavior, not a bug — matches `techtrend/pipeline/identity.py`'s per-`(source, source_native_id)` resolution (unchanged), and `queries.py`'s `query_ranked` returns one row per `entities.id`. |
| 4 | SC3 revision is limited to exactly three named touches (score.py metric_name, dashboard labels in queries.py+table.html, unauthenticated HTTP client), documented honestly; the GATE and ENRICHER were NOT changed; GITHUB_TOKEN stays confined to http.py | ✓ VERIFIED | `ROADMAP.md` Phase 3 SC3 struck through with **"Revised 2026-08-22 (D3-5)"** naming all three touches verbatim. `git diff 516a7d8~1..HEAD --name-only` (full Phase 3 commit range) shows the touched-file set is exactly: 4 new collector modules + registry.py + config.py + tracked.toml + pyproject.toml + normalize.py + score.py + queries.py + table.html + tests + fixtures + ROADMAP/REQUIREMENTS. `techtrend/pipeline/enrich.py` does NOT appear in that diff (0 changes) — enricher untouched. No `gate.py` file exists; the SCORE-03 floor gate lives inside `score.py::score_entity`, which was NOT touched beyond the pre-existing floor-then-bound logic (only `compute_window_gain`'s signature and `rescore_all`'s call site changed, per touch #1). `grep -rn GITHUB_TOKEN techtrend/collectors/*.py` returns matches only in `http.py` (plus one comment reference in `registry.py`'s docstring, not a read). `build_public_client()` in `http.py` never reads `GITHUB_TOKEN`; `build_client()`'s `_default_headers()` fail-loud requirement is untouched. |
| 5 | Full test suite passes (200 passed as reported by executors), and the new sources' tests are fixture-backed/network-free; registry-count assertion updated to 5 | ✓ VERIFIED | Ran `pytest tests/ -q` independently in this verification (Postgres 17 binaries on PATH for `pytest-postgresql`'s ephemeral cluster): **200 passed, exit code 0** — exactly matching 03-06-SUMMARY.md's claimed count. Ran the 5 new-source test files individually (`test_collect_hn.py` 7, `test_collect_packages.py` 13, `test_collect_changelog.py` 7, `test_collect_public_http.py` 7, `test_config.py` 8 = 42 passed). All three collectors' tests use `httpx.MockTransport` (HN, packages) or a local fixture file read directly by `feedparser.parse()` (changelog) — no live network call. Registry-count test confirmed (see truth 1). |
| 6 | `feedparser` added to `pyproject.toml`; changelog collector uses it | ✓ VERIFIED | `pyproject.toml` dependencies list contains `"feedparser==6.0.14"`. `techtrend/collectors/changelog.py` imports `feedparser` and calls `feedparser.parse(feed.url)` in `fetch()`, checks `parsed.bozo` for malformed-feed skip, and `count_entries_in_window()` reads `entry.get("published_parsed") or entry.get("updated_parsed")`. |

**Score:** 6/6 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `techtrend/collectors/hn.py` | HNCollector implementing Collector, metrics={"points": N} | ✓ VERIFIED | Exists, substantive, wired into registry.py, exercised by 7 fixture-backed tests |
| `techtrend/collectors/packages.py` | NpmCollector + PyPiCollector, metrics={"downloads": N} | ✓ VERIFIED | Exists, substantive, wired into registry.py, exercised by 13 fixture-backed tests |
| `techtrend/collectors/changelog.py` | ChangelogCollector, metrics={"releases": N} | ✓ VERIFIED | Exists, substantive, wired into registry.py, exercised by 7 fixture-backed tests |
| `techtrend/collectors/registry.py` | COLLECTORS list with 5 entries | ✓ VERIFIED | `[GitHubCollector(), HNCollector(), NpmCollector(), PyPiCollector(), ChangelogCollector()]` |
| `techtrend/pipeline/normalize.py` | PRIMARY_METRIC map + per-source converters | ✓ VERIFIED | `PRIMARY_METRIC` dict + `primary_metric_for_source()` + 4 converter dataclasses, all identity per D-13 |
| `techtrend/pipeline/score.py` | compute_window_gain parameterized by metric_name | ✓ VERIFIED | `metric_name: str = "stars"` keyword param; SQL uses bound `%s`, not a literal |
| `techtrend/server/queries.py` + `table.html` | Generalized dashboard labels | ✓ VERIFIED | "Stars"/"Stars gained" → "Total"/"Gained"; `stars_total` alias comment documents its new role; SORT_KEYS/URL contract unchanged |
| `techtrend/config.py` + `config/tracked.toml` | `[hn]`/`[packages]`/`[[changelogs]]` curated sections | ✓ VERIFIED | `HackerNews`/`Packages`/`ChangelogFeed` Pydantic models; tracked.toml seeds 14 HN keywords, 4 npm + 5 pypi packages, 8 changelog feeds |
| `pyproject.toml` | feedparser dependency | ✓ VERIFIED | `"feedparser==6.0.14"` present |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `registry.py` | 4 new collector modules | import + instantiation | ✓ WIRED | All 4 imported and instantiated at module load, side-effect-free per docstring claim |
| `pipeline/orchestrator.py` | `COLLECTORS` | iteration, `collector.source_id`/`.fetch()`/`.normalize()` only | ✓ WIRED | `grep` confirms orchestrator.py references only `collector.source_id`, `.fetch()`, `.normalize()` — no source-name literal branching |
| `score.py::rescore_all` | `normalize.py::primary_metric_for_source` | per-entity metric resolution | ✓ WIRED | Confirmed in rescore_all's loop body |
| `score.py::rescore_all` | `normalize.py::momentum_for_source` | per-entity momentum conversion | ✓ WIRED | Confirmed, unchanged call shape |
| `queries.py::query_ranked` | `table.html` | `stars_total`/`stars_gained` fields → "Total"/"Gained" columns | ✓ WIRED | Template renders `row['stars_total']` with em-dash fallback; header text generalized |
| HN/npm/PyPI collectors | `http.py::build_public_client`/`is_retryable_public` | shared unauthenticated client + retry predicate | ✓ WIRED | All three (HN, npm, PyPI) import and call `build_public_client()`; changelog collector has no client seam (feedparser manages its own I/O, documented deliberate omission) |

### Behavioral Spot-Checks / Test Execution

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full suite passes | `pytest tests/ -q` (Postgres 17 on PATH) | 200 passed, exit 0 | ✓ PASS |
| New-source tests are isolated and pass | `pytest tests/test_collect_hn.py tests/test_collect_packages.py tests/test_collect_changelog.py tests/test_collect_public_http.py tests/test_config.py -v` | 42 passed | ✓ PASS |
| Multi-source scoring regression (positive) | `pytest tests/test_scoring.py::test_multi_source_non_stars_entity_ranks_after_rescore` | included in full-suite pass | ✓ PASS |
| Multi-source scoring regression (negative) | `pytest tests/test_scoring.py::test_multi_source_entity_with_metric_stored_under_stars_does_not_rank` | included in full-suite pass | ✓ PASS |
| Registry has all 5 source_ids | `pytest tests/test_collect_github.py::test_collectors_registry_has_all_five_phase3_entries_satisfying_protocol` | included in full-suite pass | ✓ PASS |
| No live network calls in new tests | grep for `MockTransport`/local fixture usage | HN/packages use `httpx.MockTransport`; changelog reads a local XML fixture via `feedparser.parse(path)` | ✓ PASS |
| enrich.py untouched across Phase 3 | `git diff 516a7d8~1..HEAD --name-only` | `techtrend/pipeline/enrich.py` absent from the changed-file list | ✓ PASS |
| GITHUB_TOKEN confined to http.py | `grep -rn GITHUB_TOKEN techtrend/collectors/*.py` | only `http.py` reads it | ✓ PASS |

Note: `pytest -q` initially failed in this environment with `pg_config`/`pg_ctl` not found (no Postgres binaries on PATH by default). Resolved by prepending the locally-installed `C:\Program Files\PostgreSQL\17\bin` to PATH — an environment configuration issue, not a code defect. `tests/conftest.py` already documents the "initdb/pg_ctl found on PATH" assumption.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| COLL-03 | 03-01, 03-02, 03-04 | HN collection | ✓ SATISFIED | HNCollector implemented, registered, tested |
| COLL-04 | 03-01, 03-02, 03-05 | npm/PyPI download collection | ✓ SATISFIED | NpmCollector/PyPiCollector implemented, registered, tested |
| COLL-05 | 03-01, 03-02, 03-06 | Vendor changelog collection | ✓ SATISFIED | ChangelogCollector implemented, registered, tested |

No orphaned requirements — REQUIREMENTS.md's Phase 3 mapping (COLL-03/04/05) exactly matches what the six plans collectively declared. `REQUIREMENTS.md` checkbox column for COLL-03/04/05 is still unchecked `[ ]`, and `ROADMAP.md`'s Phase 3 checkbox/plan checkboxes/progress-table row are also still unmarked (`[ ]`, "0/TBD", "Not started") despite all 6 plans being complete with passing tests and verified commits. This is expected pre-closure bookkeeping (matches the pattern of Phases 1/2/4, which show `[x]` only after their own VERIFICATION.md existed) and is not treated as a gap — it is the orchestrator's job to update these once this verification is accepted.

### Anti-Patterns Found

None. Scanned all Phase-3-touched source files (`hn.py`, `packages.py`, `changelog.py`, `registry.py`, `http.py`, `normalize.py`, `score.py`, `queries.py`, `table.html`, `config.py`) for TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER/"not yet implemented"/"coming soon" — zero matches.

### Human Verification Required

### 1. Live multi-day ranked dashboard data across all five sources

**Test:** After the Coolify Scheduled Task has fired `python -m techtrend.daily` for several consecutive days against the real Algolia HN API, npm registry, pypistats, and the 8 curated changelog feeds, open the deployed dashboard and inspect the ranked list.

**Expected:** HN stories, npm/PyPI packages, and changelog feed entities appear as ranked rows alongside GitHub repos, each showing a sensible "Total"/"Gained" value (or em-dash for non-GitHub rows, as designed), sorted correctly, with no rendering errors on real-world edge cases (e.g., a changelog feed with 0 releases in the trailing window, a brand-new HN keyword hit with only 1 day of history).

**Why human:** This requires live network calls against four external APIs and multi-day scheduled execution on the hosted Coolify deployment — explicitly out of scope for this network-free code verification per the task's own instructions. Everything the code path depends on (collectors, scorer parameterization, dashboard rendering, registry wiring) has been verified structurally and via fixture-backed tests; only the live, cumulative, multi-day data shape on the real deployed dashboard remains unverified.

### Gaps Summary

No gaps found. All 6 observable truths derived from the phase goal, ROADMAP success criteria (as honestly revised/deferred per D3-2/D3-5), and REQUIREMENTS COLL-03/04/05 are verified against the actual codebase — not just SUMMARY.md claims. The full test suite (200 tests) passes green when run independently in this verification session, including the two-sided multi-source scoring regression test that specifically proves the SC1 mechanism (per-source metric_name resolution) rather than merely proving rows exist. The SC2 deferral and SC3 revision are both recorded with dated, specific notes in ROADMAP.md and REQUIREMENTS.md, matching the project's established honest-supersession convention. The enricher and ranking gate are confirmed untouched via a full commit-range diff, and GITHUB_TOKEN is confirmed confined to `http.py`. The only open item is the deploy-time UAT for live multi-day data, which is expected and explicitly out of this verification's scope per the task instructions — routed to human_verification rather than treated as a gap.

---

_Verified: 2026-08-22_
_Verifier: Claude (gsd-verifier)_
