import { queryOptions } from '@tanstack/react-query'

import { listSessionMaterials } from './api'

export const materialKeys = {
  all: ['materials'] as const,
  session: (sessionId: string) => ['materials', 'session', sessionId] as const,
}

export function sessionMaterialsQueryOptions(sessionId: string) {
  return queryOptions({
    queryKey: materialKeys.session(sessionId),
    queryFn: ({ signal }) => listSessionMaterials(sessionId, signal),
  })
}
