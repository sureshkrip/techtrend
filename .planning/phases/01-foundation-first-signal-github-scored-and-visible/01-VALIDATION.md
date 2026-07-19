---
phase: 1
slug: foundation-first-signal-github-scored-and-visible
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-19
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | none — Wave 0 installs (`pyproject.toml` [tool.pytest.ini_options]) |
| **Quick run command** | `uv run pytest -q -x` |
| **Full suite command** | `uv run pytest -q` |
| **Estimated runtime** | ~15 seconds (no live network calls — fixtures only) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -q -x`
- **After every plan wave:** Run `uv run pytest -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

*To be filled by the planner — one row per task in each PLAN.md.*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `pyproject.toml` — project scaffold with pytest + ruff dev dependencies
- [ ] `tests/conftest.py` — shared fixtures (in-memory SQLite, frozen clock, recorded GitHub API fixtures)
- [ ] `tests/fixtures/github/` — captured GitHub search + repo JSON responses (no live network in tests)
- [ ] `tests/test_scoring.py` — stubs for SCORE-01..SCORE-05, including the literal pitfall assertion (2→10 stars must NOT outrank 4000→4300 stars)
- [ ] `tests/test_storage.py` — stubs for DATA-01..DATA-05, including re-run idempotency (no duplicate entities, no duplicate same-day snapshots)
- [ ] `tests/test_collect_github.py` — stubs for COLL-01/02/06..09
- [ ] `tests/test_health.py` — stubs for HEALTH-01/HEALTH-02 (run outcome recording, staleness flagging)
- [ ] `tests/test_dashboard.py` — stubs for DASH-01/03..06 (FastAPI TestClient route + rendered-content assertions)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Windows Task Scheduler fires the daily ingest unattended | COLL-01 | Requires OS-level scheduler registration and a real wall-clock trigger; cannot be asserted in-process | Register the task, set trigger to +2 min, confirm the log file gains a new run entry and the DB gains a new snapshot row |
| Live GitHub API call succeeds against real credentials and respects rate limits | COLL-06, COLL-07 | Tests use recorded fixtures by design; real-credential behavior is environment-specific | Run the ingest once manually with a real `GITHUB_TOKEN`; confirm the log shows a 200 and a non-zero item count, and a second immediate run shows 304s |
| Dashboard renders legibly in a browser (layout, sort/filter interaction) | DASH-01, DASH-03 | Visual/interaction quality is not assertable from HTML content alone | Open the dashboard, sort and filter the table, confirm rank order changes correctly and no full-page reload occurs |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
