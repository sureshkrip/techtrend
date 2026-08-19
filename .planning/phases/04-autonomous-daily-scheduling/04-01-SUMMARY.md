---
phase: 04-autonomous-daily-scheduling
plan: 01
subsystem: infra
tags: [coolify, cron, scheduling, docs, deploy, postgresql, glm, openai-compatible]

# Dependency graph
requires:
  - phase: 02-cost-gated-llm-enrichment
    provides: "python -m techtrend.enrich stage, enrichment_provider config tunable"
  - phase: quick-260816-lkt
    provides: "python -m techtrend.daily chained collect->score->enrich entrypoint"
  - phase: quick-260817-0qt
    provides: "PostgreSQL storage backend + Coolify hosted deployment model"
provides:
  - "ROADMAP.md Phase 4 rescoped from Windows Task Scheduler to Coolify Scheduled Task (cron), with honest supersession note"
  - "REQUIREMENTS.md SCHED-01 generalized off Windows; SCHED-02 re-expressed for hosted missed-run visibility, Windows wording marked superseded"
  - "README.md Deploy section documents the exact Coolify Scheduled Task (command, cron schedule, required env, D-17 independence, cron-only missed-run visibility)"
  - "README.md Configure section corrected: OPENAI_API_KEY (GLM/Z.ai) is the required enrichment secret, not ANTHROPIC_API_KEY"
  - "Verified (network-free) that SC1 (daily automatic run mechanism) and SC3 (staleness banner) are already satisfied by existing code"
affects: [phase-5-and-beyond, deploy-runbook, uat-backlog]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Supersession-note pattern for rescoped planning artifacts: strike through the superseded wording, add an explicit '(superseded YYYY-MM-DD — see Phase N rescope)' note, and record why — never silently delete decision history. Mirrors the CLAUDE.md SQLite->Postgres/Coolify reversal precedent."

key-files:
  created:
    - .planning/phases/04-autonomous-daily-scheduling/04-01-SUMMARY.md
  modified:
    - .planning/ROADMAP.md
    - .planning/REQUIREMENTS.md
    - README.md

key-decisions:
  - "Phase 4 rescoped in-place (ROADMAP + REQUIREMENTS) rather than superseded with a new requirement ID -- SCHED-01/SCHED-02 keep their IDs and Phase 4 mapping, with the Windows-specific wording struck through and an explicit superseded note added, per 04-CONTEXT.md's 'Claude's Discretion' guidance."
  - "README's stale 'Alternative LLM provider (Kimi/Moonshot)' bullet (which claimed the enrichment stage 'defaults to Anthropic Haiku 4.5') was also corrected, beyond the plan's literal Deploy-section scope, because it directly touches the same enrichment-secret area Task 2 was fixing and left the file internally inconsistent otherwise (Rule 1 -- bug: stale claim contradicted the immediately-preceding corrected bullet and the actual config/tracked.toml default of openai/glm-4.7-flash)."

patterns-established: []

requirements-completed: [SCHED-01, SCHED-02]

coverage:
  - id: D1
    description: "ROADMAP.md Phase 4 (bullet, Goal, Success Criteria) rescoped to the Coolify Scheduled Task (cron) model with an honest supersession note; REQUIREMENTS.md SCHED-01 generalized and SCHED-02 re-expressed for hosted missed-run visibility with Windows wording marked superseded; both files remain internally consistent and both requirements stay mapped to Phase 4."
    requirement: "SCHED-01"
    verification:
      - kind: other
        ref: "python -c assertion: 'Coolify' in ROADMAP.md, 'supersed' regex in both ROADMAP.md and REQUIREMENTS.md, SCHED-01/SCHED-02 both present in REQUIREMENTS.md"
        status: pass
    human_judgment: false
  - id: D2
    description: "README Deploy section documents the exact Coolify Scheduled Task (command python -m techtrend.daily, daily cron default 0 6 * * *, required env PG*/GITHUB_TOKEN/OPENAI_API_KEY, TECHTREND_DISABLE_LLM opt-out, D-17 serving/scheduling independence, cron-only missed-run visibility via the staleness banner); Configure section's required-secret and alternative-provider bullets corrected to OPENAI_API_KEY (GLM/Z.ai) as the deployed default, Anthropic/Kimi as documented alternatives; no Windows Task Scheduler / schtasks wording remains."
    requirement: "SCHED-01"
    verification:
      - kind: other
        ref: "python -c assertion: README Deploy section contains 'python -m techtrend.daily', a cron/'0 6 * * *' pattern, OPENAI_API_KEY + GITHUB_TOKEN, TECHTREND_DISABLE_LLM anywhere in file, a stale/out-of-date/last-successful-run phrase in Deploy, and no 'schtasks'/'Task Scheduler' anywhere in file"
        status: pass
    human_judgment: false
  - id: D3
    description: "Network-free verification that techtrend.daily.STAGES chains collect->score->enrich in order with a runnable __main__ block (SC1 mechanism, proven by existing code, not reimplemented), and that techtrend/server/health.py's 'Last successful run' / 'Data may be out of date' staleness-banner strings and staleness_hours threshold are present and unmodified (SC3, unchanged). SC2 (original Windows wake/sleep) is documented superseded/N/A via the Task 1 and Task 2 supersession notes, not implemented."
    requirement: "SCHED-02"
    verification:
      - kind: other
        ref: "python -c (via project .venv, anthropic dependency present) assertion: techtrend.daily.STAGES == [('collect',...),('score',...),('enrich',...)] in order, '__main__' present in techtrend/daily.py source, and 'Last successful run'/'Data may be out of date'/'staleness_hours' all present in techtrend/server/health.py"
        status: pass
    human_judgment: false
  - id: D4
    description: "Live end-to-end confirmation of an actual scheduled 24h Coolify run (the real cron firing python -m techtrend.daily unattended against the hosted deployment) -- deferred by design, needs the live Coolify environment, a real OPENAI_API_KEY/GITHUB_TOKEN, and 24h+ of wall-clock time to observe."
    verification: []
    human_judgment: true
    rationale: "Cannot be verified in an automated, network-free, single-session executor run -- requires the actual hosted Coolify deployment, live secrets, and waiting for a real cron fire to confirm the mechanism works end-to-end in production, not just that the mechanism (entrypoint + docs) exists correctly."

# Metrics
duration: 5min
completed: 2026-08-19
status: complete
---

# Phase 4 Plan 1: Rescope Autonomous Daily Scheduling to Hosted Coolify Summary

**Rescoped Phase 4/SCHED-01/SCHED-02 off Windows Task Scheduler onto a Coolify Scheduled Task (`python -m techtrend.daily`, cron `0 6 * * *`), documented the exact deploy setup in README, corrected stale `ANTHROPIC_API_KEY` enrichment-secret references to the actual deployed `OPENAI_API_KEY`/GLM provider, and verified (network-free) that SC1's entrypoint mechanism and SC3's staleness banner are already satisfied by existing, unmodified code.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-08-19T13:05:20Z
- **Completed:** 2026-08-19T13:07:49Z
- **Tasks:** 3/3 completed
- **Files modified:** 3 (`.planning/ROADMAP.md`, `.planning/REQUIREMENTS.md`, `README.md`)

## Accomplishments
- ROADMAP.md Phase 4 (bullet line, Goal, Success Criteria 2, and a new supersession note) rescoped from "Windows Task Scheduler wired with wake/missed-run settings" to "Coolify Scheduled Task (cron) fires `python -m techtrend.daily`" — with the original Windows-era criterion 2 struck through, not deleted, per the CLAUDE.md SQLite→Postgres reversal precedent.
- REQUIREMENTS.md SCHED-01 generalized to "on the deployed environment"; SCHED-02's Windows wake-timer wording struck through and marked "(superseded 2026-08-19 — see Phase 4 rescope)", re-expressed as hosted missed-run visibility via the existing HEALTH-02 staleness banner. Both requirements remain mapped to Phase 4 in the Traceability table (unchanged).
- README `## Deploy (Docker / Coolify)` section now documents the Coolify Scheduled Task precisely: exact command, default daily cron (`0 6 * * *`, adjustable), full required env (PG* + `GITHUB_TOKEN` + `OPENAI_API_KEY`, `TECHTREND_DISABLE_LLM` opt-out), D-17 serving/scheduling independence, and an explicit "cron-only, no catch-up code" missed-run note pointing at the staleness banner.
- README `## Configure` section corrected: the required enrichment secret is now presented as `OPENAI_API_KEY` (the deployed GLM/Z.ai provider), with Anthropic and Kimi/Moonshot documented as alternative OpenAI-compatible providers — replacing the stale claim that the stage "defaults to Anthropic Haiku 4.5."
- Verified without any network call, using the project's `.venv` Python: `techtrend.daily.STAGES` resolves in order to `collect`, `score`, `enrich` with a runnable `__main__` block; `techtrend/server/health.py`'s "Last successful run" / "Data may be out of date" staleness strings and `staleness_hours` threshold are present, confirming both SC1's mechanism and SC3 are already satisfied by existing code — no changes made to either file.

## Task Commits

Each task was committed atomically:

1. **Task 1: Rescope ROADMAP.md and REQUIREMENTS.md off Windows Task Scheduler onto the hosted Coolify model** - `6bcab88` (docs)
2. **Task 2: Document the exact Coolify Scheduled Task setup in README and correct the stale enrichment-secret references** - `ea64584` (docs)
3. **Task 3: Network-free verification that SC1 & SC3 are already met by existing code + config, and SC2 is documented N/A** - this SUMMARY.md (no code changes; verification-only task)

**Plan metadata:** committed separately after this SUMMARY (`docs({phase}-{plan}): complete ...`)

_Note: this is a docs/rescope/verification plan — no `feat`/`test`/`refactor` commits, per the plan's explicit "no production code changes" constraint._

## Files Created/Modified
- `.planning/ROADMAP.md` - Phase 4 bullet, Goal, Success Criteria 2/3, and supersession note rescoped to the Coolify Scheduled Task model
- `.planning/REQUIREMENTS.md` - SCHED-01 generalized off Windows; SCHED-02 re-expressed for hosted missed-run visibility with Windows wording marked superseded
- `README.md` - Deploy section documents the exact Coolify Scheduled Task setup; Configure section's required-secret and alternative-provider bullets corrected to `OPENAI_API_KEY`/GLM
- `.planning/phases/04-autonomous-daily-scheduling/04-01-SUMMARY.md` - this file

## Decisions Made
- Rescoped SCHED-01/SCHED-02 in place (same requirement IDs, same Phase 4 mapping) rather than retiring them and introducing new hosted-specific IDs — 04-CONTEXT.md left this to planner's discretion, and keeping the IDs stable avoids churn in the Traceability table while the strikethrough + supersession note preserves the decision history honestly.
- Corrected the README's "Alternative LLM provider (Kimi/Moonshot)" bullet beyond the plan's literal Deploy-section instructions, because it directly claimed a stale default ("defaults to Anthropic Haiku 4.5") in the same Configure-section enrichment area Task 2 was fixing — leaving it as-is would have produced an internally-contradictory README (Rule 1: bug fix, directly in scope of the task's own file).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected the README "Alternative LLM provider (Kimi/Moonshot)" bullet's stale default-provider claim**
- **Found during:** Task 2 (README enrichment-secret corrections)
- **Issue:** The bullet stated "the enrichment stage defaults to Anthropic Haiku 4.5," which is false — `config/tracked.toml`'s shipped default is `enrichment_provider = "openai"` / `enrichment_model = "glm-4.7-flash"` / `enrichment_base_url = "https://api.z.ai/api/paas/v4/"` (GLM via Z.ai, per quick task 260817-jii). Leaving it unchanged would have contradicted the immediately-preceding corrected required-secret bullet within the same section.
- **Fix:** Rewrote the bullet to state the actual shipped default (GLM/Z.ai via the OpenAI-compatible path), kept Kimi/Moonshot as one alternative OpenAI-compatible endpoint example, and added Anthropic as an explicit alternative-provider option.
- **Files modified:** README.md (Configure section)
- **Verification:** Re-read the section; `config/tracked.toml` grep confirms `enrichment_provider = "openai"` / `enrichment_model = "glm-4.7-flash"` matches the corrected bullet.
- **Committed in:** ea64584 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 Rule 1 bug fix)
**Impact on plan:** Necessary for README internal consistency within the same task's file/section; no scope creep beyond the enrichment-secret correction Task 2 already required.

## Issues Encountered
- The plan's automated verification commands (Task 3) require the `anthropic` package, which is only installed in the project's `.venv`, not the global `python` interpreter on `PATH`. Ran the Task 3 verification via `.venv/Scripts/python.exe` instead of bare `python`, per the executor's own CLAUDE.md/venv guidance. No code or plan change required.

## User Setup Required

None - no external service configuration required by this plan. Actually wiring the Coolify Scheduled Task in the live Coolify dashboard (creating the scheduled task with the documented command/cron/env) is an operator action outside this repo, deferred as a deploy-time UAT item — see "Next Phase Readiness" below.

## Next Phase Readiness
- SCHED-01 and SCHED-02 are closed/rescoped in planning artifacts; the mechanism (`python -m techtrend.daily`) and the missed-run-visibility fallback (staleness banner) both already exist in code and are verified unmodified.
- **Deferred deploy-time UAT (human, needs live Coolify environment):** actually create the Coolify Scheduled Task per the README instructions and confirm a real unattended cron fire runs `python -m techtrend.daily` successfully end-to-end against the hosted PostgreSQL + GLM/OPENAI_API_KEY — this plan verifies the mechanism and documentation are correct, not that a live 24h scheduled run has actually occurred.
- No blockers for Phase 3 (Source Breadth) or further phases; this rescope only touches planning docs + README, no shared code paths.
- Phase 4's own remaining backlog item: none — Phase 4 has exactly one plan (04-01), and its Success Criteria are fully addressed (SC1/SC3 verified met by existing code, SC2 documented superseded).

---
*Phase: 04-autonomous-daily-scheduling*
*Completed: 2026-08-19*

## Self-Check: PASSED

- FOUND: .planning/ROADMAP.md
- FOUND: .planning/REQUIREMENTS.md
- FOUND: README.md
- FOUND: .planning/phases/04-autonomous-daily-scheduling/04-01-SUMMARY.md
- FOUND commit: 6bcab88 (Task 1)
- FOUND commit: ea64584 (Task 2)
