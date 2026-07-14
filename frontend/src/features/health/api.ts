import { apiClient } from '../../api/client'
import { apiErrorFromResponse, normalizeApiError } from '../../api/errors'

export async function getApiHealth(signal?: AbortSignal) {
  try {
    const { data, error, response } = await apiClient.GET('/api/health', {
      signal,
    })

    if (error) {
      throw apiErrorFromResponse(response, error)
    }

    return data
  } catch (error) {
    throw normalizeApiError(error)
  }
}
