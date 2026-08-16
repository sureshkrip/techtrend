"""Tests for the chained daily entrypoint `python -m techtrend.daily`.

Mirrors test_stability.py's monkeypatch idiom: the three stage `main`
functions are fully stubbed (no DB, no network), each recording its stage
name into a shared list so ordering and short-circuit behavior are asserted
purely from call order and returned exit codes.
"""


def test_daily_runs_stages_in_order_on_success(monkeypatch):
    """All three stages run in collect -> score -> enrich order and daily
    returns 0 when each stage succeeds.
    """
    from techtrend import daily, enrich, ingest, score

    calls: list[str] = []
    monkeypatch.setattr(ingest, "main", lambda argv=None: calls.append("collect") or 0)
    monkeypatch.setattr(score, "main", lambda argv=None: calls.append("score") or 0)
    monkeypatch.setattr(enrich, "main", lambda argv=None: calls.append("enrich") or 0)

    assert daily.main([]) == 0
    assert calls == ["collect", "score", "enrich"]


def test_daily_short_circuits_and_propagates_nonzero(monkeypatch):
    """A non-zero score-stage code halts the chain: enrich never runs and
    the exact code is returned unchanged.
    """
    from techtrend import daily, enrich, ingest, score

    calls: list[str] = []
    monkeypatch.setattr(ingest, "main", lambda argv=None: calls.append("collect") or 0)
    monkeypatch.setattr(score, "main", lambda argv=None: calls.append("score") or 3)
    monkeypatch.setattr(enrich, "main", lambda argv=None: calls.append("enrich") or 0)

    assert daily.main([]) == 3
    assert calls == ["collect", "score"]


def test_daily_main_signature_and_callable():
    """`techtrend.daily.main` is callable with an argv=None default."""
    import inspect

    from techtrend import daily

    assert callable(daily.main)
    sig = inspect.signature(daily.main)
    assert sig.parameters["argv"].default is None
