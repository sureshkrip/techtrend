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
   - **`ANTHROPIC_API_KEY`** — required for the enrichment stage (two-line summaries + section assignment via Claude Haiku). This is the default provider — skip the rest of this bullet if you're not switching providers.
   - **`PGPASSWORD`** — the password for your PostgreSQL `techuser` role (see Prerequisites). `PGHOST`/`PGPORT`/`PGDATABASE`/`PGUSER` default to `localhost`/`5432`/`techtrend`/`techuser` and only need to be set if your server differs.

Other configuration:
- **Tunables** (ranking window, floors, caps, section taxonomy) live in `config/tracked.toml`. Point at a different file with `TECHTREND_CONFIG=/path/to/config.toml`.
- **Alternative LLM provider (Kimi/Moonshot)** — the enrichment stage defaults to Anthropic Haiku 4.5. To route it to Kimi/Moonshot's OpenAI-compatible endpoint instead, set under `[tunables]` in `config/tracked.toml`:
  ```toml
  [tunables]
  enrichment_provider = "openai"
  enrichment_model = "kimi-k2.5"
  # enrichment_base_url = "https://api.moonshot.ai/v1"  # optional, this is the default
  ```
  and set **`OPENAI_API_KEY`** in `.env`.
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
4. Set the secrets `GITHUB_TOKEN` and `ANTHROPIC_API_KEY` in the deploy environment.
5. Configure a **scheduled task** to run the daily pipeline:

   ```bash
   python -m techtrend.daily
   ```

6. The container's default command serves the dashboard on port `8000` via `uvicorn` — serving and the scheduled pipeline run are independent (serving never triggers collection).

## First run is sparse — this is expected

On a fresh install the dashboard will show few or no ranked rows for roughly the first week. GitHub restricted the stargazer-history endpoint used for day-one backfill, so velocity is reconstructed only from **observed** daily snapshots as they accrue. An item with only a day or two of history legitimately falls below the ranking floor and is honestly excluded rather than shown with a fabricated score. The list fills in as snapshots build up — an empty/sparse early dashboard means "still gathering data," not a failure.
