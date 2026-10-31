"""Source-specific raw-metric to momentum conversion (SCORE-04, D-13).

This is the seam that lets Phase 3 add Hacker News, npm, and PyPI without
touching the source-agnostic ranking step in `score.py`: each source
implements a converter here, mapping its own raw metric onto a comparable
`(successes, n)` momentum pair, and `momentum_for_source` dispatches to it.

D-13: build the seam, calibrate later. GitHub's converter is the identity
mapping -- stars gained and stars total pass through unchanged. Do NOT
attempt to calibrate against HN points or download counts that have never
been observed; that is explicitly out of scope until Phase 3 has real data
to calibrate against.
"""

from dataclasses import dataclass


@dataclass
class GitHubMomentum:
    """GitHub's momentum conversion: identity mapping for stars.

    stars_gained and stars_total already ARE a comparable (successes, n)
    pair for GitHub -- no transformation is needed. Kept as an explicit
    class (rather than inlining the identity) so the seam has exactly one
    concrete implementer to point Phase 3's collectors at.
    """

    def convert(self, gain: int, total: int) -> tuple[int, int]:
        return gain, total


@dataclass
class HackerNewsMomentum:
    """Hacker News's momentum conversion: identity mapping for points.

    Per D-13, this stays an identity pass-through until Phase 3 has real
    observed points data to calibrate against -- no cross-source weighting
    is attempted here.
    """

    def convert(self, gain: int, total: int) -> tuple[int, int]:
        return gain, total


@dataclass
class PackageDownloadsMomentum:
    """npm/PyPI's momentum conversion: identity mapping for downloads.

    Shared by both package registries since their raw metric (a downloads
    count) is the same shape. Per D-13, this stays an identity pass-through
    until there is observed download data to calibrate against.
    """

    def convert(self, gain: int, total: int) -> tuple[int, int]:
        return gain, total


@dataclass
class ChangelogMomentum:
    """Vendor changelogs' momentum conversion: identity mapping for
    releases-in-window (D3-3).

    A "release" is an event, not a cumulative count, but it still arrives
    here as the same (gain, total) shape every other converter consumes --
    no transformation is needed. Per D-13, stays identity until there is
    observed release-count data to calibrate against.
    """

    def convert(self, gain: int, total: int) -> tuple[int, int]:
        return gain, total


# Maps each source_id to the `snapshots.metric_name` that carries its
# momentum signal. Colocated with `_CONVERTERS` below because both are the
# same per-source dispatch: this map tells the scorer WHICH metric to read;
# `_CONVERTERS` tells it how to turn that metric's (gain, total) into a
# comparable momentum pair.
PRIMARY_METRIC: dict[str, str] = {
    "github": "stars",
    "hn": "points",
    "npm": "downloads",
    "pypi": "downloads",
    "changelog": "releases",
    "huggingface": "likes",
    "lobsters": "points",
    "reddit": "points",
}


def primary_metric_for_source(source: str) -> str:
    """Resolve the `snapshots.metric_name` that carries `source`'s momentum.

    An unrecognized source falls back to 'stars' -- mirroring
    `momentum_for_source`'s fallback-to-identity behavior, so scoring an
    entity from a source this seam hasn't been extended for yet degrades
    gracefully instead of raising or silently zeroing.
    """
    return PRIMARY_METRIC.get(source, "stars")


_CONVERTERS: dict[str, GitHubMomentum | HackerNewsMomentum | PackageDownloadsMomentum | ChangelogMomentum] = {
    "github": GitHubMomentum(),
    "hn": HackerNewsMomentum(),
    "npm": PackageDownloadsMomentum(),
    "pypi": PackageDownloadsMomentum(),
    "changelog": ChangelogMomentum(),
}


def momentum_for_source(source: str, gain: int, total: int) -> tuple[int, int]:
    """Route a source's raw (gain, total) metric through its converter.

    An unrecognized source falls back to the identity mapping rather than
    raising -- ranking must never crash on a source this seam hasn't been
    extended for yet.
    """
    converter = _CONVERTERS.get(source)
    if converter is None:
        return gain, total
    return converter.convert(gain, total)
