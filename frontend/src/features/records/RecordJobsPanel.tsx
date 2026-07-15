import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query'
import { useRef } from 'react'

import { ApiError } from '../../api/errors'
import { JobStatusBadge } from '../../components/domain/LmsStatus'
import { StatePanel } from '../../components/feedback/StatePanel'
import { useToast } from '../../components/feedback/toast-context'
import { Button } from '../../components/ui/Button'
import { listRecordJobs, retryRecordJob, type AIJob } from './api'
import { recordKeys } from './queries'

function jobLabel(job: AIJob) {
  if (job.job_type === 'QUESTION_CLUSTERING') return '최종 질문 분류'
  if (job.job_type === 'ANSWER_ORGANIZATION') return 'AI 답변 정리'
  if (job.job_type === 'FINAL_SUMMARY') return '최종 AI 요약'
  if (job.job_type === 'KNOWLEDGE_INDEXING') return '복습 검색 색인'
  if (job.job_type === 'RECORDING_TRANSCRIPTION') return '고품질 Transcript'
  if (job.job_type === 'MATERIAL_PROCESSING') return '강의자료 처리'
  if (job.job_type === 'SESSION_POSTPROCESSING') return '수업 후처리'
  return job.job_type
}

function jobStatusLabel(status: AIJob['status']) {
  if (status === 'SUCCEEDED') return '완료'
  if (status === 'FAILED') return '실패'
  if (status === 'RUNNING') return '실행 중'
  if (status === 'PENDING') return '대기 중'
  if (status === 'CANCELLED') return '취소됨'
  return '대체됨'
}

function canRetryFromRecord(
  job: AIJob,
  professor: boolean,
  sessionStatus: 'PROCESSING' | 'COMPLETED',
) {
  if (!professor || job.status !== 'FAILED' || !job.retryable) return false
  if (job.job_type !== 'QUESTION_CLUSTERING') return true
  if (job.clustering?.mode !== 'FINAL') return false
  return sessionStatus === 'COMPLETED'
}

function jobErrorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message
  return '작업을 다시 시작하지 못했습니다. 잠시 뒤 다시 시도해 주세요.'
}

function retryStateChanged(error: unknown) {
  return (
    error instanceof ApiError &&
    (error.status === 404 ||
      error.code === 'AI_JOB_STATE_CONFLICT' ||
      error.code === 'AI_JOB_NOT_RETRYABLE' ||
      error.code === 'AI_JOB_RETRY_SYSTEM_MANAGED')
  )
}

export function RecordJobsPanel({
  sessionId,
  professor,
  sessionStatus,
}: {
  sessionId: string
  professor: boolean
  sessionStatus: 'PROCESSING' | 'COMPLETED'
}) {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const retryKeys = useRef<
    Record<string, { attempt: number; key: string; version: number }>
  >({})
  const jobs = useInfiniteQuery({
    queryKey: recordKeys.jobs(sessionId),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      listRecordJobs(sessionId, pageParam, signal),
    getNextPageParam: (page) => page.next_cursor,
    refetchInterval: (query) => {
      if (sessionStatus === 'PROCESSING') return 3_000
      const hasActive = query.state.data?.pages
        .flatMap((page) => page.items)
        .some((job) => job.status === 'PENDING' || job.status === 'RUNNING')
      return hasActive ? 3_000 : false
    },
  })
  const items = jobs.data?.pages.flatMap((page) => page.items) ?? []
  const retry = useMutation({
    mutationFn: (job: AIJob) => {
      const existing = retryKeys.current[job.id]
      const identity =
        existing?.attempt === job.attempt && existing.version === job.version
          ? existing
          : {
              attempt: job.attempt,
              key: crypto.randomUUID(),
              version: job.version,
            }
      retryKeys.current[job.id] = identity
      return retryRecordJob(job.id, identity.key)
    },
    onSuccess: (_accepted, job) => {
      delete retryKeys.current[job.id]
      void queryClient.invalidateQueries({
        queryKey: recordKeys.jobs(sessionId),
      })
      void queryClient.invalidateQueries({
        queryKey: recordKeys.finalClusters(sessionId),
      })
      void queryClient.invalidateQueries({
        queryKey: recordKeys.answers(sessionId),
      })
      void queryClient.invalidateQueries({
        queryKey: recordKeys.manifest(sessionId),
      })
      showToast({ tone: 'success', message: '공용 작업을 다시 시작했습니다.' })
    },
    onError: (error, job) => {
      if (retryStateChanged(error)) {
        delete retryKeys.current[job.id]
        void queryClient.invalidateQueries({
          queryKey: recordKeys.jobs(sessionId),
        })
        void queryClient.invalidateQueries({
          queryKey: recordKeys.manifest(sessionId),
        })
        showToast({
          tone: 'error',
          message:
            '작업 상태가 이미 변경되었습니다. 최신 후처리 상태를 다시 불러왔습니다.',
        })
        return
      }
      showToast({ tone: 'error', message: jobErrorMessage(error) })
    },
  })

  return (
    <section className="panel record-jobs" aria-labelledby="record-jobs-title">
      <header className="question-panel__heading">
        <div>
          <p className="eyebrow">Shared post-processing jobs</p>
          <h2 id="record-jobs-title">수업 후처리 작업</h2>
          <p>
            공용 결과만 표시합니다. 개인 복습 AI 대화와 결과는 이 목록에
            포함하지 않습니다.
          </p>
        </div>
        {jobs.data && <span className="input-hint">{items.length}개</span>}
      </header>
      {jobs.isPending && (
        <StatePanel kind="loading" title="후처리 작업을 불러오는 중" />
      )}
      {jobs.isError && (
        <StatePanel
          kind="error"
          title="후처리 작업을 불러오지 못했습니다"
          actionLabel="작업 다시 불러오기"
          onAction={() => void jobs.refetch()}
        />
      )}
      {jobs.data && items.length === 0 && (
        <StatePanel kind="empty" title="표시할 공용 작업이 없습니다" />
      )}
      {items.length > 0 && (
        <ol className="record-job-list" aria-label="수업 후처리 작업 목록">
          {items.map((job) => {
            const retryable = canRetryFromRecord(job, professor, sessionStatus)
            const retryPending =
              retry.isPending && retry.variables?.id === job.id
            const retryLabel = `${jobLabel(job)} ${
              retryPending ? '재시도 요청 중' : '다시 시도'
            }`
            return (
              <li key={job.id}>
                <div>
                  <div className="record-job-list__title">
                    <strong>{jobLabel(job)}</strong>
                    <JobStatusBadge status={job.status} />
                  </div>
                  <p className="input-hint">
                    {jobStatusLabel(job.status)} · {job.attempt}번째 시도
                    {job.blocks_session_completion ? ' · 완료 판정 작업' : ''}
                  </p>
                  {job.status === 'FAILED' && job.error?.message && (
                    <p className="form-error" role="alert">
                      {job.error.message}
                    </p>
                  )}
                </div>
                {retryable && (
                  <Button
                    variant="secondary"
                    disabled={retry.isPending}
                    aria-busy={retryPending || undefined}
                    aria-label={retryLabel}
                    onClick={() => retry.mutate(job)}
                  >
                    {retryPending ? '재시도 요청 중…' : '다시 시도'}
                  </Button>
                )}
              </li>
            )
          })}
        </ol>
      )}
      {jobs.hasNextPage && (
        <Button
          variant="secondary"
          disabled={jobs.isFetchingNextPage}
          onClick={() => void jobs.fetchNextPage()}
        >
          {jobs.isFetchingNextPage ? '작업 불러오는 중…' : '작업 더 보기'}
        </Button>
      )}
      {professor && (
        <p className="input-hint">
          실패했고 서버가 재시도를 허용한 공용 작업만 다시 시작할 수 있습니다.
          FINAL 질문 분류는 class 완료 뒤에만 재시도할 수 있습니다.
        </p>
      )}
    </section>
  )
}
