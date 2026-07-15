"""Deadline policy for initial HQ processing and completed retries."""

from datetime import UTC, datetime, timedelta

import pytest

from tbd.services.recording_transcription import transcription_deadline

pytestmark = pytest.mark.unit


def test_initial_hq_attempt_keeps_the_session_processing_deadline() -> None:
    ended_at = datetime(2026, 7, 15, 10, 0, tzinfo=UTC)
    claimed_at = ended_at + timedelta(minutes=3)

    assert transcription_deadline(
        session_status="PROCESSING",
        attempt=1,
        ended_at=ended_at,
        claimed_at=claimed_at,
    ) == ended_at + timedelta(minutes=10)


def test_completed_hq_retry_gets_a_fresh_processing_window() -> None:
    ended_at = datetime(2026, 7, 15, 10, 0, tzinfo=UTC)
    claimed_at = ended_at + timedelta(hours=2)

    assert transcription_deadline(
        session_status="COMPLETED",
        attempt=2,
        ended_at=ended_at,
        claimed_at=claimed_at,
    ) == claimed_at + timedelta(minutes=10)
