"""Deterministic docs-link fallback chain (DASH-05, D-15).

Strictly ordered: `homepage` -> a matching link in the README -> the bare
repo URL. The third branch is load-bearing, not a throwaway default: it is a
*repository* URL, not documentation, and `docs_url_kind='repo'` records that
honestly so the dashboard never implies a fallback was verified as docs
(T-01-15 mitigation). No code path may relabel a `'repo'` result as
`'homepage'` or `'readme'` after the fact.
"""

import re

DOCS_PATTERNS: tuple[str, ...] = (
    "docs.",
    "/docs",
    "documentation",
    "getting-started",
    "getting_started",
    "quickstart",
)

# Matches markdown links `[text](url)` and bare http(s) URLs, in document
# order. No markdown parser is pulled in for link extraction alone -- a
# regex is sufficient and matches RESEARCH.md Pattern 6's guidance.
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]*)\]\((https?://[^\s)]+)\)")
_BARE_URL_RE = re.compile(r"https?://[^\s)\]]+")


def _extract_links(readme_text: str) -> list[tuple[str, str]]:
    """Returns `(text, url)` pairs in document order. Bare URLs already
    captured as part of a markdown link are not duplicated as bare matches.
    """
    links: list[tuple[str, str]] = []
    covered_spans: list[tuple[int, int]] = []

    for match in _MARKDOWN_LINK_RE.finditer(readme_text):
        links.append((match.group(1), match.group(2)))
        covered_spans.append(match.span())

    for match in _BARE_URL_RE.finditer(readme_text):
        start, end = match.span()
        if any(start >= s and end <= e for s, e in covered_spans):
            continue
        links.append(("", match.group(0)))

    # Re-sort by position in the original text so markdown links and bare
    # URLs interleave in true document order rather than markdown-first.
    def _position(pair: tuple[str, str]) -> int:
        _, url = pair
        return readme_text.find(url)

    return sorted(links, key=_position)


def resolve_docs_url(repo_meta: dict, readme_text: str | None) -> tuple[str, str]:
    """Returns `(url, kind)` where kind is exactly one of 'homepage',
    'readme', or 'repo'.

    Ordered per D-15: a non-empty `homepage` wins outright and the README is
    never consulted (DASH-05 adjacency -- exactly one result). Otherwise the
    first README link whose text or URL case-insensitively contains a
    `DOCS_PATTERNS` entry wins, in document order (DASH-05 ordering). If
    neither yields a result, the bare `html_url` is returned labeled
    honestly as `'repo'` (DASH-05 empty).
    """
    homepage = (repo_meta.get("homepage") or "").strip()
    if homepage:
        return homepage, "homepage"

    if readme_text:
        for text, url in _extract_links(readme_text):
            haystack = f"{text} {url}".lower()
            if any(pattern in haystack for pattern in DOCS_PATTERNS):
                return url, "readme"

    return repo_meta["html_url"], "repo"
