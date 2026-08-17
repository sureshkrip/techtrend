---
phase: 02-cost-gated-llm-enrichment
verified: 2026-08-15T00:00:00Z
status: passed
score: 4/4 must-haves verified (mechanism-level); 1 behavior-dependent item present-but-unverified (SC3 live anti-fabrication + visual walkthrough)
behavior_unverified: 1
overrides_applied: 0
behavior_unverified_items:

  - truth: "A summary for a brand-new or obscure tool reflects its actual fetched README/changelog/thread text, not a plausible-sounding fabrication from the model's own training knowledge (SC3)."
    test: "Run `python -m techtrend.enrich` against real eligible entities with a real ANTHROPIC_API_KEY, then compare 2-3 rendered summaries against each repo's actual README intro."
    expected: "Every claim in summary_line_1/summary_line_2 is traceable to the fetched description/README text; nothing echoes plausible-sounding but unsupported claims."
    why_human: "No ANTHROPIC_API_KEY / no live-enriched rows exist in this environment. The anti-fabrication mechanism (grounded prompt, refusal->None, empty-grounding->skip) is verified in code and by unit test, but whether Haiku 4.5 actually stays grounded on real, messy README text can only be judged by reading real model output next to the real source text."
human_verification:

  - test: "Live section browsing + anti-fabrication summary spot-check (already tracked in STATE.md's Deferred Items, 02-05 Task 3)"
    expected: "Sidebar counts match table rows per section; sort+section persist together; a low-confidence flag is spottable; 2-3 real summaries are traceable to real README text; unenriched rows show honest fallbacks and are never dropped."
    why_human: "Requires ANTHROPIC_API_KEY plus a fresh collect/score/enrich run against real data — unavailable in this environment. The 02-05 checkpoint was structurally accepted (tests + greps + static template review) rather than run live."
cr01_resolution: "RESOLVED 2026-08-15 (commit aeddf6a). User chose 'Fix now' at the execute-phase verification gate. `Tunables.enrichment_cap` now carries `Field(default=15, gt=0)`; `tests/test_enrich.py::test_enrichment_cap_rejects_non_positive` locks the boundary (0/-1/-15 rejected, 1 accepted). No longer a pending human item."
---

# Phase 2: Cost-Gated LLM Enrichment Verification Report

**Phase Goal:** High-velocity items surviving the ranking gate receive a grounded two-line summary and a section assignment, within a hard-capped LLM budget, and enrichment problems never cost the user visibility into already-ranked data.
**Verified:** 2026-08-15
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Only items clearing the ranking threshold, never more than the hard cap, are sent to the LLM | ✓ VERIFIED (mechanism), ⚠️ see CR-01 note | `techtrend/pipeline/enrich.py::_SELECT_CANDIDATES_SQL` filters `eligible=1 AND score_version=CURRENT` and applies `LIMIT :enrichment_cap` **on the candidate SET before any fetch**; verified by `tests/test_enrich.py::test_gate_reads_eligible_seam` and `::test_cap_limits_candidate_set` (both pass). Cap default/current config value is `15` (positive) in `config/tracked.toml`. **Caveat:** `Tunables.enrichment_cap` has no `Field(gt=0)` validation (02-REVIEW.md CR-01, unresolved) — a negative value in the hand-edited config would make SQLite's `LIMIT` unbounded, defeating the cap. Does not currently violate this truth under the shipped config; flagged as a human decision item below. |
| 2 | Each enriched item shows a two-line summary + one-of-seven section; dashboard browsable/filterable by section | ✓ VERIFIED | `techtrend/pipeline/llm.py::EnrichmentResult` fixes `summary_line_1`("what")/`summary_line_2`("why"); `build_section_result_model()` builds a per-request StrEnum from `config.sections` so `section` cannot be outside the seven ids (`tests/test_llm.py::test_enrich_item_returns_two_line_summary`, `::test_section_constrained_to_enum` pass). `techtrend/server/queries.py::query_ranked(section=...)` filters via bound `:section`; `query_section_counts()` feeds the sidebar; `partials/sidebar.html` renders "All" + seven sections with live counts (`tests/test_dashboard.py::test_section_filter` passes; verified `config/tracked.toml` has exactly 7 `[[sections]]` entries with the documented ids). |
| 3 | A summary for a new/obscure tool reflects real fetched text, not fabrication | ✓ VERIFIED (mechanism only) — ⚠️ live behavior unverified | `techtrend/pipeline/grounding.py::fetch_grounding` returns `None` when both description and README are empty/unfetchable — caller (`run_enrichment`) then skips the LLM entirely and writes a `fetch_failed` tombstone (never calls `enrich_item`). `techtrend/pipeline/llm.py::enrich_item`'s system prompt instructs the model to use ONLY the provided `<repo_description>`/`<readme_excerpt>` text, and checks `stop_reason == "refusal"` before reading `parsed_output`, returning `None` on refusal (`tests/test_llm.py::test_refusal_returns_none` passes). No live model call was exercised in this environment (no `ANTHROPIC_API_KEY`) — see behavior_unverified_items. |
| 4 | Re-running on unchanged items never re-calls the LLM (cache hit); enrichment failure still displays ranked without a summary | ✓ VERIFIED | `_cache_hit()` checks `(entity_id, content_hash, status='complete')` before calling the LLM (`tests/test_enrich.py::test_cache_hit_skips_llm_call` passes); `normalize_for_hash` strips inline-style markdown badges + HTML comments + collapses whitespace before hashing (`tests/test_grounding.py` badge-stability tests pass). `query_ranked`'s `LEFT JOIN enrichments` (never `JOIN`) keeps every eligible row visible regardless of enrichment outcome; `table.html` renders "source unavailable" (fetch_failed) or "summary pending" (never enriched) — never a blank cell, never a dropped row (`tests/test_dashboard.py::test_unenriched_item_still_renders` passes). |

**Score:** 4/4 mechanism-level truths verified by code + passing unit tests. 1 item (SC3's real-model-output guarantee) is present-and-wired but not behaviorally exercised against live data in this environment — routed to human verification, consistent with the phase's own 02-05 deferred-UAT plan.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `techtrend/db/schema.sql` | `enrichments` table, 10 columns, `UNIQUE(entity_id, content_hash)` | ✓ VERIFIED | Confirmed present with exact column set, index `idx_enrichments_entity_computed` |
| `techtrend/config.py` | `Tunables` +4 fields, `SectionDef`, `Config.sections` | ✓ VERIFIED | All four fields present with decision-id comments; `SectionDef(id,label,description)` present |
| `config/tracked.toml` | 4 `[tunables]` entries + 7 `[[sections]]` | ✓ VERIFIED | `enrichment_cap=15`, `grounding_char_cap=2000`, `enrichment_model="claude-haiku-4-5"`, `confidence_flag_threshold="low"`; exactly 7 sections with documented ids |
| `techtrend/pipeline/llm.py` | Anthropic wrapper, `EnrichmentResult`, `enrich_item` | ✓ VERIFIED | Present, wired, `anthropic==0.122.0` pinned in `pyproject.toml`, importable in project `.venv` |
| `techtrend/pipeline/grounding.py` | `extract_intro`, `normalize_for_hash`, `fetch_grounding` | ✓ VERIFIED | All three present and tested |
| `techtrend/pipeline/enrich.py` | `select_candidates`, `run_enrichment`, cache/tombstone helpers | ✓ VERIFIED | Present, matches Wave 0 contract, per-candidate try/except isolation confirmed in source |
| `techtrend/enrich.py` | standalone `python -m techtrend.enrich` entry point | ✓ VERIFIED | Mirrors `score.py` shape; `record_stage` reused, not reimplemented |
| `techtrend/server/queries.py` | `query_ranked(section=)`, `query_section_counts` | ✓ VERIFIED | LEFT JOIN + bound `:section`; `query_section_counts` uses plain JOIN excluding null sections |
| `techtrend/server/app.py` | `section` query param threaded through | ✓ VERIFIED | `dashboard(section: str | None = None)` passes to both queries + template context |
| `techtrend/web/templates/partials/sidebar.html` | New left-nav sidebar | ✓ VERIFIED | All + 7 sections, live counts, htmx links carry both `sort`+`section` |
| `techtrend/web/templates/partials/table.html` | Summary cell + fallbacks + low-confidence flag | ✓ VERIFIED | No `|safe` used (grep confirms 0 occurrences); autoescape relied on |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `select_candidates` | `scores.eligible=1 AND score_version=CURRENT` | reused `query_ranked` WHERE clause | ✓ WIRED | Identical seam, confirmed by source comparison |
| `run_enrichment` | `pipeline/grounding.py::fetch_grounding` | `fetch_grounding_fn` seam | ✓ WIRED | None-return -> tombstone -> LLM never called |
| `run_enrichment` | `pipeline/llm.py::enrich_item` | `llm_call_fn` seam, only on cache miss | ✓ WIRED | `_cache_hit` gate precedes every call |
| `query_ranked` | `enrichments` table | `LEFT JOIN` on `MAX(computed_at)` | ✓ WIRED | Confirmed no data loss on unenriched rows |
| `app.py::dashboard()` | `sidebar.html`/`table.html` | `section`/`section_counts`/`sections` context keys | ✓ WIRED | All three keys present in template context |
| every htmx link (sidebar + table) | `/?sort=...&section=...` | both params on every link | ✓ WIRED | Confirmed via direct file read — all 6 links carry both params |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|---------------------|--------|
| `table.html` summary cell | `row['summary_line_1']`/`row['summary_line_2']`/`row['low_confidence']` | `query_ranked`'s `LEFT JOIN enrichments` (real SQL, no static fallback) | Yes — real DB query, no static/empty return | ✓ FLOWING |
| `sidebar.html` section counts | `section_counts` | `query_section_counts()` (real GROUP BY query, pinned to same eligible seam) | Yes | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full test suite (project `.venv`, run once) | `.venv/Scripts/python.exe -m pytest -q` | `135 passed` | ✓ PASS |
| Phase-relevant modules only | `pytest -q tests/test_enrich.py tests/test_llm.py tests/test_grounding.py tests/test_dashboard.py` | `33 passed` | ✓ PASS |
| Cap-boundary test exists but does not cover cap<=0 | `grep -n "cap=" tests/test_enrich.py` | only `cap=2`, `cap=15` (default) exercised — no negative/zero case | ⚠️ Confirms 02-REVIEW.md CR-01's stated test gap |
| `anthropic` importable in project venv | `.venv/Scripts/python.exe -c "import anthropic; print(anthropic.__version__)"` | not independently re-run (SUMMARY-claimed `0.122.0`, `pyproject.toml` pins the same) | ? SKIP — no live network/API needed to confirm the pin; pin verified by direct file read |
| `ANTHROPIC_API_KEY` literal isolation | `grep -rln "ANTHROPIC_API_KEY" techtrend/ \| grep -v "pipeline/llm.py"` | matches `pipeline/enrich.py` (a comment mentioning the var name, not a read) and a `.pyc` cache file | ℹ️ INFO — the actual secret READ (`os.environ.get`) is confirmed confined to `pipeline/llm.py` only (`grep -n "os.environ" techtrend/` shows only `paths.py`, `collectors/http.py` (GITHUB_TOKEN), `pipeline/llm.py` (ANTHROPIC_API_KEY)); the isolation *guarantee* holds, the plan's literal-string grep is stricter than the guarantee it tests |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| DATA-04 | 02-01, 02-04 | Enrichments cached by entity + content hash | ✓ SATISFIED | `enrichments` table + `_cache_hit()`; `test_cache_hit_skips_llm_call` passes |
| ENR-01 | 02-04 | Only ranking-threshold survivors sent to LLM | ✓ SATISFIED | `select_candidates` gates on `eligible=1`; `test_gate_reads_eligible_seam` passes |
| ENR-02 | 02-01, 02-04 | Hard per-run cap, independent of threshold | ✓ SATISFIED (see CR-01 caveat above) | `LIMIT :enrichment_cap` on candidate SET; `test_cap_limits_candidate_set` passes |
| ENR-03 | 02-02 | Two-line "what/why" summary | ✓ SATISFIED | `EnrichmentResult.summary_line_1/2`; test passes |
| ENR-04 | 02-02 | Exactly one of seven sections | ✓ SATISFIED | `build_section_result_model` enum-enforced; test passes |
| ENR-05 | 02-03, 02-04 | Grounded on fetched text, never parametric knowledge | ✓ SATISFIED (mechanism); live behavior deferred | `fetch_grounding` None-on-empty; prompt instructs grounding-only; refusal->None |
| ENR-06 | 02-04, 02-05 | Enrichment failure never loses ranked data | ✓ SATISFIED | LEFT JOIN + honest fallbacks; `test_unenriched_item_still_renders`, `test_per_candidate_failure_does_not_abort_run` pass |
| DASH-02 | 02-05 | Browse/filter dashboard by section | ✓ SATISFIED | Sidebar + bound `:section` filter; `test_section_filter` passes |

No orphaned requirements — REQUIREMENTS.md's Phase 2 mapping (DATA-04, ENR-01..06, DASH-02) exactly matches the union of `requirements:` fields declared across the five 02-*-PLAN.md files.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `techtrend/config.py` | 55 | `enrichment_cap: int = 15` has no positive-value constraint (02-REVIEW.md CR-01, unresolved) | 🛑→⚠️ WARNING (not blocking under shipped config) | SQLite treats a negative `LIMIT` as unbounded; a bad `config/tracked.toml` edit would silently defeat SC1's "hard cap" guarantee. Current shipped value (15) is safe. See human_verification item above. |
| `techtrend/pipeline/grounding.py` | 38 | Badge-strip regex only covers inline-style `![alt](url)`, not reference-style `![alt][ref]` + `[ref]: url` (02-REVIEW.md WR-02) | ⚠️ WARNING | For repos using reference-style shields.io badges, a CI status flip can defeat the cache and re-trigger the LLM — a narrower version of the same SC4 guarantee this normalization exists to provide. Not tested for this style. |
| `techtrend/pipeline/llm.py` | 144-149 | Untrusted README text interpolated into the prompt with no delimiter-collision escaping (02-REVIEW.md WR-03) | ⚠️ WARNING | Instruction-only defense against prompt injection; a README containing literal `</repo_description>` text is passed through unescaped. Bounded impact (section/confidence are enum-constrained). |
| `techtrend/pipeline/grounding.py` | 51 | `normalize_for_hash(description, readme_intro)` coalesces `description` with `or ''` but not `readme_intro` (02-REVIEW.md WR-04) | ℹ️ INFO | Not exploitable at any current call site (verified `fetch_grounding` never returns `readme_intro=None`) |
| `techtrend/server/queries.py` | 76-80, 143-147 | `MAX(computed_at)` correlated-subquery "current row" join has no deterministic tie-break unlike `select_candidates`'s `entities.id ASC` (02-REVIEW.md WR-05) | ℹ️ INFO | Requires two enrichments rows for the same entity within the same 1-second `computed_at` resolution — an edge case, not exercised by any test |
| `techtrend/config.py` | 64 | `confidence_flag_threshold: str` (no `Literal` enum) can silently disable the low-confidence flag on a typo (02-REVIEW.md WR-01) | ℹ️ INFO | Same class of issue as CR-01 but lower severity/blast-radius (UI cosmetic, not cost) |

All items above are carried forward unresolved from `02-REVIEW.md` (dated 2026-08-15T02:21:47Z) — no fix commits exist after the review commit (`825aa61`, the last commit in `git log`). No `TBD`/`FIXME`/`XXX` debt markers found in any phase-modified file.

### Human Verification Required

### 1. Decide disposition of CR-01 (unresolved Critical review finding)

**Test:** Review `02-REVIEW.md` CR-01 — `Tunables.enrichment_cap` has no `Field(gt=0)` constraint; SQLite's `LIMIT` treats negative values as unbounded.
**Expected:** Either schedule the one-line fix (`Field(default=15, gt=0)` + a defensive raise in `select_candidates`), or explicitly accept the risk given the shipped config value is positive and this is a hand-edited, single-user, non-adversarial config file.
**Why human:** This is a judgment call about risk tolerance for a personal single-user tool vs. leaving an unresolved Critical finding against the phase's own stated cost-bounding guarantee. The mechanism is correct for every value currently in the repo; the gap is purely in input validation.

### 2. Live section browsing + anti-fabrication summary spot-check (already tracked, STATE.md Deferred Items, 02-05 Task 3)

**Test:** With `ANTHROPIC_API_KEY` configured and a real `collect`/`score`/`enrich` run completed, open the dashboard, click through sections, sort while filtered, find a zero-count section, and compare 2-3 real summaries against their repos' actual README intros.
**Expected:** Sidebar counts match rendered rows; sort+section never reset each other; summaries are traceable to real fetched text; a low-confidence flag is visually spottable; unenriched rows show honest fallbacks and are never dropped.
**Why human:** No `ANTHROPIC_API_KEY` and no enriched rows exist in this environment — this is inherently a live-data, visual, and LLM-output-quality judgment that cannot be programmatically verified. The mechanism producing this behavior (grounding, prompt, refusal handling, LEFT JOIN, fallback rendering) is verified in code and by unit test above.

### Gaps Summary

No must-have truth FAILED. All five plans' declared truths are backed by passing unit tests and direct source inspection; the cost-gate, grounding/anti-fabrication mechanism, cache-hit skip, and dashboard LEFT-JOIN/fallback/section-filter wiring are all present and correctly wired. The phase goal's mechanisms are real, not stubs.

Two categories of open item prevent a clean `passed`:

1. **One unresolved Critical code-review finding (CR-01)** that touches the exact guarantee SC1 states ("hard per-run cap... even on an unusually busy day") — currently non-violating under the shipped config, but left unaddressed after being flagged, and worth an explicit accept/fix decision rather than silent carry-forward.
2. **SC3's live-data guarantee** (grounded, non-fabricated summaries) has a fully-implemented and unit-tested *mechanism*, but the actual quality of real Haiku 4.5 output against real README text has never been observed in this environment — this was already correctly identified and deferred by the 02-05 plan itself (STATE.md Deferred Items), not a new gap introduced by this verification.

Four secondary WARNING/INFO-level findings (WR-01 through WR-05, IN-01, IN-02 in `02-REVIEW.md`) remain open but are edge-case robustness gaps, not goal-blocking — they are listed in Anti-Patterns Found for visibility and should be triaged (fixed or explicitly backlogged) before the next phase touches these files.

---

_Verified: 2026-08-15_
_Verifier: Claude (gsd-verifier)_
