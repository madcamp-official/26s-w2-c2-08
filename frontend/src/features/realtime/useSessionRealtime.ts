import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { courseKeys } from '../courses/queries'
import { questionKeys } from '../questions/queries'
import { answerKeys } from '../answers/queries'
import { materialKeys } from '../materials/queries'

import { createRealtimeTicket } from './api'
import {
  RealtimeSessionClient,
  type RealtimeConnectionState,
  type RealtimeEvent,
} from './client'

interface UseSessionRealtimeOptions {
  sessionId: string
  courseId: string | undefined
  enabled: boolean
  onEvent?: (event: RealtimeEvent) => void
  onResyncRequired?: () => void
  onConnectionState?: (state: RealtimeConnectionState) => void
}

export function useSessionRealtime({
  sessionId,
  courseId,
  enabled,
  onEvent,
  onResyncRequired,
  onConnectionState,
}: UseSessionRealtimeOptions) {
  const queryClient = useQueryClient()

  useEffect(() => {
    if (!enabled || !sessionId || !courseId || typeof WebSocket === 'undefined')
      return

    const invalidateCanonicalState = () => {
      void queryClient.invalidateQueries({
        queryKey: courseKeys.session(sessionId),
      })
      void queryClient.invalidateQueries({
        queryKey: courseKeys.sessions(courseId),
      })
      void queryClient.invalidateQueries({
        queryKey: courseKeys.detail(courseId),
      })
      void queryClient.invalidateQueries({
        queryKey: questionKeys.session(sessionId),
      })
      void queryClient.invalidateQueries({
        queryKey: answerKeys.session(sessionId),
      })
      void queryClient.invalidateQueries({
        queryKey: materialKeys.session(sessionId),
      })
      void queryClient.invalidateQueries({
        queryKey: materialKeys.jobs(sessionId),
      })
    }
    const client = new RealtimeSessionClient({
      sessionId,
      createTicket: (resumeCursor) =>
        createRealtimeTicket({
          session_id: sessionId,
          scope: 'SESSION_EVENTS_READ',
          resume_cursor: resumeCursor,
        }),
      onEvent: (event) => {
        onEvent?.(event)
        // partial STT is intentionally transient and has no REST representation.
        // Refetching on it would erase a newer in-memory revision before its final arrives.
        if (
          event.type !== 'transcript.partial' &&
          event.type !== 'transcript.final' &&
          event.type !== 'transcript.status'
        ) {
          invalidateCanonicalState()
        }
      },
      onResyncRequired: () => {
        onResyncRequired?.()
        invalidateCanonicalState()
      },
      onConnectionState,
    })
    client.start()
    return () => client.stop()
  }, [
    courseId,
    enabled,
    onConnectionState,
    onEvent,
    onResyncRequired,
    queryClient,
    sessionId,
  ])
}
