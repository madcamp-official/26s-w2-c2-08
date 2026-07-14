import { infiniteQueryOptions } from '@tanstack/react-query'

import { listCourseMaterialArchive, listCourseTranscriptArchive } from './api'

export const courseArchiveKeys = {
  all: ['course-archives'] as const,
  materials: (courseId: string) =>
    ['course-archives', courseId, 'materials'] as const,
  transcripts: (courseId: string) =>
    ['course-archives', courseId, 'transcripts'] as const,
}

export function courseTranscriptsInfiniteQueryOptions(courseId: string) {
  return infiniteQueryOptions({
    queryKey: courseArchiveKeys.transcripts(courseId),
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) =>
      listCourseTranscriptArchive(courseId, pageParam, signal),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  })
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
