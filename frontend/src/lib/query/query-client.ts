import { QueryClient } from '@tanstack/react-query'

import { ApiError } from '../../api/errors'

const nonRetryableStatuses = new Set([401, 403, 404, 409, 422])

export function shouldRetryQuery(
  failureCount: number,
  error: unknown,
): boolean {
  if (
    error instanceof ApiError &&
    error.status !== undefined &&
    nonRetryableStatuses.has(error.status)
  ) {
    return false
  }

  return failureCount < 1
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        retry: shouldRetryQuery,
      },
      mutations: {
        retry: false,
      },
    },
  })
}
