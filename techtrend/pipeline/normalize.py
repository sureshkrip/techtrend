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


_CONVERTERS: dict[str, GitHubMomentum] = {
    "github": GitHubMomentum(),
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
