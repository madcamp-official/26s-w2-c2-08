import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError } from '../../api/errors'
import { Button } from '../../components/ui/Button'
import { pollingIntervalForJob } from '../../lib/query/polling'
import {
  createChat,
  getJob,
  listChats,
  listMessages,
  listSummaries,
  requestLiveSummary,
  retryJob,
  sendMessage,
} from './api'
import { personalAiKeys } from './queries'

interface Props {
  sessionId: string
  mode: 'LIVE' | 'REVIEW'
}

function messageFor(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 404 || error.status === 410)
      return '이전 개인 AI 결과를 더 이상 찾을 수 없습니다. 현재 수업 상태를 다시 확인해 주세요.'
    return error.message
  }
  return 'AI 요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.'
}

function JobStatus({ jobId, onDone }: { jobId: string; onDone: () => void }) {
  const queryClient = useQueryClient()
  const job = useQuery({
    queryKey: personalAiKeys.job(jobId),
    queryFn: ({ signal }) => getJob(jobId, signal),
    refetchInterval: (query) => pollingIntervalForJob(query.state.data?.status),
  })
  const retry = useMutation({
    mutationFn: () => retryJob(jobId, crypto.randomUUID()),
    onSuccess: () =>
      void queryClient.invalidateQueries({
        queryKey: personalAiKeys.job(jobId),
      }),
  })
  useEffect(() => {
    if (job.data?.status === 'SUCCEEDED') onDone()
  }, [job.data?.status, onDone])
  if (job.isError)
    return (
      <p className="form-error" role="alert">
        {messageFor(job.error)}
      </p>
    )
  if (!job.data)
    return (
      <p className="input-hint" role="status">
        AI 작업 상태를 확인하는 중…
      </p>
    )
  if (job.data.status === 'PENDING' || job.data.status === 'RUNNING')
    return (
      <p className="ai-job-state" role="status">
        AI가 저장된 결과를 준비하고 있습니다
        {job.data.progress?.stage ? ` · ${job.data.progress.stage}` : ''}
      </p>
    )
  if (job.data.status === 'FAILED')
    return (
      <div className="ai-job-failed" role="alert">
        <p>{job.data.error?.message ?? 'AI 작업에 실패했습니다.'}</p>
        {job.data.retryable && (
          <Button
            variant="secondary"
            disabled={retry.isPending}
            onClick={() => retry.mutate()}
          >
            {retry.isPending ? '재시도 요청 중…' : '다시 시도'}
          </Button>
        )}
      </div>
    )
  if (job.data.status === 'CANCELLED' || job.data.status === 'SUPERSEDED')
    return (
      <p className="input-hint" role="status">
        이 AI 작업은 현재 수업 상태 변경으로 더 이상 진행되지 않습니다.
      </p>
    )
  return null
}

function Evidence({
  evidence,
}: {
  evidence: Array<{ source_kind: string; label: string; link: string | null }>
}) {
  if (evidence.length === 0) return null
  return (
    <ul className="chat-evidence" aria-label="답변 근거">
      {evidence.map((item, index) => (
        <li key={`${item.source_kind}-${index}`}>
          {item.link ? (
            <a href={item.link}>{item.label}</a>
          ) : (
            <span aria-disabled="true">{item.label} · 더 이상 열 수 없음</span>
          )}
        </li>
      ))}
    </ul>
  )
}

export function PersonalAiPanel({ sessionId, mode }: Props) {
  const queryClient = useQueryClient()
  const [content, setContent] = useState('')
  const summaryJobStorageKey = `goal:live-summary-job:${sessionId}`
  const [summaryJobId, setSummaryJobId] = useState<string | null>(() =>
    mode === 'LIVE'
      ? window.sessionStorage.getItem(summaryJobStorageKey)
      : null,
  )
  const summaries = useQuery({
    queryKey: personalAiKeys.summaries(sessionId),
    queryFn: ({ signal }) => listSummaries(sessionId, signal),
    enabled: mode === 'LIVE',
  })
  const chats = useQuery({
    queryKey: personalAiKeys.chats(sessionId),
    queryFn: ({ signal }) => listChats(sessionId, signal),
  })
  const activeChat = chats.data?.items[0]
  const messages = useQuery({
    queryKey: personalAiKeys.messages(activeChat?.id ?? ''),
    queryFn: ({ signal }) => listMessages(activeChat?.id ?? '', signal),
    enabled: Boolean(activeChat),
  })
  const summary = useMutation({
    mutationFn: () => requestLiveSummary(sessionId, crypto.randomUUID()),
    onSuccess: (accepted) => {
      window.sessionStorage.setItem(summaryJobStorageKey, accepted.job.id)
      setSummaryJobId(accepted.job.id)
      queryClient.setQueryData(
        personalAiKeys.job(accepted.job.id),
        accepted.job,
      )
    },
  })
  const makeChat = useMutation({
    mutationFn: () => createChat(sessionId, mode, crypto.randomUUID()),
    onSuccess: () =>
      void queryClient.invalidateQueries({
        queryKey: personalAiKeys.chats(sessionId),
      }),
  })
  const send = useMutation({
    mutationFn: () => sendMessage(activeChat!.id, content, crypto.randomUUID()),
    onSuccess: (accepted) => {
      setContent('')
      queryClient.setQueryData(
        personalAiKeys.job(accepted.job.id),
        accepted.job,
      )
      void queryClient.invalidateQueries({
        queryKey: personalAiKeys.messages(activeChat!.id),
      })
    },
  })
  const pendingJobs = useMemo(
    () =>
      messages.data?.items.flatMap((item) =>
        item.role === 'USER' &&
        'response_job_id' in item &&
        item.response_job_id
          ? [item.response_job_id]
          : [],
      ) ?? [],
    [messages.data],
  )
  const normalizedLength = Array.from(content.trim().normalize('NFC')).length
  const refresh = () => {
    void queryClient.invalidateQueries({
      queryKey: personalAiKeys.summaries(sessionId),
    })
    void queryClient.invalidateQueries({
      queryKey: personalAiKeys.chats(sessionId),
    })
    if (activeChat)
      void queryClient.invalidateQueries({
        queryKey: personalAiKeys.messages(activeChat.id),
      })
  }
  return (
    <section
      className="panel personal-ai"
      aria-labelledby={`personal-ai-${mode}`}
    >
      <header className="question-panel__heading">
        <div>
          <p className="eyebrow">Personal AI</p>
          <h2 id={`personal-ai-${mode}`}>
            {mode === 'LIVE' ? '수업 따라잡기 AI' : '복습 AI'}
          </h2>
          <p>
            {mode === 'LIVE'
              ? '현재까지 확정된 강의 내용과 자료를 바탕으로 도와드립니다.'
              : '완료된 수업 기록과 자료를 바탕으로 복습을 도와드립니다.'}
          </p>
        </div>
      </header>
      {mode === 'LIVE' && (
        <div className="personal-ai__summary">
          <div>
            <strong>현재까지 요약</strong>
            {summaries.data?.items[0] ? (
              <p>{summaries.data.items[0].content}</p>
            ) : (
              <p className="input-hint">아직 요청한 요약이 없습니다.</p>
            )}
          </div>
          <Button
            variant="secondary"
            disabled={summary.isPending}
            onClick={() => summary.mutate()}
          >
            {summary.isPending ? '요청 중…' : '방금 내용 요약하기'}
          </Button>
          {summaryJobId && (
            <JobStatus
              jobId={summaryJobId}
              onDone={() => {
                window.sessionStorage.removeItem(summaryJobStorageKey)
                setSummaryJobId(null)
                refresh()
              }}
            />
          )}
          {summary.isError && (
            <p className="form-error" role="alert">
              {messageFor(summary.error)}
            </p>
          )}
        </div>
      )}
      <div className="personal-ai__chat">
        <div className="personal-ai__chat-heading">
          <strong>AI와 대화</strong>
          {!activeChat && (
            <Button
              variant="secondary"
              disabled={makeChat.isPending}
              onClick={() => makeChat.mutate()}
            >
              {makeChat.isPending ? '대화 준비 중…' : '새 대화 시작'}
            </Button>
          )}
        </div>
        {chats.isError && (
          <p className="form-error" role="alert">
            {messageFor(chats.error)}
          </p>
        )}
        {activeChat && (
          <>
            <div
              className="personal-ai__messages"
              role="log"
              aria-live="polite"
            >
              {messages.data?.items.map((item) => (
                <article
                  key={item.id}
                  className={`personal-ai__message personal-ai__message--${item.role.toLowerCase()}`}
                >
                  <strong>{item.role === 'USER' ? '나' : 'AI'}</strong>
                  <p>{item.content}</p>
                  {item.role === 'ASSISTANT' && (
                    <Evidence evidence={item.evidence} />
                  )}
                </article>
              ))}
            </div>
            {pendingJobs.map((jobId) => (
              <JobStatus key={jobId} jobId={jobId} onDone={refresh} />
            ))}
            <form
              onSubmit={(event) => {
                event.preventDefault()
                if (
                  normalizedLength >= 1 &&
                  normalizedLength <= 2000 &&
                  !send.isPending
                )
                  send.mutate()
              }}
            >
              <label htmlFor={`personal-ai-input-${mode}`}>
                AI에게 물어보기
              </label>
              <textarea
                id={`personal-ai-input-${mode}`}
                value={content}
                onChange={(event) => setContent(event.target.value)}
                rows={3}
                placeholder="예: 방금 설명한 개념을 다른 예시로 설명해줘"
              />
              <div className="question-composer__footer">
                <span
                  className={
                    normalizedLength > 2000 ? 'form-error' : 'input-hint'
                  }
                >
                  {normalizedLength}/2000
                </span>
                <Button
                  type="submit"
                  disabled={
                    normalizedLength < 1 ||
                    normalizedLength > 2000 ||
                    send.isPending
                  }
                >
                  {send.isPending ? '보내는 중…' : '질문 보내기'}
                </Button>
              </div>
              {send.isError && (
                <p className="form-error" role="alert">
                  {messageFor(send.error)}
                </p>
              )}
            </form>
          </>
        )}
      </div>
    </section>
  )
}
