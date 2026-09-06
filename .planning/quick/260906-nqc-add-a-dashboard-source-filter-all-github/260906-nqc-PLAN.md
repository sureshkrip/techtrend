---
phase: quick-260906-nqc
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - techtrend/server/queries.py
  - techtrend/server/app.py
  - techtrend/web/templates/dashboard.html
  - techtrend/web/templates/partials/source_tabs.html
  - techtrend/web/templates/partials/sidebar.html
  - techtrend/web/templates/partials/table.html
  - tests/test_dashboard.py
autonomous: true
requirements: [DASH-02, T-01-06, T-01-29, D-17]

must_haves:
  truths:
    - "Opening the dashboard with no source param shows every source (current unfiltered behavior, byte-for-byte unchanged)."
    - "Clicking a source tab (GitHub / Hacker News / Packages / Changelogs) narrows the table to that source group only."
    - "The Packages tab shows both npm AND pypi rows (one combined group)."
    - "Source and section filters compose with AND; neither control resets the other's active state in the URL."
    - "An unrecognized ?source= value falls back to All (no predicate), never reaches SQL as raw text, and renders the All tab active."
    - "Every sort header and every section link round-trips the currently active source."
  artifacts:
    - techtrend/server/queries.py
    - techtrend/web/templates/partials/source_tabs.html
    - tests/test_dashboard.py
  key_links:
    - "URL allow-list key -> SOURCE_KEYS -> bound `sources` array param -> `entities.source = ANY(%(sources)s)` (never interpolated)."
    - "query_ranked returns applied_source -> app.py context `source` -> source_tabs active state + sidebar/table `&source=` carry-through."
---

<objective>
Add a source filter to the read-only dashboard so items can be viewed as separate
lists by origin (All / GitHub / Hacker News / Packages / Changelogs), composing with
the existing section filter and sort. The control mirrors the existing `section`
filter end to end: an allow-list KEY in the URL, mapped server-side to a concrete
set of `entities.source` values, bound as a SQL array parameter — never interpolated.

Purpose: let the owner scan one source at a time instead of one merged ranked list,
without losing the seven-section topic filter or the active sort.
Output: SOURCE_KEYS allow-list + `source_filter` fragment in queries.py, `source`
threading through GET /, a horizontal top-tab partial, `&source=` carry-through on
every existing control, and fixture-backed multi-source tests.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/quick/260906-nqc-add-a-dashboard-source-filter-all-github/260906-nqc-CONTEXT.md
@techtrend/server/queries.py
@techtrend/server/app.py
@techtrend/web/templates/dashboard.html
@techtrend/web/templates/partials/sidebar.html
@techtrend/web/templates/partials/table.html
@tests/test_dashboard.py
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add source allow-list + bound-param filter to the query and route layer</name>
  <files>techtrend/server/queries.py, techtrend/server/app.py</files>
  <behavior>
    - SOURCE_KEYS maps exactly {github: [github], hn: [hn], packages: [npm, pypi], changelog: [changelog]}.
    - query_ranked(conn, sort, section, source): recognized source -> rows restricted to that source group; unrecognized/empty/None source -> no source predicate (All), same rows as before.
    - The Packages key returns rows whose source is npm OR pypi.
    - Source composes with section (AND) and with sort independently.
    - query_ranked returns applied_source (the normalized key actually used, or None), mirroring applied_sort.
  </behavior>
  <action>
    In queries.py, add a `SOURCE_KEYS: dict[str, list[str]]` allow-dict directly beneath
    `SORT_KEYS`, mapping each fixed URL key to its concrete `entities.source` value set:
    `github -> [github]`, `hn -> [hn]`, `packages -> [npm, pypi]`, `changelog -> [changelog]`.
    This is the source analogue of SORT_KEYS: the URL only ever carries a key, and raw
    source values live only in this server-side table (never in the URL).

    Extend the `query_ranked` signature to `query_ranked(conn, sort=DEFAULT_SORT,
    section=None, source=None)` and its return to the 3-tuple
    `(rows, applied_sort, applied_source)`. Compute
    `applied_source = source if source in SOURCE_KEYS else None` — an unrecognized value
    falls back to All (no predicate) exactly as an unrecognized sort falls back to
    DEFAULT_SORT (T-01-06/T-01-29). Build
    `source_filter = "AND entities.source = ANY(%(sources)s)" if applied_source else ""`
    and add a `{source_filter}` placeholder to `_QUERY_RANKED_SQL` immediately after the
    existing `{section_filter}` placeholder. When applied_source is set, add
    `params["sources"] = SOURCE_KEYS[applied_source]` (a Python list, bound by psycopg 3
    as a SQL array for the ANY predicate) — the concrete source values are bound
    parameters, never string-formatted into the SQL. Update the `.format(...)` call to
    pass `source_filter=source_filter`. Update the query_ranked docstring to describe the
    source allow-list and bound-param discipline, matching the existing section paragraph.

    Do NOT change query_section_counts: per the locked decision, sidebar section counts
    stay source-independent (they already ignore the section filter — same precedent).
    Add a one-line note in query_section_counts' docstring that counts are deliberately
    global across sources so the sidebar totals never shift as the source tab changes.

    In app.py, add `source: str | None = None` to the `dashboard(...)` route signature.
    Capture the third return value: `rows, applied_sort, applied_source =
    query_ranked(conn, sort=sort, section=section, source=source)`. Initialize
    `applied_source = source` alongside `applied_sort = sort` before the try block (so a
    DB error path still has a defined value). Add `"source": applied_source` to the
    TemplateResponse context dict. Update the route docstring to note `source` threads
    through to query_ranked the same way `section` does and (like section) never affects
    query_section_counts.
  </action>
  <verify>
    <automated>cd C:/Users/sures/dev/repos/techtrend && ruff check techtrend/server/queries.py techtrend/server/app.py && python -c "from techtrend.server.queries import SOURCE_KEYS, query_ranked; import inspect; assert set(SOURCE_KEYS)=={'github','hn','packages','changelog'}; assert SOURCE_KEYS['packages']==['npm','pypi'] and SOURCE_KEYS['github']==['github']; p=inspect.signature(query_ranked).parameters; assert 'source' in p; print('ok')"</automated>
  </verify>
  <done>SOURCE_KEYS exists with the four keys and the packages group [npm, pypi]; query_ranked accepts `source`, applies `= ANY(%(sources)s)` only for recognized keys, returns applied_source; the app route accepts and threads `source` and exposes it in template context; query_section_counts is unchanged. ruff clean.</done>
</task>

<task type="auto">
  <name>Task 2: Add the top source-tab row and carry `source` through every existing control</name>
  <files>techtrend/web/templates/partials/source_tabs.html, techtrend/web/templates/dashboard.html, techtrend/web/templates/partials/sidebar.html, techtrend/web/templates/partials/table.html</files>
  <action>
    Create `techtrend/web/templates/partials/source_tabs.html`: a horizontal segmented
    tab row rendering, in order, All | GitHub | Hacker News | Packages | Changelogs.
    Model each tab on sidebar.html's link pattern — same
    `hx-target="#table-body" hx-swap="innerHTML" hx-push-url="true"
    hx-indicator="#table-body"` attribute set. Each tab's `hx-get` carries the current
    sort AND section AND its own source key:
    `hx-get="/?sort={{ sort }}&section={{ section or '' }}&source=<key>"`, where the All
    tab uses `source=` (empty). Give the row a wrapping element with a class such as
    `source-tabs` and each tab a class such as `source-tab`, adding a
    `source-tab-active` modifier when that tab's key equals the current `source` (and the
    All tab active when `source` is falsy) — mirroring sidebar.html's `section-active`
    convention. Add a header comment matching sidebar.html's: the tab row lives OUTSIDE
    #table-body so an htmx swap never removes it, and `hx-push-url="true"` keeps the
    address bar authoritative for which tab renders active on refresh/back/forward (the
    in-page swap updates only #table-body, exactly as the sidebar already behaves).

    In dashboard.html, include the new partial inside `.table-content` ABOVE the `<table>`
    element and OUTSIDE `<tbody id="table-body">`, so it is not swapped away on a
    sort/section/source GET: add `{% include "partials/source_tabs.html" %}` between the
    `<div class="table-content">` open tag and the `<table>`.

    In sidebar.html, append `&source={{ source or '' }}` to the `hx-get` of BOTH the "All"
    section link and each per-section link, so changing section preserves the active
    source (Pitfall #5). In table.html, append `&source={{ source or '' }}` to the
    `hx-get` of all four sort-header links (name/velocity/gained/stars), so re-sorting
    preserves the active source.

    In table.html, add an honest source-filtered empty state: change the existing
    `{% elif section %}` empty branch so a source-only filter that matches zero rows also
    gets a filter-specific message rather than falling through to "No data yet". Add a
    new `{% elif source %}` branch AFTER the `{% elif section %}` branch (before the
    `{% elif has_successful_run %}` branch) with copy along the lines of a heading "No
    items from this source yet" and a short line telling the user to check back or view
    "All". Keep `colspan="7"` consistent with the other empty-state rows.
  </action>
  <verify>
    <automated>cd C:/Users/sures/dev/repos/techtrend && grep -q 'source_tabs.html' techtrend/web/templates/dashboard.html && grep -q 'source={{ source' techtrend/web/templates/partials/sidebar.html && grep -q 'source={{ source' techtrend/web/templates/partials/table.html && grep -q 'source-tab' techtrend/web/templates/partials/source_tabs.html && python -c "from jinja2 import Environment, FileSystemLoader; Environment(loader=FileSystemLoader('techtrend/web/templates')).get_template('partials/source_tabs.html'); print('tab template parses')"</automated>
  </verify>
  <done>source_tabs.html exists and parses, is included in dashboard.html above the table and outside #table-body, and renders five tabs each carrying current sort+section. Every sidebar section link and every table sort header now also carries `&source={{ source or '' }}`. A source filter matching zero rows shows an honest source-specific empty state.</done>
</task>

<task type="auto">
  <name>Task 3: Fixture-backed tests for source filtering, composition, fallback, and link round-trip</name>
  <files>tests/test_dashboard.py</files>
  <action>
    Add tests to tests/test_dashboard.py mirroring the existing style exactly:
    fixture-backed (`db, pg_env`), synthetic rows inserted via the existing
    `_insert_entity` / `_insert_score` / `_insert_enrichment` helpers (the local dev DB is
    github-only, so multi-source rows MUST be synthesized — never assume local data), and
    assertions against `client.get(...)` response text. Cover:

    1. Default / All: `client.get("/")` (no source param) shows rows from multiple
       sources (insert one github, one hn, one npm, one pypi, one changelog entity, all
       eligible) — every source's full_name appears; establishes the unchanged baseline.
    2. Single-source tabs: `?source=github` shows only the github row; `?source=hn` only
       hn; `?source=changelog` only changelog — the other sources' full_names are absent.
    3. Packages IN-group: `?source=packages` shows BOTH the npm AND the pypi row, and
       excludes github/hn/changelog rows — proves the combined group maps to
       source IN (npm, pypi).
    4. Composition (AND): give a github entity and an hn entity the SAME enrichment
       section; `?source=github&section=<that section>` shows only the github row (source
       AND section both applied), while `?section=<that section>` alone (no source) shows
       both.
    5. Unknown source falls back to All: `?source=nonsense` returns 200 and shows the same
       rows as `/` (no predicate) — mirror the existing unrecognized-sort fallback test.
    6. Link round-trip: request `?source=hn` and assert the rendered sort-header links and
       sidebar section links carry `source=hn` (the active source is preserved on every
       control, Pitfall #5). Reuse / extend `_sort_link_html` if convenient — its regex
       already tolerates a trailing `&section=[^"]*`, which also absorbs a following
       `&source=...`; assert `source=hn` appears within the rendered header link block.

    Do not weaken any existing assertion. If the `_sort_link_html` helper needs a small
    tweak to also surface the source param, keep it backward-compatible with the existing
    sort/section tests.
  </action>
  <verify>
    <automated>cd C:/Users/sures/dev/repos/techtrend && python -m pytest tests/test_dashboard.py -x -q</automated>
  </verify>
  <done>New tests cover All/no-predicate, each single-source tab, the packages npm+pypi group, source+section AND composition, unknown-source fallback to All, and active-source round-trip on sort headers + section links. The full tests/test_dashboard.py suite passes with no regressions.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| browser -> GET / (`source` query param) | Untrusted URL text crosses into the query layer; must never reach SQL as raw text. |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-nqc-01 | Tampering | `source` param -> query_ranked SQL | high | mitigate | URL carries only an allow-list KEY (SOURCE_KEYS); unrecognized -> None (no predicate). Concrete source values bound as a `sources` array param via `= ANY(%(sources)s)`, never string-interpolated — same discipline as SORT_KEYS/section (T-01-06/T-01-29). |
| T-nqc-02 | Information Disclosure | dashboard route | low | accept | Dashboard is strictly read-only (D-17); SELECT-only, single-user, no auth surface. Source filter adds no write path. |
| T-nqc-03 | Tampering | dependency installs | low | accept | No new packages installed (uses stdlib + existing psycopg 3 / Jinja2 / FastAPI). No package-legitimacy checkpoint required. |
</threat_model>

<verification>
- ruff clean on queries.py and app.py.
- `python -m pytest tests/test_dashboard.py -x -q` passes (new source tests + all existing).
- Manual spot check (optional): `uvicorn techtrend.server.app:app` and click through
  All / GitHub / Hacker News / Packages / Changelogs — table narrows, sort + section
  persist in the URL, tab row stays visible across swaps.
</verification>

<success_criteria>
- The dashboard shows a top tab row All | GitHub | Hacker News | Packages | Changelogs above the table and outside #table-body.
- Selecting a source narrows the table to that source group (Packages = npm + pypi); All shows the unchanged unfiltered list.
- Source AND section compose; sort, section, and source all round-trip on every control without resetting one another.
- The URL `source` param is an allow-list key bound to SQL only via a parameterized array; unknown values fall back to All.
- Sidebar section counts remain source-independent (documented, matches existing precedent).
</success_criteria>

<output>
Create `.planning/quick/260906-nqc-add-a-dashboard-source-filter-all-github/260906-nqc-SUMMARY.md` when done.
</output>
