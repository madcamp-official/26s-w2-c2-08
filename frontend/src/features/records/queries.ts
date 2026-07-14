import { queryOptions } from '@tanstack/react-query'

import { getSessionRecord } from './api'

export const recordKeys = {
  all: ['records'] as const,
  manifest: (sessionId: string) => ['records', 'manifest', sessionId] as const,
  timeline: (sessionId: string, transcriptVersionId: string) =>
    ['records', 'timeline', sessionId, transcriptVersionId] as const,
  summary: (sessionId: string) => ['records', 'summary', sessionId] as const,
}

export function recordManifestQueryOptions(sessionId: string) {
  return queryOptions({
    queryKey: recordKeys.manifest(sessionId),
    queryFn: ({ signal }) => getSessionRecord(sessionId, signal),
  })
}
