"""npm + PyPI download-velocity collectors (COLL-04).

`NpmCollector` and `PyPiCollector` are two of the three independent Wave 2
source modules -- this module and its tests are the whole deliverable;
registry wiring is Wave 3's job so the parallel collectors stay
conflict-free (see 03-CONTEXT.md D3-1). npm and PyPI share one module
(planner's call, D3-1) since both normalize the same raw metric shape
(a downloads count) into `metrics={"downloads": N}`.

Queries the unauthenticated public npm registry (`api.npmjs.org`) and
pypistats (`pypistats.org`) APIs (see `techtrend.collectors.http.build_public_client`)
for the curated package lists (D3-4, `config.packages.npm` / `config.packages.pypi`).

CRITICAL (RESEARCH.md Pitfall 1): both collectors snapshot the rolling
LAST-WEEK download total, never a raw daily count. npm/PyPI daily download
counts are NOT cumulative -- a raw "last-day downloads" figure resets every
day and is a rate, not a running total. Storing a raw daily rate as the
`metric_value` would make `compute_window_gain`'s last-minus-first delta
meaningless (essentially random day to day). The rolling last-week total
(npm: `downloads/point/last-week/{pkg}`; PyPI: `pypistats` `recent.last_week`)
is a legitimate, directionally sound week-over-week momentum signal instead.
"""

import logging
from datetime import date
from urllib.parse import quote

import httpx
import tenacity

from techtrend.collectors.base import CollectedItem
from techtrend.collectors.http import build_public_client, is_retryable_public
from techtrend.config import Config, load_config

logger = logging.getLogger(__name__)

NPM_API_ROOT = "https://api.npmjs.org"
PYPISTATS_API_ROOT = "https://pypistats.org/api"

_RETRY_KWARGS = {
    "stop": tenacity.stop_after_attempt(5),
    "wait": tenacity.wait_exponential(multiplier=2, min=2, max=60),
    "retry": tenacity.retry_if_exception(is_retryable_public),
}


def _npm_download_url(package: str) -> str:
    """`https://api.npmjs.org/downloads/point/last-week/{package}`.

    A scoped npm package (`@org/pkg`) must URL-encode its slash as `%2F`
    for a single-package request (RESEARCH.md npm section) -- bulk
    (comma-separated) queries don't support scoped packages at all, so this
    collector always issues one request per package regardless.
    """
    return f"{NPM_API_ROOT}/downloads/point/last-week/{quote(package, safe='@')}"


def _pypi_recent_url(package: str) -> str:
    return f"{PYPISTATS_API_ROOT}/packages/{quote(package, safe='')}/recent"


@tenacity.retry(**_RETRY_KWARGS)
def _get_npm_downloads(client: httpx.Client, package: str) -> dict:
    resp = client.get(_npm_download_url(package))
    resp.raise_for_status()
    return resp.json()


@tenacity.retry(**_RETRY_KWARGS)
def _get_pypi_recent(client: httpx.Client, package: str) -> dict:
    resp = client.get(_pypi_recent_url(package))
    resp.raise_for_status()
    return resp.json()


class NpmCollector:
    """Queries the public npm downloads API. `source_id = "npm"`."""

    source_id = "npm"

    def __init__(self, config: Config | None = None, client: httpx.Client | None = None):
        # Both optional so `registry.py` can construct `NpmCollector()` at
        # import time with no side effects -- config/client are resolved
        # lazily inside fetch(), matching GitHubCollector/HNCollector's shape.
        self._config = config
        self._client = client

    def fetch(self, since: date) -> list[dict]:
        """One request per configured npm package. A per-package fetch
        failure (HTTPStatusError or TransportError) is logged and skipped
        rather than aborting the whole collector run -- mirrors
        GitHubCollector._discover / HNCollector.fetch's per-item isolation.
        """
        config = self._config or load_config()
        client = self._client or build_public_client()
        owns_client = self._client is None
        try:
            results = []
            for package in config.packages.npm:
                try:
                    raw = _get_npm_downloads(client, package)
                except httpx.HTTPStatusError as exc:
                    logger.warning(
                        "stage=collect:npm package=%s status=%s note=package skipped",
                        package,
                        exc.response.status_code,
                    )
                    continue
                except httpx.TransportError as exc:
                    logger.warning(
                        "stage=collect:npm package=%s error=%s note=package skipped",
                        package,
                        exc,
                    )
                    continue
                # The npm response already carries "package", but a caller
                # can't rely on that for every upstream response shape --
                # tag it explicitly from the configured name we requested.
                raw = dict(raw)
                raw["package"] = package
                results.append(raw)
            return results
        finally:
            if owns_client:
                client.close()

    def normalize(self, raw: dict) -> CollectedItem:
        """Map one npm downloads-point response onto the source-agnostic
        CollectedItem.

        `raw["downloads"]` IS the rolling last-week total (the endpoint
        queried is `downloads/point/last-week/...`) -- deliberately stored
        as-is, not divided into a daily rate, so `compute_window_gain`'s
        last-minus-first delta over these snapshots stays meaningful
        (RESEARCH.md Pitfall 1).
        """
        package = raw["package"]
        return CollectedItem(
            source=self.source_id,
            source_native_id=package,
            full_name=package,
            url=f"https://www.npmjs.com/package/{package}",
            metrics={"downloads": raw.get("downloads", 0) or 0},
            discovery_method="tracked-package",
        )


class PyPiCollector:
    """Queries the public pypistats recent-downloads API. `source_id = "pypi"`."""

    source_id = "pypi"

    def __init__(self, config: Config | None = None, client: httpx.Client | None = None):
        self._config = config
        self._client = client

    def fetch(self, since: date) -> list[dict]:
        """One request per configured PyPI package. A per-package fetch
        failure is logged and skipped rather than aborting the whole
        collector run, mirroring NpmCollector.fetch.
        """
        config = self._config or load_config()
        client = self._client or build_public_client()
        owns_client = self._client is None
        try:
            results = []
            for package in config.packages.pypi:
                try:
                    raw = _get_pypi_recent(client, package)
                except httpx.HTTPStatusError as exc:
                    logger.warning(
                        "stage=collect:pypi package=%s status=%s note=package skipped",
                        package,
                        exc.response.status_code,
                    )
                    continue
                except httpx.TransportError as exc:
                    logger.warning(
                        "stage=collect:pypi package=%s error=%s note=package skipped",
                        package,
                        exc,
                    )
                    continue
                raw = dict(raw)
                raw["package"] = package
                results.append(raw)
            return results
        finally:
            if owns_client:
                client.close()

    def normalize(self, raw: dict) -> CollectedItem:
        """Map one pypistats `recent` response onto the source-agnostic
        CollectedItem.

        `raw["data"]["last_week"]` is the rolling last-week total --
        deliberately used instead of `last_day` (a raw daily rate that
        resets every day and would make `compute_window_gain`'s
        last-minus-first delta meaningless, RESEARCH.md Pitfall 1).
        """
        package = raw["package"]
        data = raw.get("data", {}) or {}
        return CollectedItem(
            source=self.source_id,
            source_native_id=package,
            full_name=package,
            url=f"https://pypi.org/project/{package}/",
            metrics={"downloads": data.get("last_week", 0) or 0},
            discovery_method="tracked-package",
        )
