"""Grounding text extraction/normalization/fetch tests (D-07, D-08, D-09,
ENR-05, Common Pitfall 1 -- badge-churn cache defeat; 02-VALIDATION.md
Wave 0 + 02-03 Task 2 fetch_grounding contract).

`extract_intro`/`normalize_for_hash` were Wave 0 failing scaffolds; the
`fetch_grounding` tests below were added in Plan 02-03 (Task 2) since Wave 0
did not scaffold them -- same RED-before-implementation discipline, driven
through an `httpx.MockTransport` (no live GitHub call), mirroring
`tests/test_collect_github.py`'s style.
"""

from pathlib import Path

import httpx

from techtrend.collectors.http import build_client

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


# ---------------------------------------------------------------------------
# fetch_grounding (Task 2, ENR-05, D-08) -- driven through httpx.MockTransport,
# no live GitHub call, mirroring tests/test_collect_github.py's style.
# ---------------------------------------------------------------------------


def test_fetch_grounding_returns_description_and_intro_on_success(monkeypatch, tmp_path, github_fixture):
    from techtrend.pipeline.grounding import fetch_grounding

    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    metadata = github_fixture("repo_metadata.json")
    readme_text = _load_readme_with_badges()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/readme"):
            return httpx.Response(200, text=readme_text)
        return httpx.Response(200, json=metadata)

    client = build_client(
        transport=httpx.MockTransport(handler), cache_db_path=tmp_path / "hishel.db"
    )
    try:
        result = fetch_grounding(client, metadata["full_name"], char_cap=2000)
    finally:
        client.close()

    assert result is not None
    description, intro = result
    assert description == metadata["description"]
    assert "Example Badge Repo" in intro
    assert "## Installation" not in intro


def test_fetch_grounding_returns_none_when_description_and_readme_both_empty(
    monkeypatch, tmp_path, github_fixture
):
    """ENR-05/D-08: description empty AND README unfetchable/empty -> None,
    the signal for the caller to skip the LLM entirely rather than fabricate."""
    from techtrend.pipeline.grounding import fetch_grounding

    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    metadata = dict(github_fixture("repo_metadata.json"))
    metadata["description"] = None

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/readme"):
            return httpx.Response(404, json={"message": "Not Found"})
        return httpx.Response(200, json=metadata)

    client = build_client(
        transport=httpx.MockTransport(handler), cache_db_path=tmp_path / "hishel.db"
    )
    try:
        result = fetch_grounding(client, metadata["full_name"], char_cap=2000)
    finally:
        client.close()

    assert result is None
