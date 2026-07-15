import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { delay, http, HttpResponse } from 'msw'
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

function failedSharedJob(
  id: string,
  jobType: string,
  clustering: unknown = null,
) {
  return {
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
    let questionRequests = 0
    server.use(
      http.get('*/api/v1/sessions/:id/record', () =>
        HttpResponse.json(record('PROCESSING')),
      ),
      http.get('*/api/v1/sessions/:id/questions', () => {
        questionRequests += 1
        return HttpResponse.json({ items: [], next_cursor: null })
      }),
      http.get('*/api/v1/sessions/:id/question-clusters', () =>
        HttpResponse.json({
          scope: 'FINAL',
          clustering_state: record('PROCESSING').question_clusters.state,
          generation: null,
          items: [],
          next_cursor: null,
        }),
      ),
      http.get('*/api/v1/sessions/:id/answers', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.get('*/api/v1/sessions/:id/jobs', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    )

    renderPage()

    expect(
      await screen.findByText('수업 기록을 정리하고 있습니다'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('원본 녹음 저장 상태를 확인하는 중'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('최종 Transcript를 기준으로 요약을 준비하고 있습니다.'),
    ).toBeInTheDocument()
    expect(screen.getByText('수업 질문')).toBeInTheDocument()
    expect(screen.getByText('교수자 답변')).toBeInTheDocument()
    expect(screen.getByText('수업 후처리 작업')).toBeInTheDocument()
    expect(screen.queryByText('복습 AI')).not.toBeInTheDocument()
    await waitFor(() => expect(questionRequests).toBeGreaterThan(1), {
      timeout: 4_000,
    })
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
      screen.queryByRole('button', { name: /다시 시도$/ }),
    ).not.toBeInTheDocument()
  })

  it('shows every server-allowed shared-job retry to a professor', async () => {
    const retryableJobs = [
      failedSharedJob('final-clustering', 'QUESTION_CLUSTERING', {
        mode: 'FINAL',
        input_through_sequence: 1,
        base_revision: 1,
        final_answered_through_at: '2026-07-14T02:00:00Z',
      }),
      failedSharedJob('answer-organization', 'ANSWER_ORGANIZATION'),
      failedSharedJob('hq-stt', 'RECORDING_TRANSCRIPTION'),
    ]
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
          items: retryableJobs,
          next_cursor: null,
        }),
      ),
      http.post('*/api/v1/jobs/:id/retry', async ({ params }) => {
        await delay(150)
        const job = retryableJobs.find((item) => item.id === params.id)
        return HttpResponse.json(
          {
            job: {
              ...job,
              status: 'PENDING',
              attempt: 2,
              version: 2,
              retryable: false,
              error: null,
              started_at: null,
              finished_at: null,
            },
          },
          { status: 202 },
        )
      }),
      http.get('*/api/v1/sessions/:id/chats', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    )

    renderPage(true)

    expect(await screen.findByText('수업 후처리 작업')).toBeInTheDocument()
    const clusteringRetry = await screen.findByRole('button', {
      name: '최종 질문 분류 다시 시도',
    })
    const organizationRetry = screen.getByRole('button', {
      name: 'AI 답변 정리 다시 시도',
    })
    const transcriptRetry = screen.getByRole('button', {
      name: '고품질 Transcript 다시 시도',
    })
    expect(screen.getAllByText('고품질 Transcript')).toHaveLength(2)
    expect(
      screen.getByText(
        /실패했고 서버가 재시도를 허용한 공용 작업만 다시 시작할 수 있습니다/,
      ),
    ).toBeInTheDocument()

    fireEvent.click(organizationRetry)
    expect(
      await screen.findByRole('button', {
        name: 'AI 답변 정리 재시도 요청 중',
      }),
    ).toBeDisabled()
    expect(clusteringRetry).toBeDisabled()
    expect(transcriptRetry).toBeDisabled()
    expect(
      screen.queryByRole('button', {
        name: '고품질 Transcript 재시도 요청 중',
      }),
    ).not.toBeInTheDocument()
    expect(
      await screen.findByText('공용 작업을 다시 시작했습니다.'),
    ).toBeInTheDocument()
  })

  it('reuses an idempotency key after an ambiguous retry failure and rotates it after success', async () => {
    const job = failedSharedJob('postprocessing', 'SESSION_POSTPROCESSING')
    const retryKeys: string[] = []
    let retryRequests = 0
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
        HttpResponse.json({ items: [job], next_cursor: null }),
      ),
      http.get('*/api/v1/sessions/:id/chats', () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.post('*/api/v1/jobs/:id/retry', ({ request }) => {
        retryRequests += 1
        retryKeys.push(request.headers.get('Idempotency-Key') ?? '')
        if (retryRequests === 1) {
          return HttpResponse.json(
            {
              error: {
                code: 'SERVICE_UNAVAILABLE',
                message: '재시도 결과를 확인하지 못했습니다.',
                request_id: 'req-retry-1',
                details: null,
              },
            },
            { status: 503 },
          )
        }
        return HttpResponse.json(
          {
            job: {
              ...job,
              status: 'PENDING',
              attempt: 2,
              version: 2,
              error: null,
              started_at: null,
              finished_at: null,
            },
          },
          { status: 202 },
        )
      }),
    )

    renderPage(true)

    fireEvent.click(
      await screen.findByRole('button', { name: '수업 후처리 다시 시도' }),
    )
    expect(
      await screen.findByText('재시도 결과를 확인하지 못했습니다.'),
    ).toBeInTheDocument()
    await waitFor(() => expect(retryKeys).toHaveLength(1))

    fireEvent.click(
      screen.getByRole('button', { name: '수업 후처리 다시 시도' }),
    )
    expect(
      await screen.findByText('공용 작업을 다시 시작했습니다.'),
    ).toBeInTheDocument()
    await waitFor(() => expect(retryKeys).toHaveLength(2))
    expect(retryKeys[1]).toBe(retryKeys[0])

    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: '수업 후처리 다시 시도' }),
      ).toBeEnabled(),
    )
    fireEvent.click(
      screen.getByRole('button', { name: '수업 후처리 다시 시도' }),
    )
    await waitFor(() => expect(retryKeys).toHaveLength(3))
    expect(retryKeys[2]).not.toBe(retryKeys[1])
  })
})
