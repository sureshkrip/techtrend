"""Hacker News collector (COLL-03).

`HNCollector` is one of three independent Wave 2 source modules -- this
module and its tests are the whole deliverable; registry wiring is Wave 3's
job so the parallel collectors stay conflict-free (see 03-CONTEXT.md D3-1).

Queries the Algolia HN Search API (unauthenticated, public -- see
`techtrend.collectors.http.build_public_client`) by the curated AI/LLM
keyword list (D3-4, `config.hn.keywords`), unions hits by `objectID` across
keywords, and normalizes each story into a `CollectedItem` carrying
`metrics={"points": N}` -- the primary momentum signal for HN per
CONTEXT.md's discretion note and `normalize.PRIMARY_METRIC['hn']`.

No historical backfill exists for HN (Algolia only indexes what was posted),
so results will be sparse for the first ~week -- expected, matching GitHub's
D-08a honesty (RESEARCH.md HN section).
"""

import logging
from datetime import UTC, date, datetime, timedelta

import httpx
import tenacity

from techtrend.collectors.base import CollectedItem
from techtrend.collectors.http import build_public_client, is_retryable_public
from techtrend.config import Config, load_config

logger = logging.getLogger(__name__)

# Verified live (RESEARCH.md, 2026-08-19): `search_by_date` + a numericFilters
# cutoff on `created_at_i` is the recency-scoped query shape, distinct from
# the relevance-ranked `search` endpoint which has no clean recency filter.
HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"

_RETRY_KWARGS = {
    "stop": tenacity.stop_after_attempt(5),
    "wait": tenacity.wait_exponential(multiplier=2, min=2, max=60),
    "retry": tenacity.retry_if_exception(is_retryable_public),
}


@tenacity.retry(**_RETRY_KWARGS)
def _search_page(client: httpx.Client, query: str, cutoff_epoch: int) -> dict:
    resp = client.get(
        HN_SEARCH_URL,
        params={
            "query": query,
            "tags": "story",
            "numericFilters": f"created_at_i>{cutoff_epoch}",
            "hitsPerPage": 50,
        },
    )
    resp.raise_for_status()
    return resp.json()


class HNCollector:
    """Queries the Algolia HN Search API. `source_id = "hn"`."""

    source_id = "hn"

    def __init__(self, config: Config | None = None, client: httpx.Client | None = None):
        # Both optional so `registry.py` can construct `HNCollector()` at
        # import time with no side effects -- config/client are resolved
        # lazily inside fetch(), matching GitHubCollector's shape.
        self._config = config
        self._client = client

    def fetch(self, since: date) -> list[dict]:
        """Search the curated keyword list, dedupe by objectID, return raw hits.

        Mirrors GitHubCollector's own behavior of always fetching current
        state rather than an incremental delta -- `since` is accepted for
        protocol conformance but not used to scope the query beyond the
        configured lookback window.

        A per-keyword search failure (HTTPStatusError or TransportError) is
        logged and skipped rather than aborting the whole collector run --
        mirrors GitHubCollector._discover's per-pass isolation, so one bad
        keyword never loses every other keyword's hits.
        """
        config = self._config or load_config()
        client = self._client or build_public_client()
        owns_client = self._client is None
        try:
            cutoff_epoch = int(
                (datetime.now(UTC) - timedelta(days=config.hn.lookback_days)).timestamp()
            )
            hits: dict[str, dict] = {}
            for keyword in config.hn.keywords:
                try:
                    page = _search_page(client, keyword, cutoff_epoch)
                except httpx.HTTPStatusError as exc:
                    logger.warning(
                        "stage=collect:hn keyword=%s status=%s note=search pass skipped",
                        keyword,
                        exc.response.status_code,
                    )
                    continue
                except httpx.TransportError as exc:
                    logger.warning(
                        "stage=collect:hn keyword=%s error=%s note=search pass skipped",
                        keyword,
                        exc,
                    )
                    continue
                for hit in page.get("hits", []):
                    hits[hit["objectID"]] = hit
            return list(hits.values())
        finally:
            if owns_client:
                client.close()

    def normalize(self, raw: dict) -> CollectedItem:
        """Map one Algolia hit onto the source-agnostic CollectedItem.

        A self-post (Ask HN/Show HN with no external `url`) falls back to
        the HN item permalink -- there is no homepage to link to otherwise.
        `metrics={"points": N}` is HN's primary momentum signal
        (`normalize.PRIMARY_METRIC['hn']`).
        """
        object_id = str(raw["objectID"])
        url = raw.get("url") or f"https://news.ycombinator.com/item?id={object_id}"
        return CollectedItem(
            source=self.source_id,
            source_native_id=object_id,
            full_name=raw["title"],
            url=url,
            metrics={"points": raw.get("points", 0) or 0},
            discovery_method="hn-search",
        )
