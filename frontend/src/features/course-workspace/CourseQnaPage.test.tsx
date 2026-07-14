import { fireEvent, render, screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { AppProviders } from '../../app/providers'
import { appRoutes } from '../../app/router'
import { server } from '../../test/server'

const courseId = '10000000-0000-0000-0000-000000000001'
const sessionId = '20000000-0000-0000-0000-000000000001'
const session = {
  id: sessionId,
  title: '그래프 탐색',
  lecture_date: '2026-07-13',
  status: 'COMPLETED' as const,
  started_at: '2026-07-13T06:00:00Z',
}

function completedAnswer(id: string, textContent: string | null) {
  return {
    id,
    session_id: sessionId,
    answer_type: textContent ? ('TEXT' as const) : ('VOICE' as const),
    status: 'COMPLETED' as const,
    version: 1,
    target: textContent
      ? {
          type: 'STUDENT_QUESTION' as const,
          question_id: '30000000-0000-0000-0000-000000000001',
        }
      : {
          type: 'AI_REPRESENTATIVE_QUESTION' as const,
          representative_question_id: '40000000-0000-0000-0000-000000000001',
        },
    target_text_snapshot: '왜 이 방식이 필요한가요?',
    text_content: textContent,
    source_transcript_version_id: textContent ? null : 'version-live',
    canonical_transcript_mapping: null,
    organization_state: {
      status: 'NOT_APPLICABLE' as const,
      job_id: null,
      attempt: null,
      retryable: false,
      organization: null,
    },
    capture_started_after_sequence: textContent ? null : 0,
    start_sequence: textContent ? null : 1,
    end_sequence: textContent ? null : 2,
    started_at: '2026-07-13T06:20:00Z',
    completed_at: '2026-07-13T06:25:00Z',
    updated_at: '2026-07-13T06:25:00Z',
  }
}

function question(id: string, content: string) {
  return {
    id,
    session_id: sessionId,
    content,
    status: 'OPEN' as const,
    version: 1,
    clustering_sequence: 1,
    reaction_count: 3,
    reacted_by_me: false,
    cluster_id: null,
    created_at: '2026-07-13T06:10:00Z',
    updated_at: '2026-07-13T06:10:00Z',
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
    initialEntries: [`/courses/${courseId}/qna`],
  })
  render(
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>,
  )
}

describe('Course Q&A archive', () => {
  it('shows unanswered anonymous questions and answered representative questions read-only', async () => {
    authenticate()
    const anonymous = question(
      '30000000-0000-0000-0000-000000000001',
      '왜 방문 배열이 필요한가요?',
    )
    const representativeAnswer = completedAnswer(
      '50000000-0000-0000-0000-000000000001',
      null,
    )
    server.use(
      http.get('*/api/v1/courses/:courseId/qna', () =>
        HttpResponse.json({
          items: [
            {
              target_type: 'STUDENT_QUESTION',
              session,
              question: anonymous,
              target_text_snapshot: anonymous.content,
              answer: null,
              record_url: `/sessions/${sessionId}`,
              occurred_at: anonymous.created_at,
            },
            {
              target_type: 'AI_REPRESENTATIVE_QUESTION',
              session,
              representative_question_id:
                '40000000-0000-0000-0000-000000000001',
              target_text_snapshot: '비슷한 질문을 어떻게 묶나요?',
              answer: representativeAnswer,
              record_url: `/sessions/${sessionId}`,
              occurred_at: representativeAnswer.completed_at,
            },
          ],
          next_cursor: null,
        }),
      ),
    )
    renderPage()

    expect(
      await screen.findByRole('heading', { name: '모든 class의 질의응답' }),
    ).toBeInTheDocument()
    const unanswered = screen.getByText(anonymous.content).closest('li')
    expect(unanswered).not.toBeNull()
    expect(
      within(unanswered!).getByText('아직 답변이 없습니다.'),
    ).toBeInTheDocument()
    expect(within(unanswered!).getByText(/작성자 비공개/)).toBeInTheDocument()
    expect(screen.getByText('AI 대표질문')).toBeInTheDocument()
    expect(screen.getByText(/완료된 음성 Answer/)).toBeInTheDocument()
    expect(
      screen.getAllByRole('link', { name: 'class 기록 보기' })[0],
    ).toHaveAttribute('href', `/sessions/${sessionId}`)
    expect(
      screen.queryByRole('button', { name: /수정|철회|재시도/ }),
    ).not.toBeInTheDocument()
    expect(screen.queryByText('dohyun@example.test')).not.toBeInTheDocument()
  })

  it('keeps the first page when appending the next cursor page', async () => {
    authenticate()
    server.use(
      http.get('*/api/v1/courses/:courseId/qna', ({ request }) => {
        const cursor = new URL(request.url).searchParams.get('cursor')
        const current = question(
          cursor
            ? '30000000-0000-0000-0000-000000000003'
            : '30000000-0000-0000-0000-000000000002',
          cursor ? '두 번째 질문' : '첫 번째 질문',
        )
        return HttpResponse.json({
          items: [
            {
              target_type: 'STUDENT_QUESTION',
              session,
              question: current,
              target_text_snapshot: current.content,
              answer: completedAnswer(
                `50000000-0000-0000-0000-00000000000${cursor ? '3' : '2'}`,
                `${current.content} 답변`,
              ),
              record_url: `/sessions/${sessionId}`,
              occurred_at: current.created_at,
            },
          ],
          next_cursor: cursor ? null : 'next-qna',
        })
      }),
    )
    renderPage()

    expect(await screen.findByText('첫 번째 질문')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '질의응답 더 보기' }))
    expect(await screen.findByText('두 번째 질문')).toBeInTheDocument()
    expect(screen.getByText('첫 번째 질문')).toBeInTheDocument()
  })

  it('keeps workspace navigation around an empty archive', async () => {
    authenticate()
    server.use(
      http.get('*/api/v1/courses/:courseId/qna', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    )
    renderPage()

    expect(
      await screen.findByRole('heading', {
        name: '표시할 질의응답이 없습니다',
      }),
    ).toBeInTheDocument()
    expect(screen.getByText('LIVE CLASS')).toBeInTheDocument()
    expect(
      screen.getByRole('navigation', { name: 'Course 기록 탐색' }),
    ).toBeInTheDocument()
  })
})
