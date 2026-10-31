"""Grounding text fetch, extraction, and normalization (ENR-05, D-07, D-08,
D-09; Common Pitfall 1 -- badge-churn cache defeat).

`fetch_grounding` dispatches on `entities.source` to a source-appropriate
grounding strategy (quick task 260906-n5d). It is NOT a collector (writes no
snapshot/CollectedItem); it is a "freshly fetched" grounding source for the
anti-fabrication guarantee (SC3): if there is nothing real to summarize, it
returns `None` and the caller skips the LLM entirely rather than fabricating
from the model's parametric knowledge (D-08).

Root cause this dispatcher fixes: the original `fetch_grounding` unconditionally
hit `GET api.github.com/repos/{full_name}` for every entity regardless of
source. For non-GitHub entities `full_name` is a headline / package name /
feed label, not an `owner/repo` path -- the GitHub call 404d, the exception
propagated into `run_enrichment`'s per-candidate try/except, and the
candidate was silently skipped: no enrichments row, no summary, no section.
Every source below grounds on real, already-stored or freshly-fetched
first-party text -- never fabricated:

- github: GitHub metadata `description` + README intro via the authenticated
  GitHub client (`_fetch_github_grounding`, preserved byte-for-byte from the
  pre-dispatch implementation).
- hn: the entity's `full_name`, which for HN IS the real story title
  (`hn.py::normalize` sets `full_name=raw["title"]`) -- no network fetch
  needed, the title alone is genuine, already-stored, non-fabricated text.
- npm: the first-party packument (`registry.npmjs.org`) description + readme,
  fetched via the unauthenticated public client.
- pypi: pypi.org's JSON API `info.summary` + `info.description`, fetched via
  the unauthenticated public client (distinct from the pypistats endpoint the
  collector uses -- pypistats carries no description).
- changelog: a fresh feedparser re-parse of the feed, grounding on the feed's
  own title + its most-recent entry titles (real in-feed content, not the
  bare curated label).

The GitHub auth token env var is never read here -- that stays isolated to
`collectors/http.py` (T-01-12 mitigation).

`normalize_for_hash` strips markdown badge images and HTML comments and
collapses whitespace BEFORE hashing, so churning CI badges never register as
a content change (D-09, Pitfall #1) -- the cache would otherwise almost
never hit for actively-CI'd, high-traffic repos, quietly multiplying LLM
spend for exactly the repos this dashboard cares most about.
"""

import logging
import re
from urllib.parse import quote

import feedparser
import httpx
import tenacity

from techtrend.collectors.http import is_retryable, is_retryable_public

logger = logging.getLogger(__name__)

GITHUB_API_ROOT = "https://api.github.com"
NPM_REGISTRY_ROOT = "https://registry.npmjs.org"
PYPI_JSON_ROOT = "https://pypi.org/pypi"

_RETRY_KWARGS = {
    "stop": tenacity.stop_after_attempt(5),
    "wait": tenacity.wait_exponential(multiplier=2, min=2, max=60),
    "retry": tenacity.retry_if_exception(is_retryable),
}

# Public-API retry kwargs (npm/pypi) -- mirrors _RETRY_KWARGS but keyed on
# is_retryable_public, which retries only 429/5xx (none of these public APIs
# use GitHub's x-ratelimit-remaining:0 403 convention).
_RETRY_KWARGS_PUBLIC = {
    "stop": tenacity.stop_after_attempt(5),
    "wait": tenacity.wait_exponential(multiplier=2, min=2, max=60),
    "retry": tenacity.retry_if_exception(is_retryable_public),
}

_BADGE_MD_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_DEEP_HEADING_RE = re.compile(r"^#{2,}\s", re.MULTILINE)  # H2 and deeper


def extract_intro(readme_text: str, char_cap: int) -> str:
    """Top section of the README: everything before the first H2+ heading,
    capped to char_cap characters. An H1 title (if present) is kept (D-07)."""
    match = _DEEP_HEADING_RE.search(readme_text)
    intro = readme_text[: match.start()] if match else readme_text
    return intro[:char_cap].strip()


def normalize_for_hash(description: str | None, readme_intro: str) -> str:
    """Strip badge markup and HTML comments (Common Pitfall #1), collapse
    whitespace, before hashing -- badge/whitespace churn must never register
    as a content change (D-09)."""
    combined = f"{description or ''}\n{readme_intro}"
    combined = _BADGE_MD_RE.sub("", combined)
    combined = _HTML_COMMENT_RE.sub("", combined)
    return re.sub(r"\s+", " ", combined).strip()


# ---------------------------------------------------------------------------
# github (UNCHANGED): metadata description + README intro via the
# authenticated GitHub client. Extracted verbatim from the pre-dispatch
# fetch_grounding (D-07/D-08).
# ---------------------------------------------------------------------------


@tenacity.retry(**_RETRY_KWARGS)
def _get_metadata(client: httpx.Client, full_name: str) -> dict:
    resp = client.get(f"{GITHUB_API_ROOT}/repos/{full_name}")
    resp.raise_for_status()
    return resp.json()


@tenacity.retry(**_RETRY_KWARGS)
def _get_readme_text(client: httpx.Client, full_name: str) -> str | None:
    try:
        resp = client.get(
            f"{GITHUB_API_ROOT}/repos/{full_name}/readme",
            headers={"Accept": "application/vnd.github.raw+json"},
        )
        resp.raise_for_status()
        return resp.text
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            # No README -- not a retryable error, just nothing to ground on.
            return None
        raise


def _fetch_github_grounding(client: httpx.Client, full_name: str, char_cap: int) -> tuple[str, str] | None:
    """Freshly fetch `full_name`'s description + README intro (D-07).

    Reuses the existing GitHub auth/cache/retry layer (`build_client()`) --
    this is GitHub REST traffic, the same as collection, but this module is
    NOT a collector (no snapshot/CollectedItem is written here).

    Returns `(description, extracted_intro)` on success. Returns `None` when
    BOTH the description is empty/missing AND the README fetch failed or was
    effectively empty after stripping -- the caller writes a `fetch_failed`
    tombstone and skips the LLM call entirely (D-08): never fabricate a
    summary from nothing.
    """
    metadata = _get_metadata(client, full_name)
    readme_text = _get_readme_text(client, full_name)

    description = (metadata.get("description") or "").strip()
    stripped_readme = (readme_text or "").strip()

    if not description and not stripped_readme:
        return None

    return description, extract_intro(stripped_readme, char_cap)


# ---------------------------------------------------------------------------
# hn: full_name IS the real story title (hn.py::normalize). No network
# fetch -- the title is genuine, already-stored, non-fabricated text (D-08).
# ---------------------------------------------------------------------------


def _fetch_hn_grounding(full_name: str, char_cap: int) -> tuple[str, str] | None:
    """Ground on the HN story title. Returns `(title, "")`, or `None` when
    the title is empty/whitespace (should never happen -- HN requires a
    title, but this keeps the "nothing real -> tombstone" contract honest)."""
    title = (full_name or "").strip()
    if not title:
        return None
    return title[:char_cap], ""


# ---------------------------------------------------------------------------
# npm: first-party packument (registry.npmjs.org) via the unauthenticated
# public client -- description + readme intro, mirroring the GitHub shape
# with real first-party text (D-08).
# ---------------------------------------------------------------------------


@tenacity.retry(**_RETRY_KWARGS_PUBLIC)
def _get_npm_packument(client: httpx.Client, package: str) -> dict | None:
    url = f"{NPM_REGISTRY_ROOT}/{quote(package, safe='@')}"
    try:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            # Unpublished/not-found -- nothing to ground on, not a retryable
            # error (mirrors _get_readme_text's 404 -> None handling).
            return None
        raise


def _fetch_npm_grounding(client: httpx.Client, package: str, char_cap: int) -> tuple[str, str] | None:
    """Freshly fetch `package`'s npm registry description + readme intro.

    Returns `None` when the packument 404s (unpublished/not-found) or when
    BOTH `description` and `readme` are empty/missing after stripping (D-08).
    """
    packument = _get_npm_packument(client, package)
    if packument is None:
        return None

    description = (packument.get("description") or "").strip()
    readme = (packument.get("readme") or "").strip()

    if not description and not readme:
        return None

    return description, extract_intro(readme, char_cap)


# ---------------------------------------------------------------------------
# pypi: pypi.org's JSON API (distinct from the pypistats endpoint the
# collector uses -- pypistats carries no description) via the unauthenticated
# public client -- info.summary + info.description intro (D-08).
# ---------------------------------------------------------------------------


@tenacity.retry(**_RETRY_KWARGS_PUBLIC)
def _get_pypi_metadata(client: httpx.Client, package: str) -> dict | None:
    url = f"{PYPI_JSON_ROOT}/{quote(package, safe='')}/json"
    try:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return None
        raise


def _fetch_pypi_grounding(client: httpx.Client, package: str, char_cap: int) -> tuple[str, str] | None:
    """Freshly fetch `package`'s pypi.org JSON metadata -- `info.summary` as
    description, `info.description` (long text) as the body.

    Returns `None` when the package 404s or when BOTH `summary` and
    `description` are empty/missing after stripping (D-08).
    """
    metadata = _get_pypi_metadata(client, package)
    if metadata is None:
        return None

    info = metadata.get("info") or {}
    summary = (info.get("summary") or "").strip()
    description = (info.get("description") or "").strip()

    if not summary and not description:
        return None

    return summary, extract_intro(description, char_cap)


# ---------------------------------------------------------------------------
# changelog: fresh feedparser re-parse (grounding is a fresh fetch, not a
# collector) -- feed title + most-recent entry titles (real in-feed
# content), not the bare curated label (D-08).
# ---------------------------------------------------------------------------


def _fetch_changelog_grounding(full_name: str, url: str, char_cap: int) -> tuple[str, str] | None:
    """Re-parse the feed and ground on its own title + recent entry titles.

    Returns `None` when the feed is bozo/unreachable or has zero entries --
    nothing real to ground on (D-08).
    """
    parsed = feedparser.parse(url)
    if getattr(parsed, "bozo", False) or not parsed.entries:
        return None

    description = parsed.feed.get("title") or full_name
    entry_titles = [entry.get("title", "") for entry in parsed.entries if entry.get("title")]
    body = "\n".join(entry_titles)[:char_cap]

    return description, body


# ---------------------------------------------------------------------------
# public dispatcher
# ---------------------------------------------------------------------------


def fetch_grounding(
    source: str,
    full_name: str,
    url: str,
    char_cap: int,
    *,
    github_client: httpx.Client | None,
    public_client: httpx.Client | None,
) -> tuple[str, str] | None:
    """Dispatch to a source-appropriate grounding strategy (D-08).

    `char_cap` is required, not defaulted here -- the default (2000) lives
    once in `Tunables.grounding_char_cap` (D-15), the caller passes it
    through so this module never duplicates that config default as a code
    constant. `github_client`/`public_client` are required keyword params
    (no internal build_client()/build_public_client() fallback) -- the
    production caller constructs both once per run and passes them in; tests
    inject httpx.MockTransport-backed clients or None for the branch under
    test.

    Returns `(description, body_text)` on success. Returns `None` when the
    source's strategy found nothing real to ground on, or when `source` is
    not recognized -- the caller writes a `fetch_failed` tombstone and skips
    the LLM entirely rather than fabricate (D-08); an unknown source never
    raises.
    """
    if source == "github":
        return _fetch_github_grounding(github_client, full_name, char_cap)
    if source in ("hn", "huggingface", "lobsters", "reddit"):
        return _fetch_hn_grounding(full_name, char_cap)
    if source == "npm":
        return _fetch_npm_grounding(public_client, full_name, char_cap)
    if source == "pypi":
        return _fetch_pypi_grounding(public_client, full_name, char_cap)
    if source == "changelog":
        return _fetch_changelog_grounding(full_name, url, char_cap)

    logger.warning(
        "source=%s full_name=%s note=unknown source, no grounding strategy -- returning None",
        source,
        full_name,
    )
    return None
