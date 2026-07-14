import createClient from 'openapi-fetch'

import type { paths } from './generated/schema'

const apiBaseUrl = (
  import.meta.env.VITE_API_BASE_URL || window.location.origin
).replace(/\/$/, '')

export const apiClient = createClient<paths>({
  baseUrl: apiBaseUrl,
  credentials: 'include',
  fetch: (request) => globalThis.fetch(request),
  headers: {
    Accept: 'application/json',
  },
})
