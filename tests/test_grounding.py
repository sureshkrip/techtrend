"""Grounding text extraction/normalization tests (D-07, D-09, Common
Pitfall 1 -- badge-churn cache defeat; 02-VALIDATION.md Wave 0).

`techtrend.pipeline.grounding` does not exist yet -- these tests define
`extract_intro`/`normalize_for_hash`'s contract before a later plan
implements it. Imports are inside each test function so
`pytest --collect-only` succeeds cleanly (no module-level ImportError at
collection time); running the tests fails/errors until the module exists,
which is the intended Wave 0 RED state.
"""

from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "github"


def _load_readme_with_badges() -> str:
    return (FIXTURES_DIR / "readme_with_badges.md").read_text(encoding="utf-8")


def test_extract_intro_truncates_at_first_deep_heading():
    from techtrend.pipeline.grounding import extract_intro

    readme_text = _load_readme_with_badges()
    intro = extract_intro(readme_text, char_cap=2000)

    assert "Example Badge Repo" in intro
    assert "## Installation" not in intro
    assert "Install with your package manager" not in intro


def test_extract_intro_respects_char_cap():
    from techtrend.pipeline.grounding import extract_intro

    readme_text = _load_readme_with_badges()
    intro = extract_intro(readme_text, char_cap=20)

    assert len(intro) <= 20


def test_normalize_for_hash_strips_badges_and_comments_and_collapses_whitespace():
    from techtrend.pipeline.grounding import extract_intro, normalize_for_hash

    readme_text = _load_readme_with_badges()
    intro = extract_intro(readme_text, char_cap=2000)
    normalized = normalize_for_hash("A short repo description.", intro)

    assert "![" not in normalized
    assert "<!--" not in normalized
    assert "  " not in normalized  # no run of two+ spaces after collapsing


def test_normalize_for_hash_is_stable_across_badge_only_changes():
    """Pitfall 1: a badge/CI-status flip must never register as a content
    change -- otherwise the (entity, content_hash) cache almost never hits
    for actively-CI'd repos and DATA-04/SC4's cost guarantee breaks."""
    from techtrend.pipeline.grounding import normalize_for_hash

    intro_a = "Intro text.\n\n![build](https://img.shields.io/badge/build-passing)"
    intro_b = "Intro text.\n\n![build](https://img.shields.io/badge/build-failing)"

    assert normalize_for_hash("desc", intro_a) == normalize_for_hash("desc", intro_b)
