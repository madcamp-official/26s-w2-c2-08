import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'

import { server } from '../../test/server'
import { PersonalAiPanel } from './PersonalAiPanel'

const sessionId = '10000000-0000-0000-0000-000000000001'
const chatId = '20000000-0000-0000-0000-000000000001'
const jobId = '30000000-0000-0000-0000-000000000001'

function renderPanel(mode: 'LIVE' | 'REVIEW') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <PersonalAiPanel sessionId={sessionId} mode={mode} />
    </QueryClientProvider>,
  )
}

describe('PersonalAiPanel', () => {
  it('recovers a pending Chat turn from the stored USER response_job_id without streaming text', async () => {
    server.use(
      http.get('*/api/v1/sessions/:sessionId/chats', () =>
        HttpResponse.json({
          items: [
            {
              id: chatId,
              session_id: sessionId,
              mode: 'LIVE',
              created_at: '2026-07-14T00:00:00Z',
              updated_at: '2026-07-14T00:00:00Z',
            },
          ],
          next_cursor: null,
        }),
      ),
      http.get('*/api/v1/chats/:chatId/messages', () =>
        HttpResponse.json({
          items: [
            {
              id: 'message-user',
              chat_id: chatId,
              job_id: null,
              response_job_id: jobId,
              sequence: 1,
              role: 'USER',
              content: '방금 내용을 요약해줘',
              evidence: [],
              model_name: null,
              prompt_version: null,
              created_at: '2026-07-14T00:00:00Z',
            },
          ],
          next_cursor: null,
        }),
      ),
      http.get('*/api/v1/jobs/:jobId', () =>
        HttpResponse.json({
          id: jobId,
          session_id: sessionId,
          job_type: 'CHAT_RESPONSE',
          visibility: 'REQUESTER_ONLY',
          status: 'RUNNING',
          attempt: 1,
          version: 1,
          progress: { stage: 'GENERATING', percent: null },
          retryable: false,
          blocks_session_completion: false,
          clustering: null,
          error: null,
          target: {
            resource_type: 'CHAT_MESSAGE',
            resource_id: 'message-user',
            resource_url: `/api/v1/chat-messages/message-user`,
          },
          result: null,
          result_unavailable_reason: null,
          created_at: '2026-07-14T00:00:00Z',
          updated_at: '2026-07-14T00:00:00Z',
          started_at: '2026-07-14T00:00:00Z',
          finished_at: null,
        }),
      ),
    )
    renderPanel('LIVE')
    expect(await screen.findByText('방금 내용을 요약해줘')).toBeInTheDocument()
    expect(
      await screen.findByText(/AI가 저장된 결과를 준비/),
    ).toBeInTheDocument()
    expect(
      screen.queryByText('답변을 생성하고 있습니다…'),
    ).not.toBeInTheDocument()
  })

  it('renders REVIEW evidence links and keeps unavailable evidence disabled', async () => {
    server.use(
      http.get('*/api/v1/sessions/:sessionId/chats', () =>
        HttpResponse.json({
          items: [
            {
              id: chatId,
              session_id: sessionId,
              mode: 'REVIEW',
              created_at: '2026-07-14T00:00:00Z',
              updated_at: '2026-07-14T00:00:00Z',
            },
          ],
          next_cursor: null,
        }),
      ),
      http.get('*/api/v1/chats/:chatId/messages', () =>
        HttpResponse.json({
          items: [
            {
              id: 'message-ai',
              chat_id: chatId,
              job_id: jobId,
              response_job_id: null,
              sequence: 2,
              role: 'ASSISTANT',
              content: '복습할 핵심은 최단 경로의 조건입니다.',
              evidence: [
                {
                  source_kind: 'TRANSCRIPT',
                  label: '05:20 강의 내용',
                  link: `/api/v1/sessions/${sessionId}/transcript?transcript_version_id=version-1&start_sequence=1&end_sequence=2`,
                },
                { source_kind: 'QUESTION', label: '삭제된 질문', link: null },
              ],
              model_name: null,
              prompt_version: 'v1',
              created_at: '2026-07-14T00:00:01Z',
            },
          ],
          next_cursor: null,
        }),
      ),
    )
    renderPanel('REVIEW')
    expect(
      await screen.findByText('복습할 핵심은 최단 경로의 조건입니다.'),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: '05:20 강의 내용' }),
    ).toHaveAttribute('href', expect.stringContaining('/api/v1/sessions/'))
    expect(
      screen.getByText('삭제된 질문 · 더 이상 열 수 없음'),
    ).toHaveAttribute('aria-disabled', 'true')
  })
})
