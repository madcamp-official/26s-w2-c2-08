"""Unit coverage for Course Session cursor integrity and scope."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from tbd.repositories.sessions import SessionCursorPosition
from tbd.services.sessions import InvalidSessionCursorError, SessionCursorCodec

pytestmark = pytest.mark.unit

SECRET = "session-cursor-test-secret-that-is-at-least-32-bytes"


@pytest.mark.parametrize(
    "started_at",
    [datetime(2026, 7, 15, 9, 30, tzinfo=UTC), None],
)
def test_session_cursor_round_trip_preserves_started_at_null_position(
    started_at: datetime | None,
) -> None:
    """Legacy/null-start rows remain addressable after all started classes."""

    codec = SessionCursorCodec(SECRET)
    course_id = uuid4()
    position = SessionCursorPosition(started_at=started_at, session_id=uuid4())

    cursor = codec.encode(course_id=course_id, status="COMPLETED", position=position)

    assert (
        codec.decode(
            cursor=cursor,
            course_id=course_id,
            status="COMPLETED",
        )
        == position
    )


def test_session_cursor_rejects_tampering_and_scope_reuse() -> None:
    """One signed position cannot cross a Course or status-filter boundary."""

    codec = SessionCursorCodec(SECRET)
    course_id = uuid4()
    cursor = codec.encode(
        course_id=course_id,
        status="COMPLETED",
        position=SessionCursorPosition(
            started_at=datetime(2026, 7, 15, 9, 30, tzinfo=UTC),
            session_id=UUID("00000000-0000-0000-0000-000000000123"),
        ),
    )

    replacement = "A" if cursor[-1] != "A" else "B"
    with pytest.raises(InvalidSessionCursorError):
        codec.decode(
            cursor=f"{cursor[:-1]}{replacement}",
            course_id=course_id,
            status="COMPLETED",
        )
    with pytest.raises(InvalidSessionCursorError):
        codec.decode(cursor=cursor, course_id=uuid4(), status="COMPLETED")
    with pytest.raises(InvalidSessionCursorError):
        codec.decode(cursor=cursor, course_id=course_id, status="LIVE")
    with pytest.raises(InvalidSessionCursorError):
        codec.decode(cursor=cursor, course_id=course_id, status=None)


@pytest.mark.parametrize("cursor", ["", "not-base64!", "e30", "W10"])
def test_session_cursor_rejects_malformed_values(cursor: str) -> None:
    codec = SessionCursorCodec(SECRET)

    with pytest.raises(InvalidSessionCursorError):
        codec.decode(cursor=cursor, course_id=uuid4(), status="COMPLETED")
