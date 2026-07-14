import type { components } from '../../api/generated/schema'
import { apiClient } from '../../api/client'
import { apiErrorFromResponse, normalizeApiError } from '../../api/errors'

export type RealtimeTicketInput =
  components['schemas']['RealtimeTicketCreateRequest']
export type RealtimeTicket = components['schemas']['RealtimeTicket']

export async function createRealtimeTicket(input: RealtimeTicketInput) {
  try {
    const { data, error, response } = await apiClient.POST(
      '/api/v1/realtime-tickets',
      { body: input },
    )
    if (error) throw apiErrorFromResponse(response, error)
    return data
  } catch (error) {
    throw normalizeApiError(error)
  }
}
