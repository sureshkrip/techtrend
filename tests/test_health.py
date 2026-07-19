"""Placeholder for run health tests.

Covers HEALTH-01 (run outcome recording), HEALTH-02 (staleness flagging).
HEALTH-01's idempotency guarantee is already proven in test_storage.py; this
file covers the remaining health-reporting behavior in a later plan.
"""

import pytest


def test_health_placeholder():
    pytest.skip("HEALTH-01/HEALTH-02: implemented in a later plan in this phase")
