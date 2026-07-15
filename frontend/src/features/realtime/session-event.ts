import type { QueryClient } from '@tanstack/react-query'

import type { LectureSession } from '../courses/api'
import { courseKeys } from '../courses/queries'
import { clearAudioPublisherClientState } from '../live/audio-publisher'
import { purgeLivePersonalAiClientState } from '../personal-ai/client-state'
import type { RealtimeEvent } from './client'

const sessionStatuses = new Set(['READY', 'LIVE', 'PROCESSING', 'COMPLETED'])

function sessionFromEvent(
  event: RealtimeEvent,
  expectedSessionId: string,
): LectureSession | null {
  if (event.type !== 'session.updated') return null
  const value = event.data
  if (!value || typeof value !== 'object') return null
  const data = value as Record<string, unknown>
  if (
    data.id !== expectedSessionId ||
    typeof data.course_id !== 'string' ||
    typeof data.version !== 'number' ||
    !Number.isSafeInteger(data.version) ||
    !sessionStatuses.has(String(data.status)) ||
    event.resource_version !== data.version
  ) {
    return null
  }
  return data as unknown as LectureSession
}

/** Apply only a complete, newer member-visible Session projection. */
export function applySessionUpdatedEvent(
  queryClient: QueryClient,
  sessionId: string,
  event: RealtimeEvent,
) {
  const incoming = sessionFromEvent(event, sessionId)
  if (!incoming) return false
  const current = queryClient.getQueryData<LectureSession>(
    courseKeys.session(sessionId),
  )
  if (
    current &&
    (current.course_id !== incoming.course_id ||
      current.version >= incoming.version)
  ) {
    return false
  }
  if (incoming.status !== 'LIVE') {
    clearAudioPublisherClientState(sessionId)
    purgeLivePersonalAiClientState(queryClient, sessionId)
  }
  queryClient.setQueryData(courseKeys.session(sessionId), incoming)
  return true
}
