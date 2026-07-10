export interface HealthResponse {
  status?: string
  [key: string]: unknown
}

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? '/api').replace(
  /\/$/,
  '',
)

export async function fetchHealth(
  signal?: AbortSignal,
): Promise<HealthResponse> {
  const response = await fetch(`${apiBaseUrl}/health`, {
    headers: { Accept: 'application/json' },
    signal,
  })

  if (!response.ok) {
    throw new Error(`Health check failed with status ${response.status}`)
  }

  const body: unknown = await response.json()

  if (typeof body !== 'object' || body === null || Array.isArray(body)) {
    return {}
  }

  return body as HealthResponse
}
