"""Lobste.rs developer & open-source community collector.

Queries the public, unauthenticated Lobste.rs JSON feeds:
- `https://lobste.rs/hottest.json`
- `https://lobste.rs/t/ai.json`
- `https://lobste.rs/t/ml.json`
- `https://lobste.rs/t/release.json`
- `https://lobste.rs/t/show.json`

Normalizes each story into a `CollectedItem` with `source="lobsters"` and
`metrics={"points": score}`.
"""

import logging
from datetime import date

import httpx
import tenacity

from techtrend.collectors.base import CollectedItem
from techtrend.collectors.http import build_public_client, is_retryable_public
from techtrend.config import Config

logger = logging.getLogger(__name__)

LOBSTERS_FEEDS = (
    "https://lobste.rs/hottest.json",
    "https://lobste.rs/t/ai.json",
    "https://lobste.rs/t/ml.json",
    "https://lobste.rs/t/release.json",
    "https://lobste.rs/t/show.json",
)

_RETRY_KWARGS = {
    "stop": tenacity.stop_after_attempt(4),
    "wait": tenacity.wait_exponential(multiplier=2, min=2, max=30),
    "retry": tenacity.retry_if_exception(is_retryable_public),
}


@tenacity.retry(**_RETRY_KWARGS)
def _fetch_feed(client: httpx.Client, url: str) -> list[dict]:
    resp = client.get(url)
    resp.raise_for_status()
    return resp.json()


class LobstersCollector:
    """Queries the public Lobste.rs JSON feeds. `source_id = "lobsters"`."""

    source_id = "lobsters"

    def __init__(self, config: Config | None = None, client: httpx.Client | None = None):
        self._config = config
        self._client = client

    def fetch(self, since: date) -> list[dict]:
        client = self._client or build_public_client()
        owns_client = self._client is None
        stories: dict[str, dict] = {}
        try:
            for url in LOBSTERS_FEEDS:
                try:
                    items = _fetch_feed(client, url)
                except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                    logger.warning(
                        "stage=collect:lobsters feed=%s error=%s note=feed skipped",
                        url,
                        exc,
                    )
                    continue
                for item in items:
                    short_id = item.get("short_id")
                    if short_id:
                        stories[short_id] = item
            return list(stories.values())
        finally:
            if owns_client:
                client.close()

    def normalize(self, raw: dict) -> CollectedItem:
        short_id = str(raw["short_id"])
        short_id_url = raw.get("short_id_url") or f"https://lobste.rs/s/{short_id}"
        url = raw.get("url") or short_id_url
        score = int(raw.get("score") or 0) + int(raw.get("comment_count") or 0)
        return CollectedItem(
            source=self.source_id,
            source_native_id=short_id,
            full_name=raw["title"],
            url=url,
            homepage=short_id_url,
            description=", ".join(raw.get("tags") or []),
            metrics={"points": score},
            discovery_method="lobsters-feed",
        )
