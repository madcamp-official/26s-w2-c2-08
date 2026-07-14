import { infiniteQueryOptions, queryOptions } from '@tanstack/react-query'

import type { CourseRoleFilter, LectureSession } from './api'
import { getCourse, getSession, listCourseSessions, listCourses } from './api'

export const courseKeys = {
  all: ['courses'] as const,
  list: (role: CourseRoleFilter) => ['courses', 'list', role] as const,
  infiniteList: (role: CourseRoleFilter) =>
    ['courses', 'infinite-list', role] as const,
  detail: (courseId: string) => ['courses', 'detail', courseId] as const,
  sessions: (courseId: string) => ['courses', courseId, 'sessions'] as const,
  completedSessions: (courseId: string) =>
    ['courses', courseId, 'sessions', 'COMPLETED'] as const,
  session: (sessionId: string) => ['sessions', 'detail', sessionId] as const,
}

export function sessionNeedsStatusPolling(
  session: Pick<LectureSession, 'status'> | undefined,
) {
  return session?.status === 'READY'
}

export function courseSessionsQueryOptions(courseId: string) {
  return queryOptions({
    queryKey: courseKeys.sessions(courseId),
    queryFn: ({ signal }) => listCourseSessions(courseId, {}, signal),
  })
}

export function courseCompletedSessionsInfiniteQueryOptions(courseId: string) {
  return infiniteQueryOptions({
    queryKey: courseKeys.completedSessions(courseId),
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) =>
      listCourseSessions(
        courseId,
        { status: 'COMPLETED', cursor: pageParam, limit: 20 },
        signal,
      ),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  })
}

export function sessionQueryOptions(sessionId: string) {
  return queryOptions({
    queryKey: courseKeys.session(sessionId),
    queryFn: ({ signal }) => getSession(sessionId, signal),
    refetchInterval: (query) =>
      sessionNeedsStatusPolling(query.state.data) ? 5_000 : false,
  })
}

export function courseListQueryOptions(role: CourseRoleFilter) {
  return queryOptions({
    queryKey: courseKeys.list(role),
    queryFn: ({ signal }) => listCourses(role, {}, signal),
  })
}

export function courseInfiniteListQueryOptions(role: CourseRoleFilter) {
  return infiniteQueryOptions({
    queryKey: courseKeys.infiniteList(role),
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) =>
      listCourses(role, { cursor: pageParam }, signal),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  })
}

export function courseDetailQueryOptions(courseId: string) {
  return queryOptions({
    queryKey: courseKeys.detail(courseId),
    queryFn: ({ signal }) => getCourse(courseId, signal),
  })
}
