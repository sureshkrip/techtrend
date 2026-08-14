---
phase: 2
slug: cost-gated-llm-enrichment
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-14
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Seeded by plan-phase from 02-RESEARCH.md §Validation Architecture. Task-ID rows are filled once PLAN.md waves exist (validate-phase §6).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest ≥8 (already configured) |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`: `testpaths = ["tests"]`, `addopts = "-q"`) |
| **Quick run command** | `pytest -q tests/test_enrich.py tests/test_grounding.py tests/test_llm.py` |
| **Full suite command** | `pytest -q` |
| **Estimated runtime** | ~10–20 seconds (no live API calls — Anthropic client is stubbed) |

---

## Sampling Rate

- **After every task commit:** Run `pytest -q tests/test_enrich.py tests/test_grounding.py tests/test_llm.py tests/test_dashboard.py`
- **After every plan wave:** Run `pytest -q` (full suite)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~20 seconds

---

## Per-Requirement Verification Map

*Task IDs are assigned when PLAN.md waves are created; validate-phase §6 rewrites this into the per-task grid. Rows below map each phase requirement to its automated proof.*

| Requirement | Behavior | Test Type | Automated Command | File Exists |
|-------------|----------|-----------|-------------------|-------------|
| DATA-04 | Unchanged content hash → LLM never re-called (cache hit skips the call) | unit | `pytest tests/test_enrich.py::test_cache_hit_skips_llm_call -x` | ❌ W0 |
| ENR-01 | Only `scores.eligible=1` items at `CURRENT_SCORE_VERSION` are candidates | unit | `pytest tests/test_enrich.py::test_gate_reads_eligible_seam -x` | ❌ W0 |
| ENR-02 | Hard per-run cap enforced independent of threshold; overflow untouched this run | unit | `pytest tests/test_enrich.py::test_cap_limits_candidate_set -x` | ❌ W0 |
| ENR-03 | Two-line summary present in a successful enrichment | unit | `pytest tests/test_llm.py::test_enrich_item_returns_two_line_summary -x` | ❌ W0 |
| ENR-04 | Exactly one of the seven section ids returned; schema enum enforcement | unit | `pytest tests/test_llm.py::test_section_constrained_to_enum -x` | ❌ W0 |
| ENR-05 | Grounding fetch failure → LLM never called, no fabrication | unit | `pytest tests/test_enrich.py::test_fetch_failure_skips_llm -x` | ❌ W0 |
| ENR-06 | LLM error / cap overflow never removes an already-ranked item from `query_ranked` output | integration | `pytest tests/test_dashboard.py::test_unenriched_item_still_renders -x` | ❌ W0 |
| DASH-02 | `?section=X` filters the ranked table; unenriched items only under "All" (D-13) | integration | `pytest tests/test_dashboard.py::test_section_filter -x` | ❌ W0 |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_grounding.py` — `extract_intro`, `normalize_for_hash`, badge-stripping (grounding pitfall #1)
- [ ] `tests/test_llm.py` — `EnrichmentResult` schema validation, refusal handling, prompt construction with a **fake Anthropic client** (no live API call — inject a stub `client` via the same optional-parameter pattern `GitHubCollector.__init__(config=None, client=None)` establishes)
- [ ] `tests/test_enrich.py` — gate/cap/cache-hit/fetch-failure orchestration logic in `pipeline/enrich.py`
- [ ] `tests/fixtures/anthropic/` — recorded structured-output-shaped response fixtures (`enrichment_success.json`, `enrichment_refusal.json`) for the fake client to replay
- [ ] `tests/fixtures/github/readme_with_badges.md` — README fixture with badge markup + a deep heading, for `extract_intro`/`normalize_for_hash` tests
- [ ] Extend `tests/test_dashboard.py` — `section` query param, sidebar counts, unenriched-item-under-"All"-only behavior (D-13)
- [ ] Framework install: **none** — pytest already configured; no new test dependency needed

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Summary text genuinely reflects fetched README/description (SC3 anti-fabrication, qualitative) | ENR-05 | Grounding faithfulness is a semantic judgment a unit test can only approximate | After a real run, open the dashboard, pick 2–3 enriched rows, compare each summary against the repo's actual README intro — flag any claim not supported by the fetched text |
| Low-confidence visual flag is spottable at a glance (D-02) | ENR-04 | Visual salience is a perceptual judgment | Load a view containing at least one `confidence=low` filing; confirm the flag is visible without hunting |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 20s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
