"""Jaccard rank-overlap stability metric tests (SCORE-05, D-12).

D-12: ship the 7-day-window-plus-Wilson-bound scorer with NO additional
damping in Phase 1, and log a stability metric each run so the need for
further smoothing is discovered empirically rather than assumed. EWMA
smoothing and rank hysteresis are both explicitly rejected -- hysteresis
specifically because it would make the displayed rank depend on yesterday's
rank, breaking the "scores are a pure function of (entities, snapshots)"
property.
"""


def test_rank_overlap_empty_sets():
    """Both sets empty -> 1.0, never a ZeroDivisionError on an empty union."""
    from techtrend.pipeline.stability import rank_overlap

    assert rank_overlap(set(), set()) == 1.0


def test_rank_overlap_partial():
    from techtrend.pipeline.stability import rank_overlap

    assert rank_overlap({1, 2, 3}, {2, 3, 4}) == 0.5
