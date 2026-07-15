import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'

import { server } from '../../test/server'
import { courseKeys } from '../courses/queries'
import { PersonalAiPanel } from './PersonalAiPanel'
import { personalAiKeys } from './queries'

const sessionId = '10000000-0000-0000-0000-000000000001'
const chatId = '20000000-0000-0000-0000-000000000001'
const jobId = '30000000-0000-0000-0000-000000000001'

function renderPanel(mode: 'LIVE' | 'REVIEW') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  client.setQueryData(courseKeys.session(sessionId), { status: 'LIVE' })
  render(
    <QueryClientProvider client={client}>
      <PersonalAiPanel sessionId={sessionId} mode={mode} />
    </QueryClientProvider>,
  )
  return client
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

  it('accepts consecutive REVIEW questions in the same chat', async () => {
    const submitted: string[] = []
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
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.post('*/api/v1/chats/:chatId/messages', async ({ request }) => {
        const body = (await request.json()) as { content: string }
        submitted.push(body.content)
        const turn = submitted.length
        return HttpResponse.json({
          user_message: {
            id: `message-user-${turn}`,
            chat_id: chatId,
            job_id: null,
            response_job_id: `job-${turn}`,
            sequence: turn * 2 - 1,
            role: 'USER',
            content: body.content,
            evidence: [],
            model_name: null,
            prompt_version: null,
            created_at: `2026-07-14T00:00:0${turn}Z`,
          },
          job: {
            id: `job-${turn}`,
            session_id: sessionId,
            job_type: 'CHAT_RESPONSE',
            visibility: 'REQUESTER_ONLY',
            status: 'PENDING',
            attempt: 1,
            version: 1,
            progress: null,
            retryable: false,
            blocks_session_completion: false,
            clustering: null,
            error: null,
            target: null,
            result: null,
            result_unavailable_reason: null,
            created_at: `2026-07-14T00:00:0${turn}Z`,
            updated_at: `2026-07-14T00:00:0${turn}Z`,
            started_at: null,
            finished_at: null,
          },
        })
      }),
      http.get('*/api/v1/jobs/:jobId', ({ params }) =>
        HttpResponse.json({
          id: params.jobId,
          session_id: sessionId,
          job_type: 'CHAT_RESPONSE',
          visibility: 'REQUESTER_ONLY',
          status: 'SUCCEEDED',
          attempt: 1,
          version: 2,
          progress: null,
          retryable: false,
          blocks_session_completion: false,
          clustering: null,
          error: null,
          target: null,
          result: null,
          result_unavailable_reason: null,
          created_at: '2026-07-14T00:00:01Z',
          updated_at: '2026-07-14T00:00:02Z',
          started_at: '2026-07-14T00:00:01Z',
          finished_at: '2026-07-14T00:00:02Z',
        }),
      ),
    )
    renderPanel('REVIEW')
    const input = await screen.findByLabelText('AI에게 물어보기')

    fireEvent.change(input, { target: { value: '첫 번째 질문' } })
    fireEvent.click(screen.getByRole('button', { name: '질문 보내기' }))
    await waitFor(() => expect(input).toHaveValue(''))

    fireEvent.change(input, { target: { value: '두 번째 질문' } })
    fireEvent.click(screen.getByRole('button', { name: '질문 보내기' }))

    await waitFor(() =>
      expect(submitted).toEqual(['첫 번째 질문', '두 번째 질문']),
    )
    expect(input).toHaveValue('')
  })

  it('refreshes a succeeded Chat job only once while its USER message remains', async () => {
    let messageRequests = 0
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
      http.get('*/api/v1/chats/:chatId/messages', () => {
        messageRequests += 1
        return HttpResponse.json({
          items: [
            {
              id: 'message-user',
              chat_id: chatId,
              job_id: null,
              response_job_id: jobId,
              sequence: 1,
              role: 'USER',
              content: '한 번만 새로고침해줘',
              evidence: [],
              model_name: null,
              prompt_version: null,
              created_at: '2026-07-14T00:00:00Z',
            },
          ],
          next_cursor: null,
        })
      }),
      http.get('*/api/v1/jobs/:jobId', () =>
        HttpResponse.json({
          id: jobId,
          session_id: sessionId,
          job_type: 'CHAT_RESPONSE',
          visibility: 'REQUESTER_ONLY',
          status: 'SUCCEEDED',
          attempt: 1,
          version: 2,
          progress: null,
          retryable: false,
          blocks_session_completion: false,
          clustering: null,
          error: null,
          target: {
            resource_type: 'CHAT_MESSAGE',
            resource_id: 'message-user',
            resource_url: `/api/v1/chat-messages/message-user`,
          },
          result: {
            resource_type: 'CHAT_MESSAGE',
            resource_id: 'message-assistant',
            resource_url: `/api/v1/chat-messages/message-assistant`,
          },
          result_unavailable_reason: null,
          created_at: '2026-07-14T00:00:00Z',
          updated_at: '2026-07-14T00:00:02Z',
          started_at: '2026-07-14T00:00:00Z',
          finished_at: '2026-07-14T00:00:02Z',
        }),
      ),
    )

    renderPanel('LIVE')
    expect(await screen.findByText('한 번만 새로고침해줘')).toBeInTheDocument()
    await waitFor(() => expect(messageRequests).toBe(2))
    await new Promise((resolve) => window.setTimeout(resolve, 100))
    expect(messageRequests).toBe(2)
  })

  it('stores an accepted USER turn under its response chat and preserves it across a capped refetch', async () => {
    const otherSessionId = '10000000-0000-0000-0000-000000000099'
    const userMessage = {
      id: 'message-accepted',
      chat_id: chatId,
      job_id: null,
      response_job_id: jobId,
      sequence: 101,
      role: 'USER',
      content: '최신 질문을 보존해줘',
      evidence: [],
      model_name: null,
      prompt_version: null,
      created_at: '2026-07-15T00:00:00Z',
    }
    const acceptedJob = {
      id: jobId,
      session_id: sessionId,
      job_type: 'CHAT_RESPONSE',
      visibility: 'REQUESTER_ONLY',
      status: 'PENDING',
      attempt: 1,
      version: 1,
      progress: null,
      retryable: false,
      blocks_session_completion: false,
      clustering: null,
      error: null,
      target: {
        resource_type: 'CHAT_MESSAGE',
        resource_id: userMessage.id,
        resource_url: `/api/v1/chat-messages/${userMessage.id}`,
      },
      result: null,
      result_unavailable_reason: null,
      created_at: '2026-07-15T00:00:00Z',
      updated_at: '2026-07-15T00:00:00Z',
      started_at: null,
      finished_at: null,
    }
    let messageRequests = 0
    let acceptTurn: ((response: Response) => void) | undefined
    const acceptedResponse = new Promise<Response>((resolve) => {
      acceptTurn = resolve
    })
    server.use(
      http.get('*/api/v1/sessions/:sessionId/summaries', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
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
      http.get('*/api/v1/chats/:chatId/messages', () => {
        messageRequests += 1
        return HttpResponse.json({
          items: [
            {
              id: 'message-oldest',
              chat_id: chatId,
              job_id: null,
              response_job_id: null,
              sequence: 1,
              role: 'USER',
              content: '서버의 오래된 첫 메시지',
              evidence: [],
              model_name: null,
              prompt_version: null,
              created_at: '2026-07-14T00:00:00Z',
            },
          ],
          next_cursor: null,
        })
      }),
      http.post('*/api/v1/chats/:chatId/messages', async ({ request }) => {
        expect(request.headers.get('Idempotency-Key')).toBeTruthy()
        expect(await request.json()).toEqual({ content: userMessage.content })
        return acceptedResponse
      }),
      http.get('*/api/v1/jobs/:jobId', () =>
        HttpResponse.json({
          ...acceptedJob,
          status: 'RUNNING',
          progress: { stage: 'GENERATING', percent: null },
          started_at: '2026-07-15T00:00:01Z',
        }),
      ),
    )
    const client = renderPanel('LIVE')
    client.setQueryData(personalAiKeys.messages(otherSessionId, chatId), {
      items: [{ ...userMessage, id: 'other-session-message' }],
      next_cursor: null,
    })

    fireEvent.change(await screen.findByLabelText('AI에게 물어보기'), {
      target: { value: userMessage.content },
    })
    fireEvent.click(screen.getByRole('button', { name: '질문 보내기' }))
    await waitFor(() => expect(acceptTurn).toBeTypeOf('function'))
    client.setQueryData(personalAiKeys.chats(sessionId), {
      items: [],
      next_cursor: null,
    })
    acceptTurn?.(
      HttpResponse.json({ user_message: userMessage, job: acceptedJob }),
    )

    await waitFor(() =>
      expect(
        client.getQueryData<{ items: Array<{ id: string }> }>(
          personalAiKeys.messages(sessionId, chatId),
        )?.items,
      ).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ id: userMessage.id }),
        ]),
      ),
    )
    client.setQueryData(personalAiKeys.chats(sessionId), {
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
    })
    await screen.findByLabelText('AI에게 물어보기')
    await client.refetchQueries({
      queryKey: personalAiKeys.messages(sessionId, chatId),
      type: 'active',
    })

    await waitFor(() => expect(messageRequests).toBeGreaterThanOrEqual(2))
    expect(
      client.getQueryData<{ items: Array<{ id: string }> }>(
        personalAiKeys.messages(sessionId, chatId),
      )?.items,
    ).toEqual(
      expect.arrayContaining([expect.objectContaining({ id: userMessage.id })]),
    )
    expect(
      client.getQueryData<{ items: Array<{ id: string }> }>(
        personalAiKeys.messages(otherSessionId, chatId),
      )?.items,
    ).toEqual([expect.objectContaining({ id: 'other-session-message' })])
    const cachedJob = client.getQueryData<{ id: string; status: string }>(
      personalAiKeys.job(sessionId, jobId),
    )
    expect(cachedJob?.id).toBe(jobId)
    expect(['PENDING', 'RUNNING']).toContain(cachedJob?.status)
  })
})
