import { QueryClient } from '@tanstack/react-query'
import { beforeEach, describe, expect, it } from 'vitest'

import type { LectureSession } from '../courses/api'
import { courseKeys } from '../courses/queries'
import { liveSummaryJobStorageKey } from '../personal-ai/client-state'
import { personalAiKeys } from '../personal-ai/queries'
import type { RealtimeEvent } from './client'
import { applySessionUpdatedEvent } from './session-event'

const sessionId = '10000000-0000-0000-0000-000000000001'
const otherSessionId = '10000000-0000-0000-0000-000000000002'

function session(
  id: string,
  status: LectureSession['status'],
  version: number,
): LectureSession {
  return {
    id,
    course_id: '20000000-0000-0000-0000-000000000001',
    title: '그래프 탐색',
    lecture_date: '2026-07-15',
    status,
    started_at: '2026-07-15T00:00:00Z',
    ended_at: null,
    completed_at: null,
    canonical_transcript_version_id: null,
    version,
    created_at: '2026-07-15T00:00:00Z',
    updated_at: '2026-07-15T00:00:00Z',
  }
}

function updatedEvent(data: LectureSession, resourceVersion = data.version) {
  return {
    event_id: crypto.randomUUID(),
    type: 'session.updated',
    session_id: data.id,
    cursor: 'cursor-1',
    resource_version: resourceVersion,
    data,
  } satisfies RealtimeEvent
}

describe('applySessionUpdatedEvent', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient()
    window.sessionStorage.clear()
  })

  it('applies a newer PROCESSING projection after purging only that session AI state', () => {
    queryClient.setQueryData(
      courseKeys.session(sessionId),
      session(sessionId, 'LIVE', 1),
    )
    queryClient.setQueryData(personalAiKeys.summaries(sessionId), {
      items: [{ id: 'summary-live' }],
    })
    queryClient.setQueryData(personalAiKeys.summaries(otherSessionId), {
      items: [{ id: 'summary-other' }],
    })
    window.sessionStorage.setItem(
      liveSummaryJobStorageKey(sessionId),
      'job-live',
    )

    const applied = applySessionUpdatedEvent(
      queryClient,
      sessionId,
      updatedEvent(session(sessionId, 'PROCESSING', 2)),
    )

    expect(applied).toBe(true)
    expect(
      queryClient.getQueryData<LectureSession>(courseKeys.session(sessionId))
        ?.status,
    ).toBe('PROCESSING')
    expect(
      queryClient.getQueryData(personalAiKeys.summaries(sessionId)),
    ).toBeUndefined()
    expect(
      queryClient.getQueryData(personalAiKeys.summaries(otherSessionId)),
    ).toBeDefined()
    expect(
      window.sessionStorage.getItem(liveSummaryJobStorageKey(sessionId)),
    ).toBeNull()
  })

  it('ignores stale or resource-version-mismatched events', () => {
    queryClient.setQueryData(
      courseKeys.session(sessionId),
      session(sessionId, 'LIVE', 3),
    )

    expect(
      applySessionUpdatedEvent(
        queryClient,
        sessionId,
        updatedEvent(session(sessionId, 'PROCESSING', 2)),
      ),
    ).toBe(false)
    expect(
      applySessionUpdatedEvent(
        queryClient,
        sessionId,
        updatedEvent(session(sessionId, 'PROCESSING', 4), 3),
      ),
    ).toBe(false)
    expect(
      queryClient.getQueryData<LectureSession>(courseKeys.session(sessionId))
        ?.status,
    ).toBe('LIVE')
  })
})
