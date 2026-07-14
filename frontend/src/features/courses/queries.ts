import { queryOptions } from '@tanstack/react-query'

import type { CourseRoleFilter } from './api'
import { getCourse, getSession, listCourseSessions, listCourses } from './api'

export const courseKeys = {
  all: ['courses'] as const,
  list: (role: CourseRoleFilter) => ['courses', 'list', role] as const,
  detail: (courseId: string) => ['courses', 'detail', courseId] as const,
  sessions: (courseId: string) => ['courses', courseId, 'sessions'] as const,
  session: (sessionId: string) => ['sessions', 'detail', sessionId] as const,
}

export function courseSessionsQueryOptions(courseId: string) {
  return queryOptions({
    queryKey: courseKeys.sessions(courseId),
    queryFn: ({ signal }) => listCourseSessions(courseId, signal),
  })
}

export function sessionQueryOptions(sessionId: string) {
  return queryOptions({
    queryKey: courseKeys.session(sessionId),
    queryFn: ({ signal }) => getSession(sessionId, signal),
  })
}

export function courseListQueryOptions(role: CourseRoleFilter) {
  return queryOptions({
    queryKey: courseKeys.list(role),
    queryFn: ({ signal }) => listCourses(role, signal),
  })
}

export function courseDetailQueryOptions(courseId: string) {
  return queryOptions({
    queryKey: courseKeys.detail(courseId),
    queryFn: ({ signal }) => getCourse(courseId, signal),
  })
}
