# Quick Task 260906-nqc: Add a dashboard source filter - Context

**Gathered:** 2026-09-06
**Status:** Ready for planning

<domain>
## Task Boundary

Add a source filter to the read-only dashboard so items can be viewed as separate
lists by origin (GitHub / Hacker News / Packages / Changelogs) instead of one
combined ranked list. Currently `server/queries.py::query_ranked` has NO source
filter, and the sidebar (`web/templates/partials/sidebar.html`) only filters by the
seven topic sections. The new control threads through the `GET /` route
(`server/app.py`) as a query param and reaches SQL as a bound parameter — never
interpolated — mirroring exactly how the existing `section` filter is already
implemented (allow-list discipline like `SORT_KEYS`, `:param` binding).

Scope: presentation + query layer only. The dashboard stays strictly read-only
(D-17). No collector, scorer, or enrichment change.
</domain>

<decisions>
## Implementation Decisions

### Source grouping
- ONE combined **"Packages"** tab covering npm + PyPI together (not separate npm/PyPI
  tabs). Prod has only ~4 npm + ~5 pypi items, so a combined tab is cleaner.
- Implication: the source filter maps a UI label to a SET of DB `source` values, not
  always 1:1. "Packages" → `source IN ('npm','pypi')`; "GitHub" → `source = 'github'`;
  "Hacker News" → `source = 'hn'`; "Changelogs" → `source = 'changelog'`; "All" → no
  source predicate. The filter value passed in the URL must still be a fixed
  allow-list key (e.g. `github` / `hn` / `packages` / `changelog`), mapped
  server-side to the concrete source-value set — the raw source values never come
  from the URL, and the set is bound as SQL parameters (e.g. `= ANY(%(sources)s)` or
  an `IN` over bound params), never string-interpolated.

### Placement
- A horizontal **top tab row** (segmented control) ABOVE the table:
  `All | GitHub | Hacker News | Packages | Changelogs`.
- The existing seven-section filter STAYS in the left sidebar unchanged. The two
  filter axes are visually distinct (source = top tabs, topic = left sidebar).

### Filter composition
- Source and section filters **compose with AND** — e.g. `source=github AND
  section=agentic_coding_tools`. Neither control resets the other, exactly mirroring
  how `sort` and `section` already both ride along on every link/tab. Every source
  tab carries the current `sort` + `section`; every section link and sort header now
  also carries the current `source`. (Pitfall #5: a control must never silently
  reset another control's state.)

### Default view
- Default is **"All sources"** (no source predicate) — the current behavior, so an
  unfiltered dashboard is unchanged. Reached via `source=` empty / absent, matching
  the `section=None` "All" convention already in `query_ranked`.

### Claude's Discretion
- Exact source-key allow-list naming, tab active-state styling, and whether section
  counts in the sidebar should reflect the active source filter — left to the
  planner, BUT keep consistent with the existing precedent: `query_section_counts`
  currently always shows full counts regardless of the section filter
  (`app.py` docstring). Decide deliberately whether the source tab should narrow
  those counts and document the choice; the safe default matching existing behavior
  is that sidebar section counts stay source-independent unless the planner has a
  strong reason otherwise.
- Whether to show a per-tab source count badge (like the section counts) — optional,
  planner's call; not required for the feature.
</decisions>

<specifics>
## Specific Ideas

- Mirror the EXISTING `section` filter end to end — it is the reference
  implementation for this task:
  - `queries.py`: `SORT_KEYS` allow-dict for `sort`; `section_filter = "AND
    enrichments.section = %(section)s" if section else ""`; params bound in a dict.
    Add the analogous source allow-list + `source_filter` fragment bound the same way.
  - `app.py`: `GET /` already takes `sort` and `section` query params and threads
    `section` straight into `query_ranked`; add `source` the same way.
  - `sidebar.html`: every link carries BOTH `sort` and its own `section` via
    `hx-get="/?sort={{ sort }}&section={{ s.id }}"` + `hx-target="#table-body"` etc.
    The new source tabs reuse this exact hx attribute set and also carry `section`;
    existing section links + `table.html` sort headers gain `&source={{ source or '' }}`.
- The htmx swap target is `#table-body`; the source tab row, like the sidebar, must
  live OUTSIDE `#table-body` so it is not swapped away on a sort/section/source GET.
</specifics>

<canonical_refs>
## Canonical References

- `techtrend/server/queries.py` — `query_ranked` (the SQL + allow-list + bound-param
  discipline to mirror), `query_section_counts`.
- `techtrend/server/app.py` — `GET /` route param threading.
- `techtrend/web/templates/partials/sidebar.html` and `partials/table.html` — the
  htmx link/attribute pattern (`hx-get`/`hx-target`/`hx-swap`/`hx-push-url`/
  `hx-indicator`) the source tabs must reuse.
- `techtrend/web/templates/dashboard.html` — layout include points (health strip,
  sidebar, table-content) where the top tab row is inserted.
- Prior quick task 260825-twr already added `entities.source` to the ranked query's
  SELECT for per-row link labeling — the source column is already available; this
  task adds FILTERING on it.
</canonical_refs>
