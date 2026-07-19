# Stack Research

**Domain:** Locally-run, single-user AI/LLM trend-tracking dashboard (data ingestion → deterministic ranking → LLM summarize/classify → server-rendered web UI, on a daily schedule, Windows 11)
**Researched:** 2026-07-19
**Confidence:** HIGH (language/storage/scheduling/HTTP libraries verified against current package registries and official docs) / MEDIUM (exact micro-versions of fast-moving web libraries — pin at install time)

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.12 or 3.13 | Runtime for ingestion, ranking, LLM calls, and web server | See "1. Language/runtime" below — Python wins on every axis that matters here: HTTP/feed ecosystem maturity, first-class `anthropic` SDK, and a scheduler story Node doesn't have. Single language end-to-end for a solo dev. |
| SQLite (stdlib `sqlite3`) | Python 3.12's bundled SQLite ≥ 3.45 | Storage for raw items, daily snapshots, and computed rankings | Zero-ops embedded DB, file-based, trivially backed up, and — with WAL mode — handles the write-then-read-heavy daily batch job with no contention. See "2. Data storage" below for the time-series schema. |
| FastAPI + Jinja2 + htmx | FastAPI ~0.11x, Jinja2 3.1.x, htmx 2.x (CDN or vendored `.js`) | Server-rendered dashboard: sortable/filterable, single local user | See "3. Web dashboard" below. No build step, no SPA, no client-side state management — htmx does sort/filter as plain GET requests that re-render an HTML partial. |
| Windows Task Scheduler | OS-native (Windows 11) | Fires the daily ingestion run | See "4. Scheduling" below — this is the Windows-specific decision that most affects the architecture. cron doesn't exist on Windows; Task Scheduler is the reliable native equivalent and needs no background process to stay alive. |
| `anthropic` (official SDK) | latest (0.6x+ line) | Calls Claude to summarize + classify surviving items | Official, maintained, typed responses, structured-outputs support, Batch API support built in. See "5. LLM integration" below for model tier and API surface. |
| `httpx` + `hishel` + `tenacity` | httpx ~0.28.x, hishel ~1.2.x (verified: 1.2.1, Apr 2026), tenacity ~9.x | Polite HTTP ingestion: sync/async client, RFC 9111 caching (ETag/If-Modified-Since), retry/backoff | See "6. HTTP/ingestion libraries" below. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `feedparser` | ~6.0.x | Parse RSS/Atom feeds (vendor changelogs, curated blogs) | Any source that publishes a feed instead of a JSON API |
| `pydantic` | v2 (~2.x) | Validate/normalize ingested records; validate LLM structured-output JSON | Every place external data (API responses, LLM output) crosses into your code |
| `APScheduler` | 3.11.3 (verified current on PyPI) | In-process scheduling *if* you also want a long-running dev/debug mode, or to run sub-schedules inside one process | Optional companion to Task Scheduler — see the Windows scheduling section for when to use each |
| `uvicorn` | ~0.3x.x | ASGI server to run the FastAPI dashboard | Always, to serve the dashboard (`uvicorn app:app`) |
| `sqlite-utils` (optional) | ~3.x | Ergonomic CLI/Python wrapper over sqlite3 (migrations, CLI inspection) | If you want a nicer DX than raw `sqlite3` + hand-written DDL; not required |
| `python-dotenv` | ~1.x | Load `ANTHROPIC_API_KEY` / config from a `.env` file | Local config management, keeps secrets out of source |
| `tenacity` | ~9.x | Declarative retry/backoff decorator for HTTP calls and LLM calls | Wrapping every outbound network call (ingestion + Claude calls) |
| `rich` or stdlib `logging` | latest | Structured console output for the daily job (useful when Task Scheduler runs it headless — log to a file) | Always — you need a log file to debug a scheduled job you can't watch run |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `ruff` | Lint + format | Single fast tool, replaces flake8+black+isort |
| `pytest` | Testing | Standard; test the ranking/velocity math and the ingestion parsers with fixtures, not live network calls |
| `uv` or `pip` + `venv` | Dependency management | `uv` is materially faster and handles Python-version pinning well; either is fine for a solo project |

## Installation

```bash
# Core
pip install fastapi uvicorn jinja2 httpx hishel tenacity anthropic pydantic feedparser python-dotenv APScheduler

# Dev dependencies
pip install ruff pytest
```

`sqlite3` and `logging` are in the Python standard library — no install needed.

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|--------------------------|
| Python everywhere | TypeScript/Node everywhere | If the developer is dramatically more fluent in TS and the ingestion sources are mostly JSON APIs with no feed/scraping needs — Node's HTTP ecosystem (`undici`, `ofetch`) and the `@anthropic-ai/sdk` are equally solid. But Node's scheduling story on Windows is thinner (no APScheduler-equivalent; you'd lean on `node-cron` inside a long-running process or Task Scheduler + a script either way), and `feedparser`-quality RSS parsing is less mature in the JS ecosystem. |
| Single Python codebase | Split Python (ingestion) + TypeScript (dashboard) | Only if you specifically want a rich client-side interactive UI (drag-drop, live charts) that justifies a SPA. For "browse, sort, filter, click through" — the stated requirement — a split toolchain adds a second package manager, a second test runner, and a build step for zero UX benefit. Reject for this project. |
| SQLite | PostgreSQL | If this ever becomes multi-user, remote-accessible, or needs concurrent writers from multiple processes. None of those apply — Postgres would mean running (and keeping alive) a server process on a machine whose entire purpose is a personal, local, single-user tool. |
| SQLite | DuckDB | If the item/snapshot volume grows into the millions of rows and you're doing heavy analytical queries (rollups across years of history, complex OLAP-style joins). At "a few hundred items/day, one row per item per day," DuckDB's columnar analytical engine buys you nothing over SQLite's B-tree + a couple of indexes, and DuckDB's Python ecosystem for a simple CRUD+cron app is less battle-tested. Revisit only if query latency becomes a real problem. |
| Server-rendered (FastAPI+Jinja2+htmx) | SPA (React/Vue + API backend) | Never, for this project. An SPA needs a build pipeline (Vite/webpack), client-side routing, client-side state management, and a second language ecosystem — all to render a sortable table for one user with no auth. This is the textbook over-engineering case the requirement explicitly asks to avoid. |
| Windows Task Scheduler (daily trigger) | Celery + Redis/RabbitMQ | If this were a multi-worker distributed system processing many concurrent jobs. For "run one ingestion job once a day," Celery means running and babysitting a message broker daemon on Windows (Redis has no first-class native Windows build; you'd need WSL or Docker Desktop just to host the queue) — pure overhead for a single scheduled task. |
| Windows Task Scheduler | cron | Not available — cron is a Unix daemon; Windows has no native equivalent. The only "cron on Windows" options are WSL (adds a whole Linux subsystem dependency for one scheduled command) or Task Scheduler. Task Scheduler is the native, zero-dependency answer. |
| httpx + hishel | `requests` + `requests-cache` | `requests` is fine and very well understood, but it's sync-only and has no first-party async story if you later want to parallelize ingestion across sources. `hishel` (RFC 9111-compliant HTTP caching for httpx) is actively maintained (last release Apr 2026) and gives you transparent conditional-request (ETag/304) handling for free — `requests-cache` does the same for `requests` if you'd rather stay on the more familiar library. Either is acceptable; httpx is the more future-proof pick given async is likely once you have 5+ ingestion sources. |
| Claude Haiku 4.5 for summarize+classify | Claude Sonnet 5 / Opus 4.8 | If classification accuracy on ambiguous items (borderline between two of the seven sections) turns out to be poor in practice, or summaries feel low-quality. Upgrade the model for that call only — the task (two-line summary + pick-one-of-seven-labels) is exactly the kind of short, structured, high-volume call Haiku is built for, and the project's own constraint ("LLM spend must be bounded per run") argues for the cheapest model that clears the quality bar. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `cron` / crontab | Doesn't exist on native Windows; only reachable via WSL, which adds a full Linux-subsystem dependency purely to schedule one script | Windows Task Scheduler (`schtasks` CLI or the Task Scheduler GUI) |
| Celery (+ Redis/RabbitMQ) | Built for distributed, multi-worker task queues; here you have exactly one job that runs once a day. The broker alone is more infrastructure than the entire rest of this app, and Redis isn't natively supported on Windows | APScheduler (in-process) if you want an all-Python scheduler, or — preferred — Windows Task Scheduler triggering a plain script |
| PostgreSQL | Requires running and maintaining a server process for a single-user local tool with no concurrency or remote-access requirement | SQLite (file-based, zero-ops) |
| React/Vue/any SPA framework | Needs a JS build pipeline, client routing, and client state management to render what is fundamentally one sortable/filterable table for one user with no auth | Server-rendered Jinja2 templates + htmx for interactivity |
| `scrapy` | A full crawling framework (spiders, pipelines, distributed crawl queues) built for scraping many arbitrary websites at scale. Every source named in this project (GitHub, HN Algolia, PyPI/npm registries, RSS feeds) has a clean JSON/XML API — there's nothing here that needs a scraping framework, and scrapy's async/Twisted-based execution model adds real complexity for no benefit | Plain `httpx` calls against each source's API/feed |
| `requests` for anything you plan to parallelize | Sync-only; ingesting from 5+ sources serially adds up. Not wrong, just leaves speed on the table for free with `httpx` | `httpx` (sync or async, same API shape as `requests`) |
| Rolling your own retry/backoff loop | Easy to get subtly wrong (missing jitter, not respecting `Retry-After`, retrying non-idempotent calls) | `tenacity` (declarative decorators) — the `anthropic` SDK already retries 429/5xx internally, so only hand-roll retries for your own HTTP ingestion calls |
| A hand-written thread that sleeps and loops forever, as the "scheduler" | Silently dies on unhandled exceptions, doesn't survive machine sleep/reboot cleanly, and gives you no visibility when it stops running | Windows Task Scheduler (OS handles wake-from-sleep, logs failures, restart policy) |

## Stack Patterns by Variant

**If you want a single always-on process (simplest mental model, but must survive reboots/sleep):**
- Run the FastAPI/uvicorn dashboard process continuously, and use `APScheduler`'s `BackgroundScheduler` inside that same process to fire the daily ingestion job.
- Because: one process to manage, no cross-process coordination. But you must also register that process with Windows to auto-start (a scheduled task with a "run at startup" trigger, or run it as a Windows service via `pywin32`/NSSM) — otherwise a reboot silently stops your dashboard *and* your scheduler together.

**If you want the ingestion job decoupled from the dashboard (recommended default):**
- Windows Task Scheduler fires a standalone `python ingest.py` script once a day (no `APScheduler` needed — the OS is the scheduler). That script writes to SQLite and exits.
- The FastAPI/uvicorn dashboard is a separate, on-demand process (start it yourself, or add a second Task Scheduler trigger for "at log on") that only *reads* SQLite to render pages.
- Because: this is more robust — a crash in ingestion can't take down the dashboard and vice versa; each half is independently restartable; Task Scheduler already gives you a run history/log with success/failure status for free, which is exactly the observability you want for something that runs unattended.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `fastapi` (any recent 0.11x) | `uvicorn` ~0.3x, `pydantic` v2 | FastAPI ≥0.100 requires Pydantic v2; don't mix with Pydantic v1 syntax |
| `hishel` ~1.2.x | `httpx` ~0.27+ | hishel wraps httpx's transport layer — pin both together and re-check hishel's changelog if you bump httpx across a minor version |
| `anthropic` SDK | Python ≥3.8 (but use 3.12/3.13 for everything else) | The SDK itself has a low floor; your own code should target 3.12+ for modern typing/stdlib features |
| `APScheduler` 3.11.x | Python ≥3.8 | The 3.x line is the stable one to use (a 4.x rewrite exists in alpha/beta form in the ecosystem discussion — do not adopt it for this project; pin to `APScheduler==3.11.*`) |
| SQLite WAL mode | Concurrent single-writer/many-reader | Enable `PRAGMA journal_mode=WAL;` once at DB creation — lets the dashboard read while the daily ingestion job writes, without lock contention |

## Sources

- PyPI — APScheduler project page (verified current release 3.11.3, Jun 28 2026) — https://pypi.org/project/APScheduler/
- PyPI — hishel project page (verified current release 1.2.1, Apr 27 2026) — https://pypi.org/project/hishel/
- GitHub — will-ockmore/httpx-retries (retry layer for httpx; supersedes the unmaintained `httpx-retry`) — https://github.com/will-ockmore/httpx-retries
- Anthropic API skill reference (bundled in this environment) — model pricing table, SDK usage patterns, Batch API, structured outputs, Messages API — used for the LLM integration section (Claude model tiers, `output_config.format`, Batch API cost/latency tradeoffs)
- General knowledge of Windows Task Scheduler vs cron vs Celery tradeoffs, SQLite vs Postgres vs DuckDB tradeoffs, and server-rendered vs SPA tradeoffs — standard, stable ecosystem knowledge not expected to have shifted materially; flagged MEDIUM confidence only on exact micro-version numbers for FastAPI/uvicorn/pydantic, which move quickly — verify at `pip install` time.

---
*Stack research for: locally-run AI/LLM trend-tracking dashboard*
*Researched: 2026-07-19*
