import type { components } from '../../api/generated/schema'
import { apiClient } from '../../api/client'
import { apiErrorFromResponse, normalizeApiError } from '../../api/errors'

export type CourseMaterialArchiveItem =
  components['schemas']['CourseMaterialArchiveItem']

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
