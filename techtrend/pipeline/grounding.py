"""Grounding text fetch, extraction, and normalization (ENR-05, D-07, D-08,
D-09; Common Pitfall 1 -- badge-churn cache defeat).

`fetch_grounding` re-fetches a repo's description + README intro through the
existing GitHub HTTP layer (`collectors/http.py::build_client()`) -- this is
NOT a collector (writes no snapshot/CollectedItem); it is a "freshly fetched"
grounding source for the anti-fabrication guarantee (SC3): if there is
nothing real to summarize, it returns `None` and the caller skips the LLM
entirely rather than fabricating from the model's parametric knowledge
(D-08). The GitHub auth token env var is never read here -- that stays
isolated to `collectors/http.py` (T-01-12 mitigation).

`normalize_for_hash` strips markdown badge images and HTML comments and
collapses whitespace BEFORE hashing, so churning CI badges never register as
a content change (D-09, Pitfall #1) -- the cache would otherwise almost
never hit for actively-CI'd, high-traffic repos, quietly multiplying LLM
spend for exactly the repos this dashboard cares most about.
"""

import logging
import re

import httpx
import tenacity

from techtrend.collectors.http import is_retryable

logger = logging.getLogger(__name__)

GITHUB_API_ROOT = "https://api.github.com"

_RETRY_KWARGS = {
    "stop": tenacity.stop_after_attempt(5),
    "wait": tenacity.wait_exponential(multiplier=2, min=2, max=60),
    "retry": tenacity.retry_if_exception(is_retryable),
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


def fetch_grounding(client: httpx.Client, full_name: str, char_cap: int) -> tuple[str, str] | None:
    """Freshly fetch `full_name`'s description + README intro (D-07).

    Reuses the existing GitHub auth/cache/retry layer (`build_client()`) --
    this is GitHub REST traffic, the same as collection, but this module is
    NOT a collector (no snapshot/CollectedItem is written here). `char_cap`
    is required, not defaulted here -- the default (2000) lives once in
    `Tunables.grounding_char_cap` (D-15), the caller passes it through so
    this module never duplicates that config default as a code constant.

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
