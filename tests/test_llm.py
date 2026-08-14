"""Anthropic structured-output LLM client tests (ENR-03, ENR-04, D-01, D-02;
02-VALIDATION.md Wave 0).

`techtrend.pipeline.llm` does not exist yet -- these tests define
`enrich_item`'s contract (two-line summary, section-enum enforcement,
refusal handling) before a later plan implements it, driven by a fake
Anthropic client that replays tests/fixtures/anthropic/*.json. No live API
call is made anywhere in this file (CLAUDE.md testing philosophy) -- the
fake client is injected via the same optional-parameter seam
`GitHubCollector.__init__(config=None, client=None)` already establishes
(techtrend/collectors/github.py). Imports are inside each test function so
`pytest --collect-only` succeeds cleanly at Wave 0.
"""

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "anthropic"

SECTIONS = [
    {
        "id": "agentic_coding_tools",
        "label": "Agentic coding tools",
        "description": "Claude Code, Cursor, Codex, Aider, GSD, Superpowers",
    },
    {
        "id": "models_releases",
        "label": "Models & releases",
        "description": "New model launches, capability/pricing changes, benchmarks",
    },
]


def _load_fixture(filename: str) -> dict:
    return json.loads((FIXTURES_DIR / filename).read_text(encoding="utf-8"))


class _FakeResponse:
    """Mimics the subset of anthropic's `ParsedMessage` the caller reads:
    `.stop_reason` and `.parsed_output`. Constructed test-side from a
    fixture so no live call is ever made."""

    def __init__(self, stop_reason, parsed_output=None):
        self.stop_reason = stop_reason
        self.parsed_output = parsed_output


class _FakeMessages:
    def __init__(self, response):
        self._response = response
        self.last_call_kwargs = None

    def parse(self, **kwargs):
        self.last_call_kwargs = kwargs
        return self._response


class _FakeAnthropicClient:
    def __init__(self, response):
        self.messages = _FakeMessages(response)


def test_enrich_item_returns_two_line_summary():
    from techtrend.pipeline.llm import EnrichmentResult, enrich_item

    data = _load_fixture("enrichment_success.json")
    result = EnrichmentResult(**data)
    fake_client = _FakeAnthropicClient(_FakeResponse("end_turn", parsed_output=result))

    output = enrich_item(
        fake_client,
        model="claude-haiku-4-5",
        sections=SECTIONS,
        description="A short repo description.",
        readme_intro="A short README intro paragraph.",
    )

    assert output is not None
    assert output.summary_line_1 == data["summary_line_1"]
    assert output.summary_line_2 == data["summary_line_2"]
    assert output.section == data["section"]


def test_section_constrained_to_enum():
    """ENR-04/D-02: exactly one of the configured section ids is a valid
    result -- schema enum enforcement, not free-text/fuzzy matching (Pattern
    2's per-request StrEnum, built from config-driven section ids)."""
    from techtrend.pipeline.llm import build_section_result_model

    section_ids = [s["id"] for s in SECTIONS]
    result_model = build_section_result_model(section_ids)

    valid = result_model(
        summary_line_1="line one",
        summary_line_2="line two",
        section="agentic_coding_tools",
        confidence="high",
    )
    assert valid.section == "agentic_coding_tools"

    with pytest.raises(Exception):  # noqa: B017 - pydantic ValidationError, not yet importable
        result_model(
            summary_line_1="line one",
            summary_line_2="line two",
            section="not_a_real_section",
            confidence="high",
        )


def test_refusal_returns_none():
    """Pitfall 4: `stop_reason == 'refusal'` must be handled before
    `parsed_output` is read -- treated identically to a fetch failure
    (D-08/D-10): skip, never fabricate, never crash the run."""
    from techtrend.pipeline.llm import enrich_item

    fake_client = _FakeAnthropicClient(_FakeResponse("refusal", parsed_output=None))

    output = enrich_item(
        fake_client,
        model="claude-haiku-4-5",
        sections=SECTIONS,
        description="A short repo description.",
        readme_intro="A short README intro paragraph.",
    )

    assert output is None
