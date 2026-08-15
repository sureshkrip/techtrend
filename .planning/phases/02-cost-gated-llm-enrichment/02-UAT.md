---
status: testing
phase: 02-cost-gated-llm-enrichment
source: [02-VERIFICATION.md]
started: 2026-08-15T00:00:00Z
updated: 2026-08-15T00:00:00Z
---

## Current Test

number: 1
name: Live section browsing + anti-fabrication summary spot-check
expected: |
  With ANTHROPIC_API_KEY configured and a fresh collect/score/enrich run completed:
  sidebar counts match table rows per section; sort and section filters persist
  together across htmx links; a low-confidence flag is spottable at a glance;
  2-3 real summaries are each traceable to their repo's actual README intro (no
  fabrication); unenriched/failed rows show honest fallbacks ("summary pending" /
  "source unavailable") and are never dropped from the "All" view.
awaiting: user response

## Tests

### 1. Live section browsing + anti-fabrication summary spot-check
expected: |
  Requires ANTHROPIC_API_KEY plus a fresh `collect` → `score` → `python -m techtrend.enrich`
  run against real data. Then, in the dashboard:
  - Sidebar lists "All" + the seven sections, each with a count; "All" is active by default
    and shows the full ranked list including unenriched rows.
  - Clicking a section narrows the table to that section's enriched rows only.
  - Sorting a column while a section is active, then switching sections, preserves BOTH
    sort and section (URL + rendered table).
  - A zero-count section shows an honest empty state, not an error.
  - 2-3 enriched summaries are each supported by the repo's actual README intro
    (SC3 anti-fabrication); flag anything unsupported.
  - At least one low-confidence filing carries a visually spottable flag.
  - Unenriched/failed rows render "summary pending" / "source unavailable" and still appear.
result: [pending]

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps
