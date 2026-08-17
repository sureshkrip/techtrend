"""OpenAI-compatible structured-output LLM client tests (quick-260817-09l).

Mirrors `tests/test_llm.py`'s structure: imports inside each test function,
no live API calls anywhere. `_FakeOpenAIClient` replays a small fake
`.chat.completions.create(**kwargs)` response shaped like the subset of the
openai SDK's `ChatCompletion` the caller reads: `.choices[0].message.content`
and `.choices[0].finish_reason`.
"""

import json

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


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content, finish_reason):
        self.message = _FakeMessage(content)
        self.finish_reason = finish_reason


class _FakeChatCompletion:
    def __init__(self, content, finish_reason):
        self.choices = [_FakeChoice(content, finish_reason)]


class _FakeCompletions:
    def __init__(self, response):
        self._response = response
        self.last_call_kwargs = None

    def create(self, **kwargs):
        self.last_call_kwargs = kwargs
        return self._response


class _FakeChat:
    def __init__(self, response):
        self.completions = _FakeCompletions(response)


class _FakeOpenAIClient:
    def __init__(self, response):
        self.chat = _FakeChat(response)


def test_enrich_item_openai_returns_two_line_summary():
    from techtrend.pipeline.llm_openai import enrich_item_openai

    data = {
        "summary_line_1": "A coding agent CLI.",
        "summary_line_2": "It automates multi-step engineering tasks.",
        "section": "agentic_coding_tools",
        "confidence": "high",
    }
    fake_client = _FakeOpenAIClient(
        _FakeChatCompletion(json.dumps(data), finish_reason="stop")
    )

    output = enrich_item_openai(
        fake_client,
        model="kimi-k2.5",
        sections=SECTIONS,
        description="A short repo description.",
        readme_intro="A short README intro paragraph.",
    )

    assert output is not None
    assert output.summary_line_1 == data["summary_line_1"]
    assert output.summary_line_2 == data["summary_line_2"]
    assert output.section == data["section"]


def test_enrich_item_openai_returns_none_on_empty_content():
    from techtrend.pipeline.llm_openai import enrich_item_openai

    fake_client = _FakeOpenAIClient(_FakeChatCompletion(None, finish_reason="stop"))

    output = enrich_item_openai(
        fake_client,
        model="kimi-k2.5",
        sections=SECTIONS,
        description="A short repo description.",
        readme_intro="A short README intro paragraph.",
    )

    assert output is None


def test_enrich_item_openai_returns_none_on_non_json_content():
    from techtrend.pipeline.llm_openai import enrich_item_openai

    fake_client = _FakeOpenAIClient(
        _FakeChatCompletion("not json at all", finish_reason="stop")
    )

    output = enrich_item_openai(
        fake_client,
        model="kimi-k2.5",
        sections=SECTIONS,
        description="A short repo description.",
        readme_intro="A short README intro paragraph.",
    )

    assert output is None


def test_enrich_item_openai_returns_none_on_refusal():
    """A content-policy refusal (finish_reason == 'content_filter') must be
    treated identically to a fetch failure -- skip, never fabricate."""
    from techtrend.pipeline.llm_openai import enrich_item_openai

    data = {
        "summary_line_1": "line one",
        "summary_line_2": "line two",
        "section": "agentic_coding_tools",
        "confidence": "high",
    }
    fake_client = _FakeOpenAIClient(
        _FakeChatCompletion(json.dumps(data), finish_reason="content_filter")
    )

    output = enrich_item_openai(
        fake_client,
        model="kimi-k2.5",
        sections=SECTIONS,
        description="A short repo description.",
        readme_intro="A short README intro paragraph.",
    )

    assert output is None


def test_enrich_item_openai_returns_none_on_invalid_section():
    """ENR-04/D-02: an out-of-enum section id fails Pydantic validation and
    must return None, not raise or silently coerce."""
    from techtrend.pipeline.llm_openai import enrich_item_openai

    data = {
        "summary_line_1": "line one",
        "summary_line_2": "line two",
        "section": "not_a_real_section",
        "confidence": "high",
    }
    fake_client = _FakeOpenAIClient(
        _FakeChatCompletion(json.dumps(data), finish_reason="stop")
    )

    output = enrich_item_openai(
        fake_client,
        model="kimi-k2.5",
        sections=SECTIONS,
        description="A short repo description.",
        readme_intro="A short README intro paragraph.",
    )

    assert output is None
