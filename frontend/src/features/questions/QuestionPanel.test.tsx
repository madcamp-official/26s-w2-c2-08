import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'

import { AppProviders } from '../../app/providers'
import { server } from '../../test/server'
import { QuestionPanel } from './QuestionPanel'

const sessionId = '30000000-0000-0000-0000-000000000001'
const question = {
  id: '40000000-0000-0000-0000-000000000001',
  session_id: sessionId,
  content: '다익스트라 알고리즘에서 음수 가중치가 안 되는 이유가 궁금합니다.',
  status: 'OPEN' as const,
  version: 1,
  clustering_sequence: 1,
  reaction_count: 2,
  reacted_by_me: false,
  cluster_id: null,
  created_at: '2026-07-14T00:00:00Z',
  updated_at: '2026-07-14T00:00:00Z',
}

function renderPanel(student: boolean) {
  render(
    <AppProviders>
      <QuestionPanel sessionId={sessionId} student={student} />
    </AppProviders>,
  )
}

describe('QuestionPanel', () => {
  it('creates a normalized-length-safe anonymous Question and refreshes its list', async () => {
    let created = false
    server.use(
      http.get(`*/api/v1/sessions/${sessionId}/questions`, () =>
        HttpResponse.json({
          items: created ? [question] : [],
          next_cursor: null,
        }),
      ),
      http.post(
        `*/api/v1/sessions/${sessionId}/questions`,
        async ({ request }) => {
          expect(await request.json()).toEqual({ content: '  새 질문  ' })
          created = true
          return HttpResponse.json(
            {
              question: {
                ...question,
                id: '50000000-0000-0000-0000-000000000001',
                content: '새 질문',
              },
              clustering_state: {
                pending: true,
                requested_through_sequence: 2,
                applied_through_sequence: 0,
                current_revision: 0,
                current_generation: null,
                final_generation: null,
                active_job_id: '60000000-0000-0000-0000-000000000001',
                retry_job_id: null,
                last_job: {
                  id: '60000000-0000-0000-0000-000000000001',
                  attempt: 1,
                  status: 'PENDING',
                  mode: 'LIVE_INCREMENTAL',
                },
              },
            },
            { status: 201 },
          )
        },
      ),
    )
    renderPanel(true)

    fireEvent.change(await screen.findByLabelText('질문 작성'), {
      target: { value: '  새 질문  ' },
    })
    expect(screen.getByText('4/300')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '익명 질문 등록' }))

    expect(
      await screen.findByText('익명 질문을 등록했습니다.'),
    ).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.getByText(question.content)).toBeInTheDocument(),
    )
  })

  it('keeps student authoring and reaction controls out of a professor DOM', async () => {
    server.use(
      http.get(`*/api/v1/sessions/${sessionId}/questions`, () =>
        HttpResponse.json({ items: [question], next_cursor: null }),
      ),
    )
    renderPanel(false)

    expect(await screen.findByText(question.content)).toBeInTheDocument()
    expect(screen.queryByLabelText('질문 작성')).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: '익명 질문 등록' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: '나도 궁금해요' }),
    ).not.toBeInTheDocument()
  })
})
