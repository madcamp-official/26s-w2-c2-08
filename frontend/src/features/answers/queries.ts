import { queryOptions } from '@tanstack/react-query'

import { listSessionAnswers } from './api'

export const answerKeys = {
  all: ['answers'] as const,
  session: (sessionId: string) => ['answers', 'session', sessionId] as const,
}

export function sessionAnswersQueryOptions(sessionId: string) {
  return queryOptions({
    queryKey: answerKeys.session(sessionId),
    queryFn: ({ signal }) => listSessionAnswers(sessionId, signal),
  })
}
