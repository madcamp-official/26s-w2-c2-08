import { queryOptions } from '@tanstack/react-query'

import { getLiveTranscript } from './api'

export const liveTranscriptKeys = {
  all: ['live-transcript'] as const,
  session: (sessionId: string) =>
    ['live-transcript', 'session', sessionId] as const,
}

export function liveTranscriptQueryOptions(sessionId: string) {
  return queryOptions({
    queryKey: liveTranscriptKeys.session(sessionId),
    queryFn: ({ signal }) => getLiveTranscript(sessionId, signal),
    staleTime: 0,
  })
}
