import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { courseKeys } from '../courses/queries'
import { questionKeys } from '../questions/queries'
import { answerKeys } from '../answers/queries'

import { createRealtimeTicket } from './api'
import { RealtimeSessionClient } from './client'

interface UseSessionRealtimeOptions {
  sessionId: string
  courseId: string | undefined
  enabled: boolean
}

export function useSessionRealtime({
  sessionId,
  courseId,
  enabled,
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
    }
    const client = new RealtimeSessionClient({
      sessionId,
      createTicket: (resumeCursor) =>
        createRealtimeTicket({
          session_id: sessionId,
          scope: 'SESSION_EVENTS_READ',
          resume_cursor: resumeCursor,
        }),
      onEvent: invalidateCanonicalState,
      onResyncRequired: invalidateCanonicalState,
    })
    client.start()
    return () => client.stop()
  }, [courseId, enabled, queryClient, sessionId])
}
