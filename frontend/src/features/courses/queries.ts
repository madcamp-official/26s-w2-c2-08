import { queryOptions } from '@tanstack/react-query'

import type { CourseRoleFilter } from './api'
import { getCourse, listCourses } from './api'

export const courseKeys = {
  all: ['courses'] as const,
  list: (role: CourseRoleFilter) => ['courses', 'list', role] as const,
  detail: (courseId: string) => ['courses', 'detail', courseId] as const,
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
