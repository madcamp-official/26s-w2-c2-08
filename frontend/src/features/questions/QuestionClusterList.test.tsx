import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'

import { AppProviders } from '../../app/providers'
import { server } from '../../test/server'
import { QuestionClusterList } from './QuestionClusterList'

const sessionId = '30000000-0000-0000-0000-000000000001'
const clusterId = '40000000-0000-0000-0000-000000000001'

describe('QuestionClusterList', () => {
  it('shows representative questions and cluster members as lists', async () => {
    server.use(
      http.get(`*/api/v1/sessions/${sessionId}/question-clusters`, () =>
        HttpResponse.json({
          scope: 'CURRENT',
          generation: 3,
          next_cursor: null,
          clustering_state: {
            pending: false,
            requested_through_sequence: 4,
            applied_through_sequence: 4,
            current_revision: 3,
            current_generation: 3,
            final_generation: null,
            active_job_id: null,
            retry_job_id: null,
            last_job: {
              id: '50000000-0000-0000-0000-000000000001',
              attempt: 1,
              status: 'SUCCEEDED',
              mode: 'LIVE_INCREMENTAL',
            },
          },
          items: [
            {
              id: clusterId,
              session_id: sessionId,
              generation: 3,
              revision: 3,
              ordinal: 0,
              member_count: 1,
              members_url: `/api/v1/sessions/${sessionId}/question-clusters/${clusterId}/members`,
              is_final: false,
              finalized_at: null,
              created_by_job_id: '50000000-0000-0000-0000-000000000001',
              created_by_job_attempt: 1,
              representative_question: {
                id: '60000000-0000-0000-0000-000000000001',
                session_id: sessionId,
                content: '네트워크 관련 질문',
                lifecycle_status: 'ACTIVE',
                status: 'OPEN',
                version: 1,
                answer_id: null,
                created_by_job_id: '50000000-0000-0000-0000-000000000001',
                created_by_job_attempt: 1,
                created_in_generation: 3,
                created_at: '2026-07-14T00:00:00Z',
              },
            },
          ],
        }),
      ),
      http.get(
        `*/api/v1/sessions/${sessionId}/question-clusters/${clusterId}/members`,
        () =>
          HttpResponse.json({
            cluster_id: clusterId,
            next_cursor: null,
            items: [
              {
                source_kind: 'STUDENT_QUESTION',
                ordinal: 0,
                question: {
                  id: '70000000-0000-0000-0000-000000000001',
                  session_id: sessionId,
                  content: '패킷이 무엇인가요?',
                  status: 'OPEN',
                  version: 1,
                  clustering_sequence: 4,
                  reaction_count: 0,
                  reacted_by_me: false,
                  cluster_id: clusterId,
                  created_at: '2026-07-14T00:00:00Z',
                  updated_at: '2026-07-14T00:00:00Z',
                },
              },
            ],
          }),
      ),
    )

    render(
      <AppProviders>
        <QuestionClusterList sessionId={sessionId} />
      </AppProviders>,
    )

    expect(await screen.findByText('네트워크 관련 질문')).toBeInTheDocument()
    expect(await screen.findByText('패킷이 무엇인가요?')).toBeInTheDocument()
    expect(screen.getByText('학생 질문')).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: '질문 목록' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('list', { name: 'AI 대표질문 목록' }),
    ).toBeInTheDocument()
  })
})
