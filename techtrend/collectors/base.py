"""Collector plugin seam (COLL-06).

`Collector` is the protocol every source implements. `CollectedItem` is the
one contract every source normalizes onto -- validated strictly so a
malformed or unexpected upstream response shape fails here, at the collector
boundary, rather than reaching SQL (T-01-11 mitigation). Nothing above this
module (identity resolution, snapshot writing, the orchestrator) may know
anything GitHub-specific; that is what makes Phase 3's "add a source by
writing one module plus one registry line" success criterion possible.
"""

from datetime import date
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class CollectedItem(BaseModel):
    """Normalized shape every `Collector.normalize()` returns.

    `metrics` carries every numeric signal the source produces as a flat
    dict of metric name to integer value (e.g. `{"stars": 34521, "releases": 12}`)
    so the source-agnostic snapshot writer can iterate it without knowing what
    a "star" or a "release" is.

    `readme_text` and `homepage` are the two inputs the docs-link resolution
    chain (D-15) needs; both are optional because not every source will have
    a README to scan.
    """

    model_config = ConfigDict(extra="forbid")

    source: str
    source_native_id: str | None
    full_name: str
    url: str
    homepage: str | None = None
    description: str | None = None
    metrics: dict[str, int] = Field(default_factory=dict)
    topics: list[str] = Field(default_factory=list)
    discovery_method: str
    readme_text: str | None = None


@runtime_checkable
class Collector(Protocol):
    """Every source module implements this. `registry.py` is the only file
    the orchestrator iterates -- it never branches on `source_id`.

    `@runtime_checkable` so tests (and any future structural registration
    check) can `isinstance(collector, Collector)` against `COLLECTORS`
    entries -- Protocol's default `isinstance` support raises `TypeError`
    without this decorator.
    """

    source_id: str

    def fetch(self, since: date) -> list[dict]:
        """Return raw, source-native dicts for every candidate item as of `since`."""
        ...

    def normalize(self, raw: dict) -> CollectedItem:
        """Map one raw dict from `fetch()` onto the source-agnostic `CollectedItem`."""
        ...
