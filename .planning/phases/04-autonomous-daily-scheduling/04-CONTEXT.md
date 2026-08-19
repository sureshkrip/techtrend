# Phase 4: Autonomous Daily Scheduling — Context

**Gathered:** 2026-08-19
**Status:** Ready for planning
**Note:** Executing Phase 4 ahead of Phase 3 at the owner's explicit request — nothing ranks until the daily run works, so scheduling is the current pain point.

<domain>
## Task Boundary

Make the full `collect → score → enrich` pipeline run automatically once per day on the **hosted Coolify deployment**, so the dashboard is current without manual triggering. This phase **rescopes** the original Phase 4 (which assumed Windows Task Scheduler + wake-from-sleep) to the hosted model that is now in use (Coolify, server-side PostgreSQL) — consistent with the deployment reversal already recorded in CLAUDE.md and PROJECT.md.
</domain>

<decisions>
## Implementation Decisions (LOCKED — do not revisit)

### Scheduling mechanism
- **Coolify Scheduled Task (cron)** fires `python -m techtrend.daily` inside the app container on a daily cron (default `0 6 * * *` — 06:00 UTC; owner may adjust).
- Serving and scheduling stay **independent**: the uvicorn dashboard process is separate from the scheduled task. Serving never triggers a pipeline run (D-17), and a scheduled run never depends on the dashboard being open. This matches the project's own "Stack Patterns by Variant" (Task Scheduler / cron fires a standalone script; dashboard is a separate read-only process) and the existing `Dockerfile` comment which already anticipates a "Coolify Scheduled Task."
- **Not** APScheduler-in-process; **not** external/GitHub-Actions cron. (Both considered and rejected in discussion.)

### Missed-run handling
- **Cron only — NO new catch-up/backfill code.** If the container is down at fire time, that day is simply skipped.
- A skipped/stale day is surfaced by the **existing** dashboard staleness machinery built in Phase 1 (`techtrend/server/health.py`: the `staleness_hours` escalation and the `"Last successful run: …"` / `"Data may be out of date…"` banner). No changes to health.py are required or wanted.

### SCHED-02 rescope
- The original SCHED-02 ("survive sleep/missed-window on Windows" — wake timers, wake-to-run, run-if-missed) is **N/A on an always-on hosted server** and must be **documented as superseded**, not implemented. The hosted equivalent of "don't silently skip a day" is the staleness banner (SCHED-02 → satisfied by existing HEALTH-02 behavior on the hosted model).

### Claude's Discretion
- Exact cron time/expression wording in docs (06:00 UTC is a sensible default).
- Whether to record the rescope as an amended requirement vs. a new hosted requirement id — planner's call, but keep REQUIREMENTS.md and ROADMAP.md internally consistent and honest about the supersession (mirror how the SQLite→Postgres reversal was recorded, not silently edited away).
</decisions>

<specifics>
## Specific Ideas / Expected Deliverables

Primarily **rescope + documentation + verification**, with minimal-to-no production code:

1. **Rescope ROADMAP.md Phase 4** — replace "Windows Task Scheduler wired with wake/missed-run settings" framing with the Coolify Scheduled Task model; keep the decision-history honest (note the supersession rather than silently rewriting), consistent with the CLAUDE.md Coolify reversal.
2. **Rescope REQUIREMENTS.md SCHED-01/SCHED-02** — SCHED-01 stays (runs daily, automatically); SCHED-02 is re-expressed for the hosted model (missed-run visibility via the staleness banner) and its Windows wake-timer wording marked superseded.
3. **Deployment docs (README.md `## Deploy` / scheduling section)** — precise Coolify Scheduled Task setup: the command (`python -m techtrend.daily`), the cron schedule, the required environment (PG* connection vars, `OPENAI_API_KEY` for the GLM enrichment provider, `GITHUB_TOKEN`; note `TECHTREND_DISABLE_LLM` as the opt-out), and that the scheduled task is independent of serving. Fold in the earlier-flagged doc-staleness (`ANTHROPIC_API_KEY` → the app now uses `OPENAI_API_KEY`/GLM) where it touches scheduling env.
4. **Verification (no live wait)** — show that Success Criteria 1 & 3 are already satisfied by existing code + the Coolify config: `python -m techtrend.daily` is the single chained entrypoint (already built, quick task 260816-lkt), and `health.py`'s staleness banner already renders "last successful run" / stale-data messaging. SC2 (wake-from-sleep) is documented as N/A on hosted.
</specifics>

<canonical_refs>
## Canonical References

- `.claude/CLAUDE.md` — Constraints + "Stack Patterns by Variant" (Coolify hosted deployment; standalone scheduled script vs. read-only dashboard) and the SQLite→Postgres/Coolify reversal precedent for how to record a superseded decision honestly.
- `techtrend/daily.py` — the `python -m techtrend.daily` chained entrypoint the scheduled task runs (collect→score→enrich, fail-fast).
- `techtrend/server/health.py` — existing staleness banner (`staleness_hours`, "Last successful run: …") that satisfies the hosted SCHED-02 / missed-run-visibility criterion.
- `Dockerfile` — already references a Coolify Scheduled Task + `/data` volume; the image serves the dashboard, the scheduled task runs the pipeline in the same image.
- Memory: `phase-4-coolify-deployment` — records that Phase 4 was rescoped off Windows Task Scheduler when deployment moved to hosted Coolify.
</canonical_refs>
