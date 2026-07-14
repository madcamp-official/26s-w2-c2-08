import { apiClient, apiUrl } from '../../api/client'
import { apiErrorFromResponse, normalizeApiError } from '../../api/errors'

export async function getCurrentUser(signal?: AbortSignal) {
  try {
    const { data, error, response } = await apiClient.GET('/api/v1/me', {
      signal,
    })
    if (error) throw apiErrorFromResponse(response, error)
    return data
  } catch (error) {
    throw normalizeApiError(error)
  }
}

export async function logoutCurrentSession() {
  try {
    const { error, response } = await apiClient.POST('/api/v1/auth/logout')
    if (error) throw apiErrorFromResponse(response, error)
  } catch (error) {
    throw normalizeApiError(error)
  }
}

export function googleLoginUrl(returnTo: string): string {
  const url = new URL(apiUrl('/api/v1/auth/google/start'))
  url.searchParams.set('return_to', returnTo)
  return url.toString()
}
