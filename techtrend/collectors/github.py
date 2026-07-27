"""GitHub collector (COLL-01, COLL-02, COLL-06, COLL-07, COLL-08, COLL-09).

`GitHubCollector` is the single source implementing the `Collector` protocol
(base.py). The auth token env var is never read here -- `techtrend.collectors.http`
owns that (T-01-12 mitigation; enforced by an acceptance-criteria grep
confining the literal env var name to http.py).

Discovery (D-01/D-03) runs two GitHub Search API passes -- one over the
topics allowlist, one over the keyword list scoped to `in:name,description`
-- then unions the results with the config seed list and force-include list.
GitHub's search `q` syntax does not guarantee OR semantics across qualifiers
the way D-03 requires, so `admit_repo()` is the true, deterministic D-03 gate
applied locally to every candidate regardless of what the search query
happened to return; the search queries themselves are best-effort discovery,
not the authority on admission.

Search (30 req/min authenticated) and core (5,000 req/hr authenticated) are
two separate GitHub rate-limit budgets (COLL-07 precision) -- this collector
never adds their remaining-request counts together.
"""

import logging
from datetime import date

import httpx
import tenacity

from techtrend.collectors.base import CollectedItem
from techtrend.collectors.http import build_client, is_retryable
from techtrend.config import Config, load_config

logger = logging.getLogger(__name__)

GITHUB_API_ROOT = "https://api.github.com"

_RETRY_KWARGS = {
    "stop": tenacity.stop_after_attempt(5),
    "wait": tenacity.wait_exponential(multiplier=2, min=2, max=60),
    "retry": tenacity.retry_if_exception(is_retryable),
}

# GitHub's Search API rejects a query carrying more than 5 boolean
# (AND/OR/NOT) operators with HTTP 422 (V1). N terms joined by " OR "
# produces N-1 operators, so batches are capped at 6 terms -- the largest
# batch size that stays at or under the 5-operator limit.
_MAX_TERMS_PER_SEARCH_PASS = 6


def _chunk(items: list[str], size: int) -> list[list[str]]:
    """Split `items` into consecutive batches of at most `size` elements."""
    return [items[i : i + size] for i in range(0, len(items), size)]


def admit_repo(
    full_name: str,
    *,
    topics: list[str] | None = None,
    description: str | None = None,
    name: str | None = None,
    seed: set[str],
    topics_allowlist: set[str],
    keywords: list[str],
    force_include: set[str],
    force_exclude: set[str],
) -> bool:
    """D-01/D-03/D-04 deterministic relevance gate.

    Force-exclude always wins, even over a seed/topic/keyword match. Seed
    membership and force-include admit unconditionally. Otherwise admit on a
    topics-allowlist hit OR a keyword match against name/description -- the
    keyword fallback exists specifically to catch brand-new repos that have
    not tagged themselves with topics yet.
    """
    if full_name in force_exclude:
        return False
    if full_name in seed or full_name in force_include:
        return True
    topic_set = set(topics or [])
    if topic_set & topics_allowlist:
        return True
    haystack = f"{name or ''} {description or ''}".lower()
    return any(keyword.lower() in haystack for keyword in keywords)


def _search_query_topic(topic: str) -> str:
    """`topic:X` -- exactly one topic per search request (V1).

    Confirmed live against GitHub's Search API: `topic:a OR topic:b`
    unconditionally returns HTTP 422 ("The search contains only logical
    operators (AND / OR / NOT) without any search terms. Logical operators
    only apply to text, not to qualifiers.") regardless of how few operators
    are used -- OR-ing `topic:` qualifiers together is never valid, not just
    over some operator-count limit. Free-text terms (`_search_query_keywords`)
    do not have this restriction. Each topic is therefore issued as its own
    search request and the results are unioned by full_name in `_discover`.
    """
    return f"topic:{topic}"


def _search_query_keywords(keywords: list[str]) -> str:
    """`("k1" OR "k2" OR ...) in:name,description` for one batch of <=
    `_MAX_TERMS_PER_SEARCH_PASS` keywords -- name/description scan.
    Free-text OR is valid on GitHub's Search API (unlike qualifier OR, see
    `_search_query_topic`), but a query carrying more than 5 boolean
    operators still returns HTTP 422 regardless of term type (V1); N terms
    joined by " OR " produces N-1 operators, so `_MAX_TERMS_PER_SEARCH_PASS`
    caps batches at 6. Callers are responsible for chunking the full
    keywords list via `_chunk` before calling this.
    """
    terms = " OR ".join(f'"{keyword}"' for keyword in keywords)
    return f"({terms}) in:name,description"


def _parse_last_page(link_header: str | None) -> int | None:
    """Extract the `rel="last"` page number from a GitHub `Link` header.

    With `per_page=1` on the releases endpoint, the last-page number IS the
    total release count -- one request instead of paginating every release.
    """
    if not link_header:
        return None
    for part in link_header.split(","):
        segment = part.strip()
        if 'rel="last"' not in segment:
            continue
        url_part = segment.split(";")[0].strip().strip("<>")
        page = httpx.URL(url_part).params.get("page")
        if page is not None:
            return int(page)
    return None


@tenacity.retry(**_RETRY_KWARGS)
def _search_page(client: httpx.Client, query: str) -> dict:
    resp = client.get(
        f"{GITHUB_API_ROOT}/search/repositories",
        params={"q": query, "sort": "stars", "order": "desc", "per_page": 100},
    )
    resp.raise_for_status()
    return resp.json()


@tenacity.retry(**_RETRY_KWARGS)
def _get_metadata(client: httpx.Client, full_name: str) -> dict:
    resp = client.get(f"{GITHUB_API_ROOT}/repos/{full_name}")
    resp.raise_for_status()
    return resp.json()


@tenacity.retry(**_RETRY_KWARGS)
def _get_release_count(client: httpx.Client, full_name: str) -> int:
    resp = client.get(
        f"{GITHUB_API_ROOT}/repos/{full_name}/releases",
        params={"per_page": 1},
    )
    resp.raise_for_status()
    last_page = _parse_last_page(resp.headers.get("link"))
    if last_page is not None:
        return last_page
    return len(resp.json())


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
            # No README -- not an error, just nothing for docs_link to scan.
            return None
        raise


class GitHubCollector:
    """The one registered source (COLL-06). `source_id = "github"`."""

    source_id = "github"

    def __init__(self, config: Config | None = None, client: httpx.Client | None = None):
        # Both optional so `registry.py` can construct `GitHubCollector()` at
        # import time with no side effects -- config/client are resolved
        # lazily inside fetch(), never at construction.
        self._config = config
        self._client = client

    def _discover(self, client: httpx.Client, config: Config) -> list[dict]:
        """Best-effort search discovery. Returns raw search-hit dicts, deduped
        by full_name. A search-pass failure is logged and skipped rather than
        aborting the whole collector run -- discovery is additive on top of
        the seed list, never a hard dependency.

        V1: GitHub's Search API rejects OR-ing `topic:` qualifiers at all
        (confirmed live -- see `_search_query_topic`), so every configured
        topic is issued as its own single-topic search request. Keywords
        (free text, where OR is valid) are batched into groups of at most
        `_MAX_TERMS_PER_SEARCH_PASS` -- GitHub separately rejects any query
        carrying more than 5 boolean operators regardless of term type.
        Results from every pass are unioned by full_name.
        """
        candidates: dict[str, dict] = {}
        passes = []
        for topic in config.discovery.topics:
            passes.append((f"topics:{topic}", _search_query_topic(topic)))
        for i, batch in enumerate(_chunk(config.discovery.keywords, _MAX_TERMS_PER_SEARCH_PASS)):
            passes.append((f"keywords[{i}]", _search_query_keywords(batch)))

        for label, query in passes:
            try:
                page = _search_page(client, query)
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "stage=collect:github discovery=%s status=%s note=search pass skipped",
                    label,
                    exc.response.status_code,
                )
                continue
            except httpx.TransportError as exc:
                # `is_retryable` (http.py) only recognizes HTTPStatusError, so a
                # transport-level failure (connection reset, DNS blip, timeout)
                # is never retried by tenacity -- it reaches here directly after
                # the first attempt. Treat it the same as a status-level
                # failure: log and skip this search pass rather than aborting
                # the whole collect:github stage, including the seed repos that
                # don't depend on discovery at all (WR-04).
                logger.warning(
                    "stage=collect:github discovery=%s error=%s note=search pass skipped",
                    label,
                    exc,
                )
                continue
            for item in page.get("items", []):
                candidates[item["full_name"]] = item
        return list(candidates.values())

    def _admitted(self, candidates: list[dict], config: Config) -> dict[str, str]:
        """Returns {full_name: discovery_method} for every admitted repo,
        unioning seed + force-include + search-discovered candidates and
        applying admit_repo() (D-01/D-03/D-04) as the single source of truth.
        """
        seed = set(config.seed.repos)
        force_include = set(config.overrides.force_include)
        force_exclude = set(config.overrides.force_exclude)
        topics_allowlist = set(config.discovery.topics)
        keywords = config.discovery.keywords

        admitted: dict[str, str] = {}

        def _gate(full_name: str, **meta) -> bool:
            return admit_repo(
                full_name,
                seed=seed,
                topics_allowlist=topics_allowlist,
                keywords=keywords,
                force_include=force_include,
                force_exclude=force_exclude,
                **meta,
            )

        for full_name in seed:
            if _gate(full_name):
                admitted.setdefault(full_name, "seed")
        for full_name in force_include:
            if _gate(full_name):
                admitted.setdefault(full_name, "force-include")
        for item in candidates:
            full_name = item["full_name"]
            if _gate(
                full_name,
                topics=item.get("topics", []),
                description=item.get("description"),
                name=item.get("name"),
            ):
                admitted.setdefault(full_name, "search")

        return admitted

    def _collect_repo(self, client: httpx.Client, full_name: str, discovery_method: str) -> dict:
        metadata = _get_metadata(client, full_name)
        release_count = _get_release_count(client, full_name)
        readme_text = _get_readme_text(client, full_name)
        return {
            "metadata": metadata,
            "release_count": release_count,
            "readme_text": readme_text,
            "discovery_method": discovery_method,
        }

    def fetch(self, since: date) -> list[dict]:
        """Discover, filter (D-01/D-03/D-04), then fetch metadata + releases
        + README for every admitted repo. A single admitted repo's fetch
        failure is logged and skipped -- it never aborts the rest of the run
        (the run-level failure isolation lives in the orchestrator).
        """
        config = self._config or load_config()
        client = self._client or build_client()
        owns_client = self._client is None
        try:
            candidates = self._discover(client, config)
            admitted = self._admitted(candidates, config)
            results = []
            for full_name, discovery_method in admitted.items():
                try:
                    results.append(self._collect_repo(client, full_name, discovery_method))
                except httpx.HTTPStatusError as exc:
                    logger.warning(
                        "stage=collect:github repo=%s status=%s note=repo skipped",
                        full_name,
                        exc.response.status_code,
                    )
            return results
        finally:
            if owns_client:
                client.close()

    def normalize(self, raw: dict) -> CollectedItem:
        """Map one `_collect_repo` result onto the source-agnostic CollectedItem.

        `source_native_id` is the numeric GitHub repo id, not `full_name` --
        the id survives a rename and is what COLL-09's adjacency case relies
        on. `metrics` carries `stars`/`releases` as a flat dict so the
        source-agnostic snapshot writer never learns what a "star" is.
        """
        metadata = raw["metadata"]
        metrics = {"stars": metadata.get("stargazers_count", 0)}
        if raw.get("release_count") is not None:
            metrics["releases"] = raw["release_count"]
        return CollectedItem(
            source=self.source_id,
            source_native_id=str(metadata["id"]),
            full_name=metadata["full_name"],
            url=metadata["html_url"],
            homepage=metadata.get("homepage"),
            description=metadata.get("description"),
            metrics=metrics,
            topics=metadata.get("topics", []),
            discovery_method=raw.get("discovery_method", "search"),
            readme_text=raw.get("readme_text"),
        )
