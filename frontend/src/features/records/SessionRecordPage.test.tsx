import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'

import { ToastProvider } from '../../components/feedback/ToastProvider'
import { server } from '../../test/server'
import { SessionRecordPage } from './SessionRecordPage'

const sessionId = '10000000-0000-0000-0000-000000000001'
const courseId = '20000000-0000-0000-0000-000000000001'
const versionId = '30000000-0000-0000-0000-000000000001'

function session(status: 'PROCESSING' | 'COMPLETED') {
  return {
    id: sessionId,
    course_id: courseId,
    title: '네트워크 강의',
    lecture_date: '2026-07-14',
    status,
    version: 1,
    canonical_transcript_version_id: status === 'COMPLETED' ? versionId : null,
    started_at: '2026-07-14T01:00:00Z',
    ended_at: '2026-07-14T02:00:00Z',
    completed_at: status === 'COMPLETED' ? '2026-07-14T02:10:00Z' : null,
    created_at: '2026-07-14T00:50:00Z',
    updated_at: '2026-07-14T02:10:00Z',
  }
}

function record(status: 'PROCESSING' | 'COMPLETED') {
  const finalized = status === 'COMPLETED'
  return {
    session: session(status),
    recording: finalized
      ? {
          id: 'recording-1',
          session_id: sessionId,
          status: 'UPLOADED',
          version: 1,
          content_type: 'audio/webm',
          byte_size: 1024,
          duration_ms: 60_000,
          playback_url: '/api/v1/recordings/recording-1/playback',
          created_at: '2026-07-14T01:00:00Z',
          updated_at: '2026-07-14T02:10:00Z',
        }
      : null,
    recording_url: `/api/v1/sessions/${sessionId}/recording`,
    materials: {
      total_count: 0,
      list_url: `/api/v1/sessions/${sessionId}/materials`,
    },
    transcript: finalized
      ? {
          state: {
            session_id: sessionId,
            status: 'FINALIZED',
            current_version: {},
            canonical_version_id: versionId,
            canonical_version: {},
            updated_at: '2026-07-14T02:10:00Z',
          },
          selected_version_id: versionId,
          segment_count: 1,
          gap_count: 1,
          timeline_url: `/api/v1/sessions/${sessionId}/transcript?transcript_version_id=${versionId}`,
          versions_url: `/api/v1/sessions/${sessionId}/transcript/versions`,
        }
      : {
          state: null,
          selected_version_id: null,
          segment_count: 0,
          gap_count: 0,
          timeline_url: `/api/v1/sessions/${sessionId}/transcript`,
          versions_url: `/api/v1/sessions/${sessionId}/transcript/versions`,
        },
    summary: finalized
      ? {
          state: { status: 'AVAILABLE', reason: null },
          summary_url: '/api/v1/summaries/summary-1',
          summaries_url: `/api/v1/sessions/${sessionId}/summaries?summary_type=FINAL`,
        }
      : {
          state: { status: 'PENDING', reason: null },
          summary_url: null,
          summaries_url: `/api/v1/sessions/${sessionId}/summaries?summary_type=FINAL`,
        },
    questions: {
      total_count: 0,
      list_url: `/api/v1/sessions/${sessionId}/questions?sort=RECENT`,
    },
    question_clusters: {
      state: {
        pending: false,
        requested_through_sequence: 0,
        applied_through_sequence: 0,
        current_revision: 0,
        current_generation: null,
        final_generation: null,
        active_job_id: null,
        retry_job_id: null,
        last_job: null,
      },
      current: {
        total_count: 0,
        list_url: `/api/v1/sessions/${sessionId}/question-clusters?scope=CURRENT`,
      },
      final: {
        total_count: 0,
        list_url: `/api/v1/sessions/${sessionId}/question-clusters?scope=FINAL`,
      },
    },
    answers: {
      total_count: 0,
      list_url: `/api/v1/sessions/${sessionId}/answers`,
    },
    jobs: {
      total_count: 1,
      list_url: `/api/v1/sessions/${sessionId}/jobs`,
    },
  }
}

function renderPage(professor = false) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <SessionRecordPage sessionId={sessionId} professor={professor} />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('SessionRecordPage', () => {
  it('keeps processing record areas available without a recording or REVIEW Chat', async () => {
    server.use(
      http.get('*/api/v1/sessions/:id/record', () =>
        HttpResponse.json(record('PROCESSING')),
      ),
    )

    renderPage()

    expect(
      await screen.findByText('수업 기록을 정리하고 있습니다'),
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        '이 수업에는 저장된 녹음이 없습니다. Transcript와 다른 기록은 계속 확인할 수 있습니다.',
      ),
    ).toBeInTheDocument()
    expect(
      screen.getByText('최종 Transcript를 기준으로 요약을 준비하고 있습니다.'),
    ).toBeInTheDocument()
    expect(screen.queryByText('복습 AI')).not.toBeInTheDocument()
  })

  it('loads completed summary and merges transcript Segment and Gap independently', async () => {
    server.use(
      http.get('*/api/v1/sessions/:id/record', () =>
        HttpResponse.json(record('COMPLETED')),
      ),
      http.get('*/api/v1/sessions/:id/summaries', () =>
        HttpResponse.json({
          summary_status: 'AVAILABLE',
          summary_reason: null,
          items: [
            {
              id: 'summary-1',
              session_id: sessionId,
              job_id: 'job-1',
              summary_type: 'FINAL',
              visibility: 'COURSE_MEMBERS',
              content: 'TCP 흐름 제어와 혼잡 제어를 구분했습니다.',
              source_transcript_version_id: versionId,
              source_start_sequence: 1,
              source_end_sequence: 1,
              model_name: null,
              prompt_version: 'final-v1',
              created_at: '2026-07-14T02:10:00Z',
            },
          ],
          next_cursor: null,
        }),
      ),
      http.get('*/api/v1/sessions/:id/transcript', () =>
        HttpResponse.json({
          transcript: record('COMPLETED').transcript.state,
          selected_version: {},
          segments: [
            {
              id: 'segment-1',
              session_id: sessionId,
              transcript_version_id: versionId,
              item_type: 'SEGMENT',
              sequence: 1,
              start_ms: 1_000,
              end_ms: 2_000,
              recording_start_ms: 1_100,
              recording_end_ms: 2_100,
              text: '흐름 제어부터 살펴보겠습니다.',
              created_at: '2026-07-14T02:10:00Z',
            },
          ],
          gaps: [
            {
              id: 'gap-1',
              session_id: sessionId,
              transcript_version_id: versionId,
              item_type: 'GAP',
              start_ms: 3_000,
              end_ms: 3_500,
              is_final: true,
              reason: 'CLIENT_DISCONNECTED',
              created_at: '2026-07-14T02:10:00Z',
            },
          ],
          next_cursor: null,
        }),
      ),
      http.get('*/api/v1/sessions/:id/question-clusters', () =>
        HttpResponse.json({
          scope: 'FINAL',
          clustering_state: record('COMPLETED').question_clusters.state,
          generation: null,
          items: [],
          next_cursor: null,
        }),
      ),
      http.get('*/api/v1/sessions/:id/answers', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.get('*/api/v1/sessions/:id/chats', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    )

    renderPage()

    expect(
      await screen.findByText('TCP 흐름 제어와 혼잡 제어를 구분했습니다.'),
    ).toBeInTheDocument()
    expect(
      await screen.findByRole('button', {
        name: '흐름 제어부터 살펴보겠습니다.',
      }),
    ).toBeInTheDocument()
    expect(screen.getByText(/음성이 누락된 구간입니다/)).toBeInTheDocument()
    expect(screen.getByText('복습 AI')).toBeInTheDocument()
  })

  it('keeps record management controls out of the student DOM', async () => {
    server.use(
      http.get('*/api/v1/sessions/:id/record', () =>
        HttpResponse.json(record('COMPLETED')),
      ),
      http.get('*/api/v1/sessions/:id/summaries', () =>
        HttpResponse.json({
          summary_status: 'AVAILABLE',
          summary_reason: null,
          items: [],
          next_cursor: null,
        }),
      ),
      http.get('*/api/v1/sessions/:id/transcript', () =>
        HttpResponse.json({
          transcript: record('COMPLETED').transcript.state,
          selected_version: {},
          segments: [],
          gaps: [],
          next_cursor: null,
        }),
      ),
      http.get('*/api/v1/sessions/:id/questions', () =>
        HttpResponse.json({
          items: [
            {
              id: 'question-1',
              session_id: sessionId,
              content: '라우팅 테이블은 어떻게 갱신되나요?',
              status: 'OPEN',
              version: 1,
              clustering_sequence: 1,
              reaction_count: 2,
              reacted_by_me: false,
            },
          ],
          next_cursor: null,
        }),
      ),
      http.get('*/api/v1/sessions/:id/question-clusters', () =>
        HttpResponse.json({
          scope: 'FINAL',
          clustering_state: record('COMPLETED').question_clusters.state,
          generation: 1,
          items: [],
          next_cursor: null,
        }),
      ),
      http.get('*/api/v1/sessions/:id/answers', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.get('*/api/v1/sessions/:id/jobs', () =>
        HttpResponse.json({
          items: [
            {
              id: 'failed-final-clustering',
              session_id: sessionId,
              job_type: 'QUESTION_CLUSTERING',
              visibility: 'SHARED',
              status: 'FAILED',
              attempt: 1,
              version: 1,
              progress: null,
              retryable: true,
              blocks_session_completion: true,
              clustering: {
                mode: 'FINAL',
                input_through_sequence: 1,
                base_revision: 1,
                final_answered_through_at: '2026-07-14T02:00:00Z',
              },
              error: {
                code: 'PROVIDER_UNAVAILABLE',
                message: '최종 분류를 완료하지 못했습니다.',
              },
              target: {
                resource_type: 'SESSION',
                resource_id: sessionId,
                resource_url: null,
              },
              result: null,
              result_unavailable_reason: null,
              created_at: '2026-07-14T02:00:00Z',
              updated_at: '2026-07-14T02:00:00Z',
              started_at: '2026-07-14T02:00:00Z',
              finished_at: '2026-07-14T02:01:00Z',
            },
          ],
          next_cursor: null,
        }),
      ),
      http.get('*/api/v1/sessions/:id/chats', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    )

    renderPage(false)

    expect(await screen.findByText('수업 질문')).toBeInTheDocument()
    expect(
      await screen.findByText('라우팅 테이블은 어떻게 갱신되나요?'),
    ).toBeInTheDocument()
    expect(
      screen.queryByText('미답변 학생 질문에 텍스트 답변'),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: '다시 시도' }),
    ).not.toBeInTheDocument()
  })

  it('shows only allowed shared-job retries to a professor', async () => {
    const failedJob = (
      id: string,
      jobType: string,
      clustering: unknown = null,
    ) => ({
      id,
      session_id: sessionId,
      job_type: jobType,
      visibility: 'SHARED',
      status: 'FAILED',
      attempt: 1,
      version: 1,
      progress: null,
      retryable: true,
      blocks_session_completion: true,
      clustering,
      error: { code: 'PROVIDER_UNAVAILABLE', message: '처리하지 못했습니다.' },
      target: {
        resource_type: 'SESSION',
        resource_id: sessionId,
        resource_url: null,
      },
      result: null,
      result_unavailable_reason: null,
      created_at: '2026-07-14T02:00:00Z',
      updated_at: '2026-07-14T02:00:00Z',
      started_at: '2026-07-14T02:00:00Z',
      finished_at: '2026-07-14T02:01:00Z',
    })
    server.use(
      http.get('*/api/v1/sessions/:id/record', () =>
        HttpResponse.json(record('COMPLETED')),
      ),
      http.get('*/api/v1/sessions/:id/summaries', () =>
        HttpResponse.json({
          summary_status: 'AVAILABLE',
          summary_reason: null,
          items: [],
          next_cursor: null,
        }),
      ),
      http.get('*/api/v1/sessions/:id/transcript', () =>
        HttpResponse.json({
          transcript: record('COMPLETED').transcript.state,
          selected_version: {},
          segments: [],
          gaps: [],
          next_cursor: null,
        }),
      ),
      http.get('*/api/v1/sessions/:id/questions', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.get('*/api/v1/sessions/:id/question-clusters', () =>
        HttpResponse.json({
          scope: 'FINAL',
          clustering_state: record('COMPLETED').question_clusters.state,
          generation: null,
          items: [],
          next_cursor: null,
        }),
      ),
      http.get('*/api/v1/sessions/:id/answers', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.get('*/api/v1/sessions/:id/jobs', () =>
        HttpResponse.json({
          items: [
            failedJob('final-clustering', 'QUESTION_CLUSTERING', {
              mode: 'FINAL',
              input_through_sequence: 1,
              base_revision: 1,
              final_answered_through_at: '2026-07-14T02:00:00Z',
            }),
            failedJob('answer-organization', 'ANSWER_ORGANIZATION'),
            failedJob('hq-stt', 'RECORDING_TRANSCRIPTION'),
          ],
          next_cursor: null,
        }),
      ),
      http.get('*/api/v1/sessions/:id/chats', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    )

    renderPage(true)

    expect(await screen.findByText('수업 후처리 작업')).toBeInTheDocument()
    expect(
      await screen.findAllByRole('button', { name: '다시 시도' }),
    ).toHaveLength(2)
    expect(screen.getByText('고품질 Transcript')).toBeInTheDocument()
    expect(
      screen.getByText(
        /고품질 Transcript는 수업 기록의 신뢰성을 위해 여기서 재시도하지 않습니다/,
      ),
    ).toBeInTheDocument()
  })
})
