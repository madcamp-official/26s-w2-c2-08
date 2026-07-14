import type { components } from '../../api/generated/schema'
import { apiClient } from '../../api/client'
import { apiErrorFromResponse, normalizeApiError } from '../../api/errors'

export type CourseMaterialArchiveItem =
  components['schemas']['CourseMaterialArchiveItem']
export type CourseTranscriptArchiveItem =
  components['schemas']['CourseTranscriptArchiveItem']
export type CourseQnaArchiveItem = components['schemas']['CourseQnaArchiveItem']
type CourseTranscriptArchiveResponse =
  components['schemas']['CourseTranscriptArchiveResponse']
type CourseQnaArchiveResponse =
  components['schemas']['CourseQnaArchiveResponse']
export type CourseSummaryArchiveItem =
  components['schemas']['CourseSummaryArchiveItem']
type CourseSummaryArchiveResponse =
  components['schemas']['CourseSummaryArchiveResponse']

export async function listCourseMaterialArchive(
  courseId: string,
  cursor?: string,
  signal?: AbortSignal,
) {
  try {
    const { data, error, response } = await apiClient.GET(
      '/api/v1/courses/{course_id}/materials',
      {
        params: {
          path: { course_id: courseId },
          query: { cursor, limit: 20 },
        },
        signal,
      },
    )
    if (error) throw apiErrorFromResponse(response, error)
    return data
  } catch (error) {
    throw normalizeApiError(error)
  }
}

export async function listCourseTranscriptArchive(
  courseId: string,
  cursor?: string,
  signal?: AbortSignal,
): Promise<CourseTranscriptArchiveResponse> {
  try {
    const { data, error, response } = await apiClient.GET(
      '/api/v1/courses/{course_id}/transcripts',
      {
        params: {
          path: { course_id: courseId },
          query: { cursor, limit: 20 },
        },
        signal,
      },
    )
    if (error) throw apiErrorFromResponse(response, error)
    // openapi-typescript expands the response's allOf/oneOf branches more
    // narrowly than the named component even though both represent the same
    // wire schema. Normalize that generator artifact at the API boundary.
    return data as CourseTranscriptArchiveResponse
  } catch (error) {
    throw normalizeApiError(error)
  }
}

export async function listCourseQnaArchive(
  courseId: string,
  cursor?: string,
  signal?: AbortSignal,
): Promise<CourseQnaArchiveResponse> {
  try {
    const { data, error, response } = await apiClient.GET(
      '/api/v1/courses/{course_id}/qna',
      {
        params: {
          path: { course_id: courseId },
          query: { cursor, limit: 20 },
        },
        signal,
      },
    )
    if (error) throw apiErrorFromResponse(response, error)
    return data as CourseQnaArchiveResponse
  } catch (error) {
    throw normalizeApiError(error)
  }
}

export async function listCourseSummaryArchive(
  courseId: string,
  cursor?: string,
  signal?: AbortSignal,
): Promise<CourseSummaryArchiveResponse> {
  try {
    const { data, error, response } = await apiClient.GET(
      '/api/v1/courses/{course_id}/summaries',
      {
        params: {
          path: { course_id: courseId },
          query: { cursor, limit: 20 },
        },
        signal,
      },
    )
    if (error) throw apiErrorFromResponse(response, error)
    // The generated operation response expands the archive's oneOf more
    // narrowly than its named component. Keep that generator detail at the
    // API boundary so the screen can consume one stable archive shape.
    return data as CourseSummaryArchiveResponse
  } catch (error) {
    throw normalizeApiError(error)
  }
}
