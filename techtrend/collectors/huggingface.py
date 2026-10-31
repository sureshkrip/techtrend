"""Hugging Face trending models, spaces, and daily papers collector.

Queries the public, unauthenticated Hugging Face API:
- `https://huggingface.co/api/trending?type=model&limit=20`
- `https://huggingface.co/api/trending?type=space&limit=15`
- `https://huggingface.co/api/daily_papers?limit=20`

Each item is normalized into a `CollectedItem` with `source="huggingface"` and
`metrics={"likes": N}` (likes for models/spaces, upvotes for daily papers).
"""

import logging
from datetime import date

import httpx
import tenacity

from techtrend.collectors.base import CollectedItem
from techtrend.collectors.http import build_public_client, is_retryable_public
from techtrend.config import Config

logger = logging.getLogger(__name__)

HF_TRENDING_URL = "https://huggingface.co/api/trending"
HF_PAPERS_URL = "https://huggingface.co/api/daily_papers"

_RETRY_KWARGS = {
    "stop": tenacity.stop_after_attempt(4),
    "wait": tenacity.wait_exponential(multiplier=2, min=2, max=30),
    "retry": tenacity.retry_if_exception(is_retryable_public),
}


@tenacity.retry(**_RETRY_KWARGS)
def _fetch_trending(client: httpx.Client, repo_type: str, limit: int) -> list[dict]:
    resp = client.get(HF_TRENDING_URL, params={"type": repo_type, "limit": limit})
    resp.raise_for_status()
    data = resp.json()
    return data.get("recentlyTrending", [])


@tenacity.retry(**_RETRY_KWARGS)
def _fetch_daily_papers(client: httpx.Client, limit: int) -> list[dict]:
    resp = client.get(HF_PAPERS_URL, params={"limit": limit})
    resp.raise_for_status()
    return resp.json()


class HuggingFaceCollector:
    """Queries the public Hugging Face trending & daily papers APIs. `source_id = "huggingface"`."""

    source_id = "huggingface"

    def __init__(self, config: Config | None = None, client: httpx.Client | None = None):
        self._config = config
        self._client = client

    def fetch(self, since: date) -> list[dict]:
        client = self._client or build_public_client()
        owns_client = self._client is None
        results: list[dict] = []
        try:
            for repo_type, limit in (("model", 20), ("space", 15)):
                try:
                    items = _fetch_trending(client, repo_type, limit)
                    for entry in items:
                        repo_data = entry.get("repoData") or {}
                        repo_id = repo_data.get("id")
                        if not repo_id:
                            continue
                        results.append(
                            {
                                "kind": repo_type,
                                "id": repo_id,
                                "title": repo_id,
                                "likes": int(repo_data.get("likes") or 0),
                                "pipeline_tag": repo_data.get("pipeline_tag") or "",
                            }
                        )
                except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                    logger.warning(
                        "stage=collect:huggingface kind=%s error=%s note=pass skipped",
                        repo_type,
                        exc,
                    )

            try:
                papers = _fetch_daily_papers(client, 20)
                for entry in papers:
                    paper = entry.get("paper") or {}
                    paper_id = paper.get("id")
                    title = paper.get("title") or entry.get("title")
                    if not paper_id or not title:
                        continue
                    results.append(
                        {
                            "kind": "paper",
                            "id": str(paper_id),
                            "title": title.strip(),
                            "likes": int(paper.get("upvotes") or 0),
                            "pipeline_tag": "paper",
                        }
                    )
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                logger.warning(
                    "stage=collect:huggingface kind=paper error=%s note=pass skipped",
                    exc,
                )
            return results
        finally:
            if owns_client:
                client.close()

    def normalize(self, raw: dict) -> CollectedItem:
        kind = raw["kind"]
        item_id = raw["id"]
        if kind == "space":
            url = f"https://huggingface.co/spaces/{item_id}"
            full_name = f"[Space] {raw['title']}"
        elif kind == "paper":
            url = f"https://huggingface.co/papers/{item_id}"
            full_name = f"[Paper] {raw['title']}"
        else:
            url = f"https://huggingface.co/{item_id}"
            full_name = raw["title"]

        return CollectedItem(
            source=self.source_id,
            source_native_id=f"{kind}:{item_id}",
            full_name=full_name,
            url=url,
            description=raw.get("pipeline_tag"),
            metrics={"likes": int(raw.get("likes") or 0)},
            discovery_method="hf-trending",
        )
