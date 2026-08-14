---
status: complete
phase: 01-foundation-first-signal-github-scored-and-visible
source:
  - 01-01-SUMMARY.md
  - 01-02-SUMMARY.md
  - 01-03-SUMMARY.md
  - 01-04-SUMMARY.md
  - 01-05-SUMMARY.md
  - 01-06-SUMMARY.md
started: 2026-08-13
updated: 2026-08-13
---

## Current Test

[testing complete]

## Tests

<!-- Auto-covered by passing tests (source: automated) — not presented -->
### A. 01-01 D1–D6 — DB schema, WAL, migrations, entity resolution, snapshot upserts, idempotency
expected: covered by passing tests
result: pass
source: automated

### B. 01-02 D1–D6 — FastAPI app, Jinja/htmx render, ranked-query wiring, empty-state, links, config load
expected: covered by passing tests
result: pass
source: automated

### C. 01-03 D1–D8 — GitHub collector, search/discovery, ETag caching, run_manifest, degradation-path
expected: covered by passing tests
result: pass
source: automated

### D. 01-04 D1–D8 — Scoring (floor-before-Wilson, window-gain last-minus-first, stability metric, tie-break)
expected: covered by passing tests
result: pass
source: automated

### E. 01-05 D1–D6, D8 — Backfill sampled stargazer pagination, blocked/failed classification, D-08a honest degradation
expected: covered by passing tests
result: pass
source: automated

### F. 01-06 D1–D7 — Health strip 4-tier escalation, sort partials, empty-state honesty, docs-link fallback, CR-03 try/except
expected: covered by passing tests
result: pass
source: automated

<!-- Human-judgment checkpoints (present[]) -->
### 1. UI-SPEC visual token compliance  (01-02 D7)
expected: In a browser, spacing/color/typography render faithfully to the UI-SPEC. Tokens are grep-confirmed present; only the rendered visual fidelity needs a human glance.
result: skipped
reason: "Deferred follow-up: browser-visual judgment; tokens grep-confirmed present. User chose to close Phase 1 and verify visually later."

### 2. Live GitHub ingest happy-path  (01-03 D9)
expected: With a real GITHUB_TOKEN set, `python -m techtrend.ingest` (no flags) populates real entities/snapshots; a second run shows 304s in the log. (Token-absent degradation — run_manifest 'failed' row + descriptive error_detail — is already verified.)
result: skipped
reason: "Deferred follow-up: happy-path needs the user's own GITHUB_TOKEN (not available to the executor). Degradation path already verified."

### 3. Backfill failure never blocks live collection  (01-05 D7)
expected: With a real GITHUB_TOKEN, backfill of an owned repo returns real stargazer history, and a non-owned repo's live 403 degrades without blocking collection — ingest exit code stays 0. (Token-absent degradation already verified: blocked=106, failed=0, status=success.)
result: skipped
reason: "Deferred follow-up: happy-path needs the user's own GITHUB_TOKEN. Token-absent degradation already verified live (blocked=106, failed=0)."

### 4. Sort-header error surfacing (E3)  (01-06 D8)
expected: In a real browser, force a failed sort GET (DevTools > Network > Offline/throttle to 5xx), then click a sortable column header. A visible error indicator appears; rows are NOT left stale under a moved sort glyph. (Client-side htmx listener — not exercisable from testclient.)
result: skipped
reason: "Deferred follow-up: client-side htmx behavior, real-browser-only; not exercisable from testclient. Listener wired in dashboard.html."

### 5. Visual density/legibility at real row counts  (01-06 D9)
expected: Once tracked repos accrue several days of real star-gain data and clear the window_gain_floor, the populated table reads legibly at 5–50 rows (column widths, ellipsis, rank-vs-scan). By D-08a's design no such populated state exists on day one — reserved for personal verification.
result: skipped
reason: "Deferred follow-up: by D-08a design no populated table exists on day one; reserved for personal verification once real star-gain data accrues."

### 6. DB-unreadable graceful degradation copy  (01-06 D10)
expected: Rename/corrupt the real techtrend.db and load the dashboard — the Copywriting Contract's "couldn't read the database" copy renders instead of a raw traceback. (Smoke-tested this build against an uninitialized DB; user asked to repeat against a renamed real DB.)
result: skipped
reason: "Deferred follow-up: smoke-tested against an uninitialized DB this build (correct copy, no traceback); user to repeat against a renamed real techtrend.db."

## Summary

total: 6
passed: 0
issues: 0
pending: 0
skipped: 6

## Gaps

[none yet]

## Deferred Follow-Ups

- test: 1
  idea: "UI-SPEC visual token compliance — verify rendered spacing/color/typography in a browser."
  deferred_at: 2026-08-13
- test: 2
  idea: "Live GitHub ingest happy-path (real entities/snapshots + 304 reruns) with the user's own GITHUB_TOKEN."
  deferred_at: 2026-08-13
- test: 3
  idea: "Backfill happy-path with a real GITHUB_TOKEN (owned-repo history + non-owned live 403 degradation, exit 0)."
  deferred_at: 2026-08-13
- test: 4
  idea: "E3 sort-header error surfacing in a real browser (DevTools offline/throttle)."
  deferred_at: 2026-08-13
- test: 5
  idea: "Visual density/legibility at real populated row counts once star-gain data accrues (D-08a)."
  deferred_at: 2026-08-13
- test: 6
  idea: "DB-unreadable graceful-degradation copy against a renamed real techtrend.db."
  deferred_at: 2026-08-13
