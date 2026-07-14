import { queryOptions } from '@tanstack/react-query'

import { getSessionRecord } from './api'

export const recordKeys = {
  all: ['records'] as const,
  manifest: (sessionId: string) => ['records', 'manifest', sessionId] as const,
  timeline: (sessionId: string, transcriptVersionId: string) =>
    ['records', 'timeline', sessionId, transcriptVersionId] as const,
  summary: (sessionId: string) => ['records', 'summary', sessionId] as const,
  questions: (sessionId: string) =>
    ['records', 'questions', sessionId] as const,
  openQuestions: (sessionId: string) =>
    ['records', 'open-questions', sessionId] as const,
  answers: (sessionId: string) => ['records', 'answers', sessionId] as const,
  finalClusters: (sessionId: string) =>
    ['records', 'final-clusters', sessionId] as const,
  finalClusterMembers: (sessionId: string, clusterId: string) =>
    ['records', 'final-cluster-members', sessionId, clusterId] as const,
  jobs: (sessionId: string) => ['records', 'jobs', sessionId] as const,
}

export function recordManifestQueryOptions(sessionId: string) {
  return queryOptions({
    queryKey: recordKeys.manifest(sessionId),
    queryFn: ({ signal }) => getSessionRecord(sessionId, signal),
  })
}
