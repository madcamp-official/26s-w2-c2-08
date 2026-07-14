import { fireEvent, render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { AppProviders } from '../../app/providers'
import { appRoutes } from '../../app/router'
import { server } from '../../test/server'

const courseId = '10000000-0000-0000-0000-000000000001'
const sessionId = '20000000-0000-0000-0000-000000000001'
const versionId = '30000000-0000-0000-0000-000000000001'
const session = {
  id: sessionId,
  title: '그래프 탐색',
  lecture_date: '2026-07-13',
  status: 'COMPLETED' as const,
  started_at: '2026-07-13T06:00:00Z',
}

function version(source: 'LIVE' | 'RECORDING', status = 'FINALIZED') {
  return {
    id: versionId,
    session_id: sessionId,
    source,
    status,
    version: 2,
    last_sequence: 1,
    is_canonical: true,
    recording_id: source === 'RECORDING' ? 'recording-1' : null,
    created_by_job_id: source === 'RECORDING' ? 'job-1' : null,
    created_by_job_attempt: source === 'RECORDING' ? 1 : null,
    finalized_at: '2026-07-13T07:00:00Z',
    failed_at: null,
    created_at: '2026-07-13T06:00:00Z',
    updated_at: '2026-07-13T07:00:00Z',
  }
}

function transcriptItem(source: 'LIVE' | 'RECORDING' = 'RECORDING') {
  const selected = version(source)
  return {
    session,
    transcript: {
      state: {
        session_id: sessionId,
        status: 'FINALIZED',
        current_version: selected,
        canonical_version_id: versionId,
        canonical_version: selected,
        updated_at: '2026-07-13T07:00:00Z',
      },
      selected_version_id: versionId,
      segment_count: 1,
      gap_count: 1,
      timeline_url: `/api/v1/sessions/${sessionId}/transcript?transcript_version_id=${versionId}`,
      versions_url: `/api/v1/sessions/${sessionId}/transcript/versions`,
    },
  }
}

function authenticate() {
  server.use(
    http.get('*/api/v1/me', () =>
      HttpResponse.json({
        id: '00000000-0000-0000-0000-000000000001',
        display_name: '김도현',
        email: 'dohyun@example.test',
        avatar_url: null,
      }),
    ),
    http.get('*/api/v1/courses/:courseId', () =>
      HttpResponse.json({
        id: courseId,
        title: '알고리즘',
        semester: '2026 여름학기',
        role: 'STUDENT',
        current_session: null,
        created_at: '2026-07-01T00:00:00Z',
      }),
    ),
  )
}

function renderPage() {
  const router = createMemoryRouter(appRoutes, {
    initialEntries: [`/courses/${courseId}/transcripts`],
  })
  render(
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>,
  )
}

describe('Course Transcript archive', () => {
  it('loads a class timeline only after the user expands it', async () => {
    authenticate()
    let timelineRequests = 0
    server.use(
      http.get('*/api/v1/courses/:courseId/transcripts', () =>
        HttpResponse.json({ items: [transcriptItem()], next_cursor: null }),
      ),
      http.get('*/api/v1/sessions/:sessionId/transcript', () => {
        timelineRequests += 1
        return HttpResponse.json({
          transcript_version_id: versionId,
          segments: [
            {
              id: 'segment-1',
              session_id: sessionId,
              transcript_version_id: versionId,
              item_type: 'SEGMENT',
              sequence: 1,
              start_ms: 1_000,
              end_ms: 4_000,
              recording_start_ms: 900,
              recording_end_ms: 3_900,
              text: '그래프 탐색을 시작합니다.',
              created_at: '2026-07-13T06:00:01Z',
            },
          ],
          gaps: [
            {
              id: 'gap-1',
              session_id: sessionId,
              transcript_version_id: versionId,
              item_type: 'GAP',
              start_ms: 5_000,
              end_ms: 6_000,
              reason: 'AUDIO_MISSING',
              created_at: '2026-07-13T06:00:05Z',
            },
          ],
          next_cursor: null,
        })
      }),
    )
    renderPage()

    expect(await screen.findByText('HQ canonical')).toBeInTheDocument()
    expect(timelineRequests).toBe(0)
    fireEvent.click(screen.getByRole('button', { name: 'Transcript 펼치기' }))
    expect(
      await screen.findByText('그래프 탐색을 시작합니다.'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('0:06까지 음성이 누락된 구간입니다.'),
    ).toBeInTheDocument()
    expect(timelineRequests).toBe(1)
  })

  it('distinguishes an HQ failure that keeps a LIVE canonical transcript', async () => {
    authenticate()
    const live = version('LIVE')
    const failedRecording = {
      ...version('RECORDING', 'FAILED'),
      id: '30000000-0000-0000-0000-000000000002',
      is_canonical: false,
      last_sequence: 0,
      finalized_at: null,
      failed_at: '2026-07-13T07:00:00Z',
    }
    server.use(
      http.get('*/api/v1/courses/:courseId/transcripts', () =>
        HttpResponse.json({
          items: [
            {
              session,
              transcript: {
                state: {
                  session_id: sessionId,
                  status: 'FAILED',
                  current_version: failedRecording,
                  canonical_version_id: live.id,
                  canonical_version: live,
                  updated_at: '2026-07-13T07:00:00Z',
                },
                selected_version_id: live.id,
                segment_count: 1,
                gap_count: 0,
                timeline_url: `/api/v1/sessions/${sessionId}/transcript?transcript_version_id=${live.id}`,
                versions_url: `/api/v1/sessions/${sessionId}/transcript/versions`,
              },
            },
          ],
          next_cursor: null,
        }),
      ),
    )
    renderPage()

    expect(
      await screen.findByText('HQ 실패 · LIVE final 유지'),
    ).toBeInTheDocument()
    expect(screen.queryByText('HQ canonical')).not.toBeInTheDocument()
  })

  it('keeps the workspace around an empty Transcript archive', async () => {
    authenticate()
    server.use(
      http.get('*/api/v1/courses/:courseId/transcripts', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    )
    renderPage()

    expect(
      await screen.findByRole('heading', {
        name: '표시할 Transcript가 없습니다',
      }),
    ).toBeInTheDocument()
    expect(screen.getByText('LIVE CLASS')).toBeInTheDocument()
  })
})
