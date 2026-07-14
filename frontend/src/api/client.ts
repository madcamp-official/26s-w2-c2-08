import createClient from 'openapi-fetch'

import type { paths } from './generated/schema'

function resolveApiOrigin(configuredBaseUrl?: string): string {
  const baseUrl = configuredBaseUrl?.trim() || window.location.origin
  return new URL(baseUrl, window.location.origin).origin
}

const apiBaseUrl = resolveApiOrigin(import.meta.env.VITE_API_BASE_URL)

export function apiUrl(path: string): string {
  return new URL(path, apiBaseUrl).toString()
}

export const apiClient = createClient<paths>({
  baseUrl: apiBaseUrl,
  credentials: 'include',
  fetch: (request) => globalThis.fetch(request),
  headers: {
    Accept: 'application/json',
  },
})
