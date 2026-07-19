"""Docs-link resolution chain tests (DASH-05, D-15).

Covers the strict ordering (homepage -> README match -> repo fallback), the
honest 'repo' label on the bare-URL fallback, and deterministic first-match
ordering when the README contains several candidate links.
"""

from techtrend.pipeline.docs_link import DOCS_PATTERNS, resolve_docs_url


def test_homepage_wins_even_when_readme_also_has_a_matching_link():
    """DASH-05 adjacency: exactly one result, homepage wins, README never
    consulted even though it also contains a docs-pattern match.
    """
    repo_meta = {"homepage": "https://aider.chat", "html_url": "https://github.com/a/b"}
    readme = "See [docs](https://docs.aider.chat) for more."

    url, kind = resolve_docs_url(repo_meta, readme)

    assert url == "https://aider.chat"
    assert kind == "homepage"


def test_empty_homepage_falls_back_to_matching_readme_link(github_fixture):
    repo_meta = {"homepage": "", "html_url": "https://github.com/example-org/example-project"}
    readme = github_fixture("readme.md")

    url, kind = resolve_docs_url(repo_meta, readme)

    assert url == "https://example-project.dev/docs"
    assert kind == "readme"


def test_empty_homepage_and_no_matching_readme_link_falls_back_to_repo_url():
    """DASH-05 empty: no homepage, no matching README link -> the bare
    repo html_url, labeled honestly as 'repo'.
    """
    repo_meta = {"homepage": None, "html_url": "https://github.com/a/b"}

    url, kind = resolve_docs_url(repo_meta, "no links here at all")

    assert (url, kind) == ("https://github.com/a/b", "repo")


def test_multiple_matching_readme_links_returns_first_in_document_order():
    repo_meta = {"homepage": "", "html_url": "https://github.com/a/b"}
    readme = (
        "First see [getting started](https://example.com/getting-started) "
        "and also our [documentation](https://example.com/documentation)."
    )

    first_call = resolve_docs_url(repo_meta, readme)
    second_call = resolve_docs_url(repo_meta, readme)

    assert first_call == ("https://example.com/getting-started", "readme")
    # Deterministic: repeated calls against the same input are identical.
    assert first_call == second_call


def test_kind_is_always_exactly_one_of_three_literals_and_repo_never_relabeled():
    homepage_result = resolve_docs_url(
        {"homepage": "https://x.dev", "html_url": "https://github.com/a/b"}, None
    )
    readme_result = resolve_docs_url(
        {"homepage": "", "html_url": "https://github.com/a/b"},
        "[quickstart](https://example.com/quickstart)",
    )
    repo_result = resolve_docs_url({"homepage": "", "html_url": "https://github.com/a/b"}, None)

    for _, kind in (homepage_result, readme_result, repo_result):
        assert kind in ("homepage", "readme", "repo")

    assert repo_result[1] == "repo"
    assert len(DOCS_PATTERNS) >= 6
