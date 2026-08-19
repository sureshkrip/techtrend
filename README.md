# TechTrend

A personal, self-updating intelligence dashboard for the AI-coding and LLM ecosystem. It pulls daily from high-signal sources, ranks what it finds by **momentum** (not absolute popularity), has an LLM summarize and file the survivors into seven fixed sections, and links each tracked tool to its docs. Built for a single local user — open it once a day and know, in five minutes, what is actually gaining traction.

> **Status:** v1.0 in progress. The live source today is **GitHub** (collection, velocity scoring, and LLM enrichment). Additional sources (Hacker News, npm/PyPI, vendor changelogs) and autonomous scheduling are planned.

## Prerequisites

- **Python 3.12+** (the Docker image uses 3.13)
- **[uv](https://github.com/astral-sh/uv)** for dependency management
- **A running PostgreSQL server** for real (non-test) runs, with a `techtrend` database and a `techuser` role. Connection is configured via discrete env vars: `PGHOST` (default `localhost`), `PGPORT` (default `5432`), `PGDATABASE` (default `techtrend`), `PGUSER` (default `techuser`), `PGPASSWORD` (set in your `.env`; no default).
- **Local PostgreSQL binaries on `PATH`** (`initdb` / `pg_ctl`) to run the test suite — `pytest-postgresql` provisions a throwaway cluster per run from these binaries and needs no Docker and no already-running server.

## Install

```bash
uv sync
```

This creates a `.venv/` with all pinned dependencies from `uv.lock`.

## Configure

1. Copy the example env file and fill in your secrets:

   ```bash
   cp .env.example .env
   ```

2. Set the credentials in `.env`:
   - **`GITHUB_TOKEN`** — required for live collection and stargazer backfill (a valid, unexpired token; requests fail with `401` otherwise).
   - **`OPENAI_API_KEY`** — required for the enrichment stage (two-line summaries + section assignment). This is the required secret for the deployed default enrichment provider, GLM (Zhipu/Z.ai) via the OpenAI-compatible endpoint — see `enrichment_provider = "openai"` below. Anthropic Claude remains a documented alternative provider (set `ANTHROPIC_API_KEY` instead if you switch `enrichment_provider` back to `"anthropic"`). Neither key is required if `TECHTREND_DISABLE_LLM` is set (see below).
   - **`PGPASSWORD`** — the password for your PostgreSQL `techuser` role (see Prerequisites). `PGHOST`/`PGPORT`/`PGDATABASE`/`PGUSER` default to `localhost`/`5432`/`techtrend`/`techuser` and only need to be set if your server differs.

Other configuration:
- **Tunables** (ranking window, floors, caps, section taxonomy) live in `config/tracked.toml`. Point at a different file with `TECHTREND_CONFIG=/path/to/config.toml`.
- **Enrichment provider** — the shipped default (`config/tracked.toml`) is GLM-4.7-Flash (Zhipu/Z.ai) via the OpenAI-compatible endpoint (`enrichment_provider = "openai"`, `enrichment_model = "glm-4.7-flash"`, `enrichment_base_url = "https://api.z.ai/api/paas/v4/"`), using `OPENAI_API_KEY` as set above. Any OpenAI-compatible endpoint works the same way — e.g. to route to Kimi/Moonshot instead, set under `[tunables]` in `config/tracked.toml`:
  ```toml
  [tunables]
  enrichment_provider = "openai"
  enrichment_model = "kimi-k2.5"
  enrichment_base_url = "https://api.moonshot.ai/v1"
  ```
  Anthropic Claude is also a documented alternative — set `enrichment_provider = "anthropic"` and `ANTHROPIC_API_KEY` in `.env` instead. In every case, only the key matching the active `enrichment_provider` is required, and neither is required if `TECHTREND_DISABLE_LLM` is set.
- **`TECHTREND_DISABLE_LLM`** — a runtime env switch (truthy values `1`/`true`/`yes`/`on`)
  that skips the enrichment LLM/summary stage entirely: when set, no LLM calls are made
  and neither `OPENAI_API_KEY` nor `ANTHROPIC_API_KEY` is required. The pipeline still
  collects and scores, and the run is recorded with a `run_manifest` `disabled` status.
  Toggleable in the Coolify deploy environment without editing config files.
- **Data location** — storage is PostgreSQL (see Prerequisites), not a filesystem path. The HTTP cache and log file still default to the repo root; override with `TECHTREND_DATA_DIR=/path/to/data`. The database schema initializes itself on first run against the configured Postgres server — there is no separate migration step.

## Run

**Daily full pipeline** — collect → score → enrich, in order, fail-fast (the first stage to fail halts the chain and propagates its exit code):

```bash
python -m techtrend.daily
```

**Individual stages** (same order):

```bash
python -m techtrend.ingest   # collect + backfill (does not score/enrich)
python -m techtrend.score    # compute velocity scores + ranking gate
python -m techtrend.enrich   # LLM summarize + section-assign the survivors
```

**Offline dev run** (no tokens, no network — replays a bundled fixture):

```bash
python -m techtrend.ingest --fixture
python -m techtrend.score
```

## Dashboard

```bash
uvicorn techtrend.server.app:app
```

Then open **http://localhost:8000**. The dashboard is strictly read-only — it renders the current DB state and **never triggers a pipeline run** on load. Run the pipeline (above) to refresh its data.

## Tests

```bash
pytest
```

Requires local PostgreSQL binaries (`initdb` / `pg_ctl`) on `PATH` — `pytest-postgresql` provisions a throwaway cluster per test run automatically; no Docker and no running server needed.

## Deploy (Docker / Coolify)

The included `Dockerfile` builds a single image that serves the dashboard; the daily pipeline runs as a scheduled task inside the same container, both connecting to the same PostgreSQL server.

1. Build the image (Coolify does this from the repo).
2. **Point the app at a durable PostgreSQL server** — set `PGHOST`/`PGPORT`/`PGDATABASE`/`PGUSER`/`PGPASSWORD` in the deploy environment. This is where snapshot history now lives; it is not affected by container redeploys.
3. Optionally mount a persistent volume at `/data` and set `TECHTREND_DATA_DIR=/data` to persist the HTTP cache and logs across redeploys (not required for data durability — that's the Postgres server's job now).
4. Set the secrets `GITHUB_TOKEN` (collection/backfill) and `OPENAI_API_KEY` (the deployed GLM enrichment provider) in the deploy environment. Set `TECHTREND_DISABLE_LLM=1` instead if you want the scheduled run to only collect + score, with no LLM key required at all.
5. **Configure a Coolify Scheduled Task** to run the daily pipeline — this is the mechanism that makes the pipeline run automatically once per day (SCHED-01):
   - **Command:** `python -m techtrend.daily` — the single chained entrypoint that runs collect → score → enrich in order, fail-fast (the first stage to fail halts the chain and the run is recorded accordingly).
   - **Schedule:** a daily cron expression, defaulting to `0 6 * * *` (06:00 UTC) — adjust the time to taste.
   - **Environment:** the scheduled task runs inside the same container/image as the dashboard, so it inherits the same deploy environment set in steps 2 and 4 above (PG* connection vars, `GITHUB_TOKEN`, `OPENAI_API_KEY` or `TECHTREND_DISABLE_LLM`).
6. The container's default command serves the dashboard on port `8000` via `uvicorn` — **serving and the scheduled pipeline run are independent** (D-17): the dashboard never triggers a pipeline run on request, and the scheduled task never depends on the dashboard being open or receiving traffic.
7. **Missed-run handling is cron-only, by design — no catch-up/backfill code.** If the container is down at the scheduled fire time, that day is simply skipped; there is no wake-timer or run-if-missed mechanism (that was the original Windows-desktop scoping, superseded now that the deployment is an always-on hosted server — see ROADMAP.md Phase 4). A skipped day is still made visible, not silent: the dashboard's existing "Last successful run: …" / "Data may be out of date — last successful run was …" staleness banner (`techtrend/server/health.py`) reflects it immediately on next load.

## First run is sparse — this is expected

On a fresh install the dashboard will show few or no ranked rows for roughly the first week. GitHub restricted the stargazer-history endpoint used for day-one backfill, so velocity is reconstructed only from **observed** daily snapshots as they accrue. An item with only a day or two of history legitimately falls below the ranking floor and is honestly excluded rather than shown with a fabricated score. The list fills in as snapshots build up — an empty/sparse early dashboard means "still gathering data," not a failure.
