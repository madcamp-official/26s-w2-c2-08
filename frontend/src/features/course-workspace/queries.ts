import { infiniteQueryOptions } from '@tanstack/react-query'

import { listCourseMaterialArchive } from './api'

export const courseArchiveKeys = {
  all: ['course-archives'] as const,
  materials: (courseId: string) =>
    ['course-archives', courseId, 'materials'] as const,
}

export function courseMaterialsInfiniteQueryOptions(courseId: string) {
  return infiniteQueryOptions({
    queryKey: courseArchiveKeys.materials(courseId),
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) =>
      listCourseMaterialArchive(courseId, pageParam, signal),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  })
}
