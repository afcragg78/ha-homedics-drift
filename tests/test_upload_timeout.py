"""Upload confirmation waits stay bounded and never go below the base timeout."""

from __future__ import annotations

from custom_components.homedics_drift.const import (
    UPLOAD_STORE_TIMEOUT,
    UPLOAD_STORE_TIMEOUT_MAX,
    store_confirm_timeout,
)


def test_store_confirm_timeout_starts_at_fifteen_and_caps_at_sixty() -> None:
    assert store_confirm_timeout(0) == UPLOAD_STORE_TIMEOUT
    assert store_confirm_timeout(1) == 15.1
    # A weather-sized drawing (~325 pages of 40 points) stays under the cap.
    assert 15.0 < store_confirm_timeout(325) < UPLOAD_STORE_TIMEOUT_MAX
    assert store_confirm_timeout(1000) == UPLOAD_STORE_TIMEOUT_MAX
    assert store_confirm_timeout(-4) == UPLOAD_STORE_TIMEOUT
