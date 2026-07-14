import { queryOptions } from '@tanstack/react-query'

import { getCurrentUser } from './api'

export const currentUserQueryKey = ['auth', 'me'] as const

export const currentUserQueryOptions = queryOptions({
  queryKey: currentUserQueryKey,
  queryFn: ({ signal }) => getCurrentUser(signal),
})
