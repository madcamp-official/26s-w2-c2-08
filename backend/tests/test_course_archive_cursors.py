"""Unit coverage for Course archive cursor integrity and scope."""

from uuid import uuid4

import pytest

from tbd.services.course_archives import (
    CourseArchiveCursorCodec,
    InvalidCourseArchiveCursorError,
)

pytestmark = pytest.mark.unit
SECRET = "course-archive-test-secret-that-is-at-least-32-bytes"
RESOURCE = "course_materials"
SCOPE = {
    "attached": True,
    "sort": ["active_first", "material_created_at_asc"],
}


def test_course_archive_cursor_round_trip_preserves_position() -> None:
    codec = CourseArchiveCursorCodec(SECRET)
    course_id = uuid4()
    position = [0, None, str(uuid4()), "2026-07-15T01:02:03+00:00", str(uuid4())]

    cursor = codec.encode(
        course_id=course_id,
        resource=RESOURCE,
        scope=SCOPE,
        position=position,
    )

    assert (
        codec.decode(
            cursor=cursor,
            course_id=course_id,
            resource=RESOURCE,
            scope=SCOPE,
        )
        == position
    )


def test_course_archive_cursor_rejects_tampering_and_scope_reuse() -> None:
    codec = CourseArchiveCursorCodec(SECRET)
    course_id = uuid4()
    cursor = codec.encode(
        course_id=course_id,
        resource=RESOURCE,
        scope=SCOPE,
        position=[1, "2026-07-15T01:02:03+00:00", str(uuid4())],
    )
    replacement = "A" if cursor[-1] != "A" else "B"

    with pytest.raises(InvalidCourseArchiveCursorError):
        codec.decode(
            cursor=f"{cursor[:-1]}{replacement}",
            course_id=course_id,
            resource=RESOURCE,
            scope=SCOPE,
        )
    with pytest.raises(InvalidCourseArchiveCursorError):
        codec.decode(
            cursor=cursor,
            course_id=uuid4(),
            resource=RESOURCE,
            scope=SCOPE,
        )
    with pytest.raises(InvalidCourseArchiveCursorError):
        codec.decode(
            cursor=cursor,
            course_id=course_id,
            resource="course_transcripts",
            scope=SCOPE,
        )
    with pytest.raises(InvalidCourseArchiveCursorError):
        codec.decode(
            cursor=cursor,
            course_id=course_id,
            resource=RESOURCE,
            scope={**SCOPE, "attached": False},
        )


@pytest.mark.parametrize("cursor", ["", "not-base64!", "e30", "W10"])
def test_course_archive_cursor_rejects_malformed_values(cursor: str) -> None:
    with pytest.raises(InvalidCourseArchiveCursorError):
        CourseArchiveCursorCodec(SECRET).decode(
            cursor=cursor,
            course_id=uuid4(),
            resource=RESOURCE,
            scope=SCOPE,
        )
