import { queryOptions } from '@tanstack/react-query'

import { getApiHealth } from './api'

export const healthQueryOptions = queryOptions({
  queryKey: ['health', 'api'] as const,
  queryFn: ({ signal }) => getApiHealth(signal),
})
