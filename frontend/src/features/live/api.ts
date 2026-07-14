import type { components } from '../../api/generated/schema'
import { apiClient } from '../../api/client'
import { apiErrorFromResponse, normalizeApiError } from '../../api/errors'

export type TranscriptTimeline = components['schemas']['TranscriptTimelinePage']

export async function getLiveTranscript(
  sessionId: string,
  signal?: AbortSignal,
) {
  try {
    const { data, error, response } = await apiClient.GET(
      '/api/v1/sessions/{session_id}/transcript',
      {
        params: { path: { session_id: sessionId }, query: { limit: 200 } },
        signal,
      },
    )
    if (error) throw apiErrorFromResponse(response, error)
    return data
  } catch (error) {
    throw normalizeApiError(error)
  }
}
