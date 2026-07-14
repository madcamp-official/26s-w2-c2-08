import type { components } from '../../api/generated/schema'
import { apiClient } from '../../api/client'
import { apiErrorFromResponse, normalizeApiError } from '../../api/errors'

export type Course = components['schemas']['Course']
export type CourseRoleFilter = components['schemas']['CourseRoleFilter']
export type CourseCreateInput = components['schemas']['CourseCreateRequest']

export interface CourseJoinInput {
  join_code: string
}

function idempotencyHeaders(key?: string) {
  return key ? { 'Idempotency-Key': key } : undefined
}

export async function listCourses(
  role: CourseRoleFilter,
  signal?: AbortSignal,
) {
  try {
    const { data, error, response } = await apiClient.GET('/api/v1/courses', {
      params: { query: { role, limit: 100 } },
      signal,
    })
    if (error) throw apiErrorFromResponse(response, error)
    return data
  } catch (error) {
    throw normalizeApiError(error)
  }
}

export async function getCourse(courseId: string, signal?: AbortSignal) {
  try {
    const { data, error, response } = await apiClient.GET(
      '/api/v1/courses/{course_id}',
      {
        params: { path: { course_id: courseId } },
        signal,
      },
    )
    if (error) throw apiErrorFromResponse(response, error)
    return data
  } catch (error) {
    throw normalizeApiError(error)
  }
}

export async function createCourse(
  input: CourseCreateInput,
  idempotencyKey: string,
) {
  try {
    const { data, error, response } = await apiClient.POST('/api/v1/courses', {
      body: input,
      headers: idempotencyHeaders(idempotencyKey),
    })
    if (error) throw apiErrorFromResponse(response, error)
    return data
  } catch (error) {
    throw normalizeApiError(error)
  }
}

export async function joinCourse(
  input: CourseJoinInput,
  idempotencyKey: string,
) {
  try {
    const { data, error, response } = await apiClient.POST(
      '/api/v1/courses/join',
      {
        body: input,
        headers: idempotencyHeaders(idempotencyKey),
      },
    )
    if (error) throw apiErrorFromResponse(response, error)
    return { course: data, created: response.status === 201 }
  } catch (error) {
    throw normalizeApiError(error)
  }
}

export async function rotateCourseJoinCode(
  courseId: string,
  idempotencyKey: string,
) {
  try {
    const { data, error, response } = await apiClient.POST(
      '/api/v1/courses/{course_id}/join-code/rotate',
      {
        params: {
          path: { course_id: courseId },
          header: { 'Idempotency-Key': idempotencyKey },
        },
      },
    )
    if (error) throw apiErrorFromResponse(response, error)
    return data
  } catch (error) {
    throw normalizeApiError(error)
  }
}
