import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
  type ChatMessage,
  type ChatMessageList,
} from './api'
import { personalAiKeys } from './queries'
import {
  clearLiveSummaryJobId,
  readLiveSummaryJobId,
  writeLiveSummaryJobId,
} from './client-state'
import { courseKeys } from '../courses/queries'
import type { LectureSession } from '../courses/api'

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

function JobStatus({
  sessionId,
  jobId,
  onDone,
}: {
  sessionId: string
  jobId: string
  onDone: () => void
}) {
  const queryClient = useQueryClient()
  const completionNotified = useRef(false)
  const retryKey = useRef<string | null>(null)
  const job = useQuery({
    queryKey: personalAiKeys.job(sessionId, jobId),
    queryFn: ({ signal }) => getJob(jobId, signal),
    refetchInterval: (query) => pollingIntervalForJob(query.state.data?.status),
  })
  const retry = useMutation({
    mutationFn: () =>
      retryJob(jobId, (retryKey.current ??= crypto.randomUUID())),
    onSuccess: () => {
      retryKey.current = null
      void queryClient.invalidateQueries({
        queryKey: personalAiKeys.job(sessionId, jobId),
      })
    },
  })
  useEffect(() => {
    if (job.data?.status !== 'SUCCEEDED') {
      completionNotified.current = false
      return
    }
    if (!completionNotified.current) {
      completionNotified.current = true
      onDone()
    }
  }, [job.data?.status, onDone])
  if (job.isError)
    return (
      <div className="ai-region-error" role="alert">
        <p>{messageFor(job.error)}</p>
        <Button
          variant="secondary"
          disabled={job.isFetching}
          onClick={() => void job.refetch()}
        >
          {job.isFetching ? '작업 확인 중…' : 'AI 작업 다시 확인'}
        </Button>
      </div>
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
        {retry.isError && (
          <p className="form-error">{messageFor(retry.error)}</p>
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
  const summaryKey = useRef<string | null>(null)
  const chatKey = useRef<string | null>(null)
  const messageRequest = useRef<{
    signature: string
    key: string
  } | null>(null)
  const [summaryJobId, setSummaryJobId] = useState<string | null>(() =>
    mode === 'LIVE' ? readLiveSummaryJobId(sessionId) : null,
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
    queryKey: personalAiKeys.messages(sessionId, activeChat?.id ?? ''),
    queryFn: async ({ signal }) => {
      const key = personalAiKeys.messages(sessionId, activeChat?.id ?? '')
      const fetched = await listMessages(activeChat?.id ?? '', signal)
      const cached = queryClient.getQueryData<ChatMessageList>(key)
      if (!cached) return fetched
      const merged = new Map(
        fetched.items.map((message) => [message.id, message] as const),
      )
      cached.items.forEach((message) => {
        if (!merged.has(message.id)) merged.set(message.id, message)
      })
      return {
        items: [...merged.values()].sort(
          (left, right) => left.sequence - right.sequence,
        ),
        next_cursor: fetched.next_cursor,
      }
    },
    enabled: Boolean(activeChat),
  })
  const summary = useMutation({
    mutationFn: () =>
      requestLiveSummary(
        sessionId,
        (summaryKey.current ??= crypto.randomUUID()),
      ),
    onSuccess: (accepted) => {
      summaryKey.current = null
      const current = queryClient.getQueryData<LectureSession>(
        courseKeys.session(sessionId),
      )
      if (mode === 'LIVE' && current?.status !== 'LIVE') return
      writeLiveSummaryJobId(sessionId, accepted.job.id)
      setSummaryJobId(accepted.job.id)
      queryClient.setQueryData(
        personalAiKeys.job(sessionId, accepted.job.id),
        accepted.job,
      )
    },
  })
  const makeChat = useMutation({
    mutationFn: () =>
      createChat(sessionId, mode, (chatKey.current ??= crypto.randomUUID())),
    onSuccess: () => {
      chatKey.current = null
      const current = queryClient.getQueryData<LectureSession>(
        courseKeys.session(sessionId),
      )
      if (mode === 'LIVE' && current?.status !== 'LIVE') return
      void queryClient.invalidateQueries({
        queryKey: personalAiKeys.chats(sessionId),
      })
    },
  })
  const send = useMutation({
    mutationFn: (request: { chatId: string; content: string }) => {
      const signature = `${request.chatId}:${request.content.normalize('NFC')}`
      if (messageRequest.current?.signature !== signature) {
        messageRequest.current = { signature, key: crypto.randomUUID() }
      }
      return sendMessage(
        request.chatId,
        request.content,
        messageRequest.current.key,
      )
    },
    onSuccess: (accepted, request) => {
      messageRequest.current = null
      const current = queryClient.getQueryData<LectureSession>(
        courseKeys.session(sessionId),
      )
      if (mode === 'LIVE' && current?.status !== 'LIVE') return
      setContent((current) => (current === request.content ? '' : current))
      const acceptedUserMessage: ChatMessage = {
        ...accepted.user_message,
        role: 'USER',
        job_id: null,
        response_job_id:
          accepted.user_message.response_job_id ?? accepted.job.id,
        evidence: [],
        model_name: null,
        prompt_version: null,
      }
      queryClient.setQueryData<ChatMessageList>(
        personalAiKeys.messages(sessionId, acceptedUserMessage.chat_id),
        (current) => ({
          items: [
            ...(current?.items.filter(
              (message) => message.id !== acceptedUserMessage.id,
            ) ?? []),
            acceptedUserMessage,
          ].sort((left, right) => left.sequence - right.sequence),
          next_cursor: current?.next_cursor ?? null,
        }),
      )
      queryClient.setQueryData(
        personalAiKeys.job(sessionId, accepted.job.id),
        accepted.job,
      )
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
  const refresh = useCallback(() => {
    void queryClient.invalidateQueries({
      queryKey: personalAiKeys.summaries(sessionId),
    })
    void queryClient.invalidateQueries({
      queryKey: personalAiKeys.chats(sessionId),
    })
    if (activeChat)
      void queryClient.invalidateQueries({
        queryKey: personalAiKeys.messages(sessionId, activeChat.id),
      })
  }, [activeChat, queryClient, sessionId])
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
            {summaries.isPending ? (
              <p className="input-hint" role="status">
                저장된 요약을 불러오는 중…
              </p>
            ) : summaries.isError ? (
              <div className="ai-region-error" role="alert">
                <p>{messageFor(summaries.error)}</p>
                <Button
                  variant="secondary"
                  disabled={summaries.isFetching}
                  onClick={() => void summaries.refetch()}
                >
                  {summaries.isFetching
                    ? '다시 불러오는 중…'
                    : '요약 다시 불러오기'}
                </Button>
              </div>
            ) : summaries.data.items[0] ? (
              <p>{summaries.data.items[0].content}</p>
            ) : (
              <p className="input-hint">아직 요청한 요약이 없습니다.</p>
            )}
          </div>
          <Button
            variant="secondary"
            disabled={
              summary.isPending || summaries.isPending || summaries.isError
            }
            onClick={() => summary.mutate()}
          >
            {summary.isPending ? '요청 중…' : '방금 내용 요약하기'}
          </Button>
          {summaryJobId && (
            <JobStatus
              sessionId={sessionId}
              jobId={summaryJobId}
              onDone={() => {
                clearLiveSummaryJobId(sessionId)
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
          {chats.isSuccess && !activeChat && (
            <Button
              variant="secondary"
              disabled={makeChat.isPending}
              onClick={() => makeChat.mutate()}
            >
              {makeChat.isPending ? '대화 준비 중…' : '새 대화 시작'}
            </Button>
          )}
        </div>
        {chats.isPending && (
          <p className="input-hint" role="status">
            저장된 AI 대화를 불러오는 중…
          </p>
        )}
        {chats.isError && (
          <div className="ai-region-error" role="alert">
            <p>{messageFor(chats.error)}</p>
            <Button
              variant="secondary"
              disabled={chats.isFetching}
              onClick={() => void chats.refetch()}
            >
              {chats.isFetching
                ? '다시 불러오는 중…'
                : '대화 목록 다시 불러오기'}
            </Button>
          </div>
        )}
        {makeChat.isError && (
          <p className="form-error" role="alert">
            {messageFor(makeChat.error)}
          </p>
        )}
        {activeChat && (
          <>
            {messages.isPending && (
              <p className="input-hint" role="status">
                대화 내용을 불러오는 중…
              </p>
            )}
            {messages.isError && (
              <div className="ai-region-error" role="alert">
                <p>{messageFor(messages.error)}</p>
                <Button
                  variant="secondary"
                  disabled={messages.isFetching}
                  onClick={() => void messages.refetch()}
                >
                  {messages.isFetching
                    ? '다시 불러오는 중…'
                    : '대화 내용 다시 불러오기'}
                </Button>
              </div>
            )}
            {messages.isSuccess && (
              <div
                className="personal-ai__messages"
                role="log"
                aria-live="polite"
              >
                {messages.data.items.map((item) => (
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
            )}
            {pendingJobs.map((jobId) => (
              <JobStatus
                key={jobId}
                sessionId={sessionId}
                jobId={jobId}
                onDone={refresh}
              />
            ))}
            {messages.isSuccess && (
              <form
                onSubmit={(event) => {
                  event.preventDefault()
                  if (
                    normalizedLength >= 1 &&
                    normalizedLength <= 2000 &&
                    !send.isPending
                  )
                    send.mutate({ chatId: activeChat.id, content })
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
            )}
          </>
        )}
      </div>
    </section>
  )
}
