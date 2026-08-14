"""Grounding text extraction and normalization (ENR-05, D-07, D-09; Common
Pitfall 1 -- badge-churn cache defeat).

`normalize_for_hash` strips markdown badge images and HTML comments and
collapses whitespace BEFORE hashing, so churning CI badges never register as
a content change (D-09, Pitfall #1) -- the cache would otherwise almost
never hit for actively-CI'd, high-traffic repos, quietly multiplying LLM
spend for exactly the repos this dashboard cares most about.
"""

import re

_BADGE_MD_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_DEEP_HEADING_RE = re.compile(r"^#{2,}\s", re.MULTILINE)  # H2 and deeper


def extract_intro(readme_text: str, char_cap: int) -> str:
    """Top section of the README: everything before the first H2+ heading,
    capped to char_cap characters. An H1 title (if present) is kept (D-07)."""
    match = _DEEP_HEADING_RE.search(readme_text)
    intro = readme_text[: match.start()] if match else readme_text
    return intro[:char_cap].strip()


def normalize_for_hash(description: str | None, readme_intro: str) -> str:
    """Strip badge markup and HTML comments (Common Pitfall #1), collapse
    whitespace, before hashing -- badge/whitespace churn must never register
    as a content change (D-09)."""
    combined = f"{description or ''}\n{readme_intro}"
    combined = _BADGE_MD_RE.sub("", combined)
    combined = _HTML_COMMENT_RE.sub("", combined)
    return re.sub(r"\s+", " ", combined).strip()
