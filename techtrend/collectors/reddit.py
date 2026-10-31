"""Reddit AI & Open-Source collector (r/LocalLLaMA, r/MachineLearning, r/opensource, r/ClaudeAI).

Queries the public, unauthenticated ArcticShift Reddit API
(`https://arctic-shift.photon-reddit.com/api/posts/search`), which is
accessible from datacenter IPs without Reddit's HTTP 403/429 blocks and
provides trailing-week posts with full upvote scores and comment counts.
"""

import logging
from datetime import date

import httpx
import tenacity

from techtrend.collectors.base import CollectedItem
from techtrend.collectors.http import build_public_client, is_retryable_public
from techtrend.config import Config

logger = logging.getLogger(__name__)

ARCTIC_SHIFT_URL = "https://arctic-shift.photon-reddit.com/api/posts/search"
TRACKED_SUBREDDITS = (
    "LocalLLaMA",
    "MachineLearning",
    "opensource",
    "ClaudeAI",
)

_RETRY_KWARGS = {
    "stop": tenacity.stop_after_attempt(4),
    "wait": tenacity.wait_exponential(multiplier=2, min=2, max=30),
    "retry": tenacity.retry_if_exception(is_retryable_public),
}


@tenacity.retry(**_RETRY_KWARGS)
def _fetch_subreddit(client: httpx.Client, subreddit: str) -> list[dict]:
    resp = client.get(
        ARCTIC_SHIFT_URL,
        params={
            "subreddit": subreddit,
            "after": "7d",
            "before": "12h",
            "limit": 100,
        },
    )
    resp.raise_for_status()
    return resp.json().get("data", [])


class RedditCollector:
    """Queries top weekly posts from AI & open-source subreddits. `source_id = "reddit"`."""

    source_id = "reddit"

    def __init__(self, config: Config | None = None, client: httpx.Client | None = None):
        self._config = config
        self._client = client

    def fetch(self, since: date) -> list[dict]:
        client = self._client or build_public_client()
        owns_client = self._client is None
        posts_by_id: dict[str, dict] = {}
        try:
            for sub in TRACKED_SUBREDDITS:
                try:
                    posts = _fetch_subreddit(client, sub)
                except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                    logger.warning(
                        "stage=collect:reddit subreddit=%s error=%s note=subreddit skipped",
                        sub,
                        exc,
                    )
                    continue
                ranked = sorted(
                    posts,
                    key=lambda p: (int(p.get("score") or 0) + int(p.get("num_comments") or 0)),
                    reverse=True,
                )
                for post in ranked[:20]:
                    post_id = post.get("id")
                    if post_id and post.get("title"):
                        posts_by_id[str(post_id)] = post
            return list(posts_by_id.values())
        finally:
            if owns_client:
                client.close()

    def normalize(self, raw: dict) -> CollectedItem:
        post_id = str(raw["id"])
        sub = raw.get("subreddit") or "reddit"
        permalink = raw.get("permalink")
        url = f"https://www.reddit.com{permalink}" if permalink else (raw.get("url") or f"https://www.reddit.com/comments/{post_id}")
        points = int(raw.get("score") or 0) + int(raw.get("num_comments") or 0)
        return CollectedItem(
            source=self.source_id,
            source_native_id=post_id,
            full_name=f"[r/{sub}] {raw['title']}",
            url=url,
            metrics={"points": points},
            discovery_method="reddit-top",
        )
