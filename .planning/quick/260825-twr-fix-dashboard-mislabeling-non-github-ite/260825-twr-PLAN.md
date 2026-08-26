---
phase: quick-260825-twr
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - techtrend/server/queries.py
  - techtrend/web/templates/partials/table.html
  - tests/test_dashboard.py
autonomous: true
requirements: [DASH-04, DASH-05, D3-5]
must_haves:
  truths:
    - "A Hacker News row shows 'View on HN' (not 'View on GitHub')"
    - "A non-GitHub row renders no bogus second 'Repo'/'Docs' link"
    - "A GitHub row renders exactly as before (primary 'View on GitHub' + Docs/Repo second link)"
    - "The name-column header reads 'Item', not 'Repo'"
  artifacts:
    - techtrend/server/queries.py
    - techtrend/web/templates/partials/table.html
    - tests/test_dashboard.py
  key_links:
    - "query_ranked selects entities.source so table.html can branch row['source']"
---

<objective>
Make the dashboard presentation layer source-aware so non-GitHub items
(Hacker News, npm, PyPI, changelog) stop being mislabeled as GitHub repos.

The backend is already source-agnostic — each `entities` row carries a
`source` column (`github`/`hn`/`npm`/`pypi`/`changelog`, from each
collector's `source_id`). Only the read query and the table template are
hardwired to GitHub.

Purpose: Honest outbound links + a source-neutral column header (DASH-04/
DASH-05 continuation, D3-5 touch #3). Presentation layer ONLY — no scoring,
ingestion, or schema change.

Output: Updated `_QUERY_RANKED_SQL` (selects `source`), source-branched
`table.html`, and tests covering non-GitHub rendering.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@techtrend/server/queries.py
@techtrend/web/templates/partials/table.html
@tests/test_dashboard.py

# Source-id authority (confirmed): github, hn, npm, pypi, changelog
@techtrend/collectors/registry.py
</context>

<key_decisions>
Two design decisions locked by reading the existing test suite — the executor
MUST honor both or existing tests break:

1. **Second link gates on `row['source'] == 'github'`, NOT on `docs_url`.**
   The existing test `test_row_links_source_before_docs_with_honest_label`
   asserts that an *undocumented* GitHub row (docs_url=None) STILL renders a
   second link labeled `Repo` whose href falls back to `row['url']` (it
   asserts the url appears twice in the row). Gating the second link on
   `docs_url` presence would delete that link and break the test. Gating on
   `source == 'github'` preserves GitHub behavior exactly (both the `Docs`
   and the `Repo`-fallback cases) while suppressing the bogus second link for
   every non-GitHub source.

2. **The primary link href stays `row['url']` for every source** — only the
   visible label text branches on source.
</key_decisions>

<tasks>

<task type="auto">
  <name>Task 1: Select source in query + branch link label and second-link visibility in template</name>
  <files>techtrend/server/queries.py, techtrend/web/templates/partials/table.html</files>
  <action>
In `techtrend/server/queries.py`, add `entities.source,` to the SELECT column
list inside `_QUERY_RANKED_SQL` (place it adjacent to `entities.full_name` /
`entities.url` near the top of the list). Match the existing rich-comment
style: add a brief inline comment noting the column exists so the template can
branch its outbound-link label per source. Do NOT change ordering, joins,
filters, the `{section_filter}`/`{order_by}` format slots, or the
`stars_total` subquery.

In `techtrend/web/templates/partials/table.html`:

(a) Name-column header (the `sort=name` link, currently label text `Repo` near
line 16): change ONLY the visible label text `Repo` → `Item`. Do NOT touch the
`hx-get`, the `sort=name` param, `hx-target`/`hx-swap`/`hx-push-url`/
`hx-indicator`, or the `{% if sort == 'name' %}` sort-glyph logic.

(b) The `action-col` cell (currently lines ~59-62): branch the PRIMARY link's
label text on `row['source']`, keeping `href="{{ row['url'] }}"` unchanged for
every source. Map: `hn` → "View on HN", `npm` → "View on npm", `pypi` →
"View on PyPI", `changelog` → "View changelog", and `github` plus any
unknown/default fallback → "View on GitHub". Use a Jinja if/elif/else chain (or
a dict lookup with a default) — whichever matches the file's existing style;
keep the anchor markup otherwise identical.

(c) The SECOND link (the `docs_url`/`Repo`/`Docs` anchor) is GitHub-repo-
specific. Wrap it in `{% if row['source'] == 'github' %}...{% endif %}` so it
renders for `github` rows exactly as it does today (unchanged: href falls back
`row['docs_url'] or row['url']`, label `Docs` when docs_url_kind in
('homepage','readme') else `Repo`) and does NOT render for any non-GitHub
source. Per key_decisions #1 do NOT gate this on `docs_url` presence.

Match existing Jinja whitespace/indentation and commenting conventions.
  </action>
  <verify>
    <automated>python -c "import techtrend.server.queries as q; assert 'entities.source' in q._QUERY_RANKED_SQL, 'source not selected'; print('source selected OK')"</automated>
  </verify>
  <done>
`_QUERY_RANKED_SQL` selects `entities.source`. The template renders the
source-appropriate primary label, renders the second link only for `github`
rows, and the name header reads `Item`. GitHub rows render byte-identically to
before (aside from the header text).
  </done>
</task>

<task type="auto">
  <name>Task 2: Add tests for non-GitHub link labeling, suppressed second link, and Item header</name>
  <files>tests/test_dashboard.py</files>
  <action>
Add tests to `tests/test_dashboard.py` using the existing `_insert_entity`
(supports `source=`), `_insert_score`, `_client`, `db`, and `pg_env`
fixtures — the ephemeral pytest-postgresql cluster fully supports synthetic
non-GitHub rows (the "local dev DB is github-only" caveat is about the real
dev database, NOT the test cluster; the existing
`test_non_github_row_with_no_stars_snapshot_renders_em_dash_total` already
inserts a `source='changelog'` row this way).

Add a test that inserts an `hn` entity (e.g.
`_insert_entity(conn, "1", source="hn", full_name="story/show-hn", url="https://news.ycombinator.com/item?id=1")`),
scores it eligible, GETs `/`, slices the row from its full_name to the next
`</tr>`, and asserts within that row:
  - `"View on HN"` is present
  - `"View on GitHub"` is NOT present
  - `">Repo<"` is NOT present AND `">Docs<"` is NOT present (no bogus second link)

Add a test asserting the name-column sort header now reads `Item`: use the
existing `_sort_link_html(text, "name")` helper and assert `"Item"` is in it
and `"Repo"` is not in that header link.

Optionally parametrize the label mapping across `npm`→"View on npm",
`pypi`→"View on PyPI", `changelog`→"View changelog" if it stays concise.

Do NOT weaken or delete the existing GitHub tests
(`test_row_links_source_before_docs_with_honest_label`) — they must still pass
unchanged, proving GitHub behavior is preserved.
  </action>
  <verify>
    <automated>python -m pytest tests/test_dashboard.py -x -q</automated>
  </verify>
  <done>
New non-GitHub link tests and the `Item` header test pass; all pre-existing
`test_dashboard.py` tests (including the GitHub docs/repo link test) still
pass.
  </done>
</task>

</tasks>

<verification>
- `python -m pytest tests/test_dashboard.py -q` passes (existing + new tests).
- `_QUERY_RANKED_SQL` selects `entities.source`.
- Manual template read confirms: primary label branches on source, second link
  wrapped in `{% if row['source'] == 'github' %}`, header text is `Item`.
- Real Hacker News rendering is verified later on the deployed Coolify
  dashboard (out of local scope — the real dev DB has 0 non-github rows).
</verification>

<success_criteria>
- Non-GitHub rows show a source-appropriate primary label and no bogus
  second link.
- GitHub rows are unchanged (primary "View on GitHub" + Docs/Repo second link).
- Name-column header reads "Item".
- No scoring/ingestion/schema change; only queries.py, table.html, and
  test_dashboard.py touched.
</success_criteria>

<output>
Create `.planning/quick/260825-twr-fix-dashboard-mislabeling-non-github-ite/260825-twr-SUMMARY.md` when done.
</output>
