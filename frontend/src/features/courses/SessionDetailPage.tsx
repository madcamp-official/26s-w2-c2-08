import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'

import { ApiError } from '../../api/errors'
import { PartialFailurePanel } from '../../components/feedback/PartialFailurePanel'
import { StatePanel } from '../../components/feedback/StatePanel'
import { useToast } from '../../components/feedback/toast-context'
import { Button } from '../../components/ui/Button'
import { Dialog } from '../../components/ui/Dialog'
import {
  createVoiceAnswer,
  type AnswerListResponse,
  type AnswerTarget,
} from '../answers/api'
import { answerKeys } from '../answers/queries'
import { AuthenticationExpiredRedirect } from '../auth/AuthenticationExpiredRedirect'
import { questionKeys } from '../questions/queries'
import { purgeLivePersonalAiClientState } from '../personal-ai/client-state'
import { deleteSession, endSession, updateSessionTitle } from './api'
import {
  courseDetailQueryOptions,
  courseKeys,
  sessionQueryOptions,
} from './queries'
import { useSessionRealtime } from '../realtime/useSessionRealtime'
import {
  ProfessorLiveClassView,
  StudentLiveClassView,
} from '../live/LiveClassRoom'
import { clearAudioPublisherClientState } from '../live/audio-publisher'
import { ProcessingClassView } from '../records/ProcessingClassView'
import { SessionRecordPage } from '../records/SessionRecordPage'
import { ReadyClassView } from './ReadyClassView'

function statusCopy(status: string) {
  switch (status) {
    case 'READY':
      return ['시작 전', '강의자료를 준비한 뒤 수업을 시작할 수 있습니다.']
    case 'LIVE':
      return [
        '진행 중',
        '실시간 수업이 진행 중입니다. 종료하면 수업 기록 정리가 시작됩니다.',
      ]
    case 'PROCESSING':
      return [
        '정리 중',
        '후처리 worker가 기록을 정리하고 있습니다. 완료 여부는 class 상태로만 확인합니다.',
      ]
    default:
      return [
        '완료',
        '수업 기록이 완성되었습니다. 다음 class를 만들 수 있습니다.',
      ]
  }
}

export function SessionDetailPage() {
  const { sessionId = '' } = useParams()
  return <SessionDetailContent key={sessionId} sessionId={sessionId} />
}

function SessionDetailContent({ sessionId }: { sessionId: string }) {
  const location = useLocation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const session = useQuery(sessionQueryOptions(sessionId))
  const course = useQuery({
    ...courseDetailQueryOptions(session.data?.course_id ?? ''),
    enabled: Boolean(session.data),
  })
  const [title, setTitle] = useState<string | null>(null)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const endKey = useRef<string | null>(null)
  const deleteKey = useRef<string | null>(null)
  const startAnswerKey = useRef<{
    target: string
    key: string
  } | null>(null)

  useSessionRealtime({
    sessionId,
    courseId: session.data?.course_id,
    enabled:
      session.isSuccess &&
      (session.data.status === 'READY' || session.data.status === 'PROCESSING'),
  })

  function refreshCourse() {
    if (session.data) {
      void queryClient.invalidateQueries({
        queryKey: courseKeys.detail(session.data.course_id),
      })
      void queryClient.invalidateQueries({
        queryKey: courseKeys.sessions(session.data.course_id),
      })
    }
  }

  const rename = useMutation({
    mutationFn: (nextTitle?: string) =>
      updateSessionTitle(
        sessionId,
        nextTitle ?? title ?? session.data?.title ?? '',
      ),
    onSuccess: (updated) => {
      queryClient.setQueryData(courseKeys.session(sessionId), updated)
      setTitle(null)
      refreshCourse()
      showToast({ tone: 'success', message: 'class 제목을 저장했습니다.' })
    },
  })
  const end = useMutation({
    mutationFn: () =>
      endSession(sessionId, (endKey.current ??= crypto.randomUUID())),
    onSuccess: (accepted) => {
      endKey.current = null
      clearAudioPublisherClientState(sessionId)
      purgeLivePersonalAiClientState(queryClient, sessionId)
      queryClient.setQueryData(courseKeys.session(sessionId), accepted.session)
      refreshCourse()
      showToast({
        tone: 'success',
        message: '수업을 종료하고 기록 정리를 시작했습니다.',
      })
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === 'ANSWER_CAPTURE_ACTIVE') {
        endKey.current = null
        void queryClient.invalidateQueries({
          queryKey: answerKeys.session(sessionId),
        })
      }
    },
  })
  const remove = useMutation({
    mutationFn: () =>
      deleteSession(sessionId, (deleteKey.current ??= crypto.randomUUID())),
    onSuccess: () => {
      setDeleteOpen(false)
      deleteKey.current = null
      if (session.data) {
        void queryClient.invalidateQueries({
          queryKey: courseKeys.detail(session.data.course_id),
        })
      }
      navigate(`/courses/${session.data?.course_id ?? ''}`, { replace: true })
    },
  })
  const startAnswer = useMutation({
    mutationFn: (target: AnswerTarget) => {
      const signature = JSON.stringify(target)
      if (startAnswerKey.current?.target !== signature) {
        startAnswerKey.current = {
          target: signature,
          key: crypto.randomUUID(),
        }
      }
      return createVoiceAnswer(sessionId, target, startAnswerKey.current.key)
    },
    onSuccess: (created) => {
      startAnswerKey.current = null
      queryClient.setQueryData<AnswerListResponse>(
        answerKeys.session(sessionId),
        (current) => ({
          items: current
            ? [
                ...current.items.filter((item) => item.id !== created.id),
                created,
              ]
            : [created],
          next_cursor: null,
        }),
      )
      void queryClient.invalidateQueries({
        queryKey: answerKeys.session(sessionId),
      })
      void queryClient.invalidateQueries({
        queryKey: questionKeys.session(sessionId),
      })
      showToast({
        tone: 'success',
        message: '음성 Answer 캡처를 시작했습니다.',
      })
    },
    onError: () => {
      void queryClient.invalidateQueries({
        queryKey: answerKeys.session(sessionId),
      })
      void queryClient.invalidateQueries({
        queryKey: questionKeys.session(sessionId),
      })
    },
  })

  if (session.isPending)
    return <StatePanel kind="loading" title="class를 불러오는 중" />
  if (session.error instanceof ApiError && session.error.status === 401) {
    return (
      <AuthenticationExpiredRedirect
        returnTo={`${location.pathname}${location.search}${location.hash}`}
      />
    )
  }
  if (session.error instanceof ApiError && session.error.status === 404) {
    return <StatePanel kind="not-found" title="class를 찾을 수 없습니다" />
  }
  if (session.error instanceof ApiError && session.error.status === 403) {
    return (
      <StatePanel kind="forbidden" title="이 class에 접근할 권한이 없습니다" />
    )
  }
  if (session.isError && !session.data)
    return (
      <StatePanel
        kind="error"
        title="class를 불러오지 못했습니다"
        actionLabel="class 다시 불러오기"
        onAction={() => void session.refetch()}
      />
    )

  if (course.isPending) {
    return <StatePanel kind="loading" title="Course 권한을 확인하는 중" />
  }
  if (course.error instanceof ApiError && course.error.status === 401) {
    return (
      <AuthenticationExpiredRedirect
        returnTo={`${location.pathname}${location.search}${location.hash}`}
      />
    )
  }
  if (course.error instanceof ApiError && course.error.status === 403) {
    return (
      <StatePanel kind="forbidden" title="이 Course에 접근할 권한이 없습니다" />
    )
  }
  if (course.error instanceof ApiError && course.error.status === 404) {
    return <StatePanel kind="not-found" title="Course를 찾을 수 없습니다" />
  }
  if (course.isError && !course.data) {
    return (
      <StatePanel
        kind="error"
        title="Course 권한을 확인하지 못했습니다"
        actionLabel="다시 시도"
        onAction={() => void course.refetch()}
      />
    )
  }

  const data = session.data
  const courseData = course.data
  if (!data) {
    return <StatePanel kind="error" title="class를 불러오지 못했습니다" />
  }

  const canonicalRefreshFailed = session.isRefetchError || course.isRefetchError
  const canonicalRefreshWarning = canonicalRefreshFailed ? (
    <PartialFailurePanel
      title="최신 class 상태를 확인하지 못했습니다"
      description="마지막으로 확인한 화면과 입력은 유지합니다. 연결을 확인한 뒤 최신 상태만 다시 불러오세요."
      actions={
        <Button
          variant="secondary"
          disabled={session.isFetching || course.isFetching}
          onClick={() => {
            void session.refetch()
            void course.refetch()
          }}
        >
          {session.isFetching || course.isFetching
            ? '상태 확인 중…'
            : '최신 상태 다시 시도'}
        </Button>
      }
    />
  ) : null

  if (data.status === 'READY') {
    return (
      <ReadyClassView
        key={data.id}
        course={courseData}
        refreshWarning={canonicalRefreshWarning}
        session={data}
      />
    )
  }

  const professor = courseData.role === 'PROFESSOR'

  if (data.status === 'LIVE') {
    const common = {
      session: data,
      courseTitle: courseData.title,
      refreshWarning: canonicalRefreshWarning,
    }
    if (!professor) return <StudentLiveClassView key={data.id} {...common} />
    return (
      <ProfessorLiveClassView
        key={data.id}
        {...common}
        onStartVoiceAnswer={(target) => startAnswer.mutate(target)}
        answerCapturePending={startAnswer.isPending}
        answerCaptureError={
          startAnswer.isError
            ? startAnswer.error instanceof ApiError
              ? startAnswer.error.message
              : '음성 Answer 캡처를 시작하지 못했습니다.'
            : null
        }
        onEnd={() => end.mutateAsync()}
        resolveEndFailure={async () => {
          const refreshed = await session.refetch()
          if (refreshed.isError || !refreshed.data) return 'unknown'
          return refreshed.data.status === 'LIVE' ? 'live' : 'ended'
        }}
        endPending={end.isPending}
        endError={
          end.isError
            ? end.error instanceof ApiError
              ? end.error.message
              : '수업 상태를 변경하지 못했습니다.'
            : null
        }
        onRename={(nextTitle) => rename.mutateAsync(nextTitle)}
        renamePending={rename.isPending}
        renameError={
          rename.isError
            ? rename.error instanceof ApiError
              ? rename.error.message
              : 'class 제목을 저장하지 못했습니다.'
            : null
        }
      />
    )
  }

  if (data.status === 'PROCESSING') {
    return (
      <ProcessingClassView
        key={data.id}
        course={courseData}
        session={data}
        refreshWarning={canonicalRefreshWarning}
        onRename={(nextTitle) => rename.mutateAsync(nextTitle)}
        renamePending={rename.isPending}
        renameError={
          rename.isError
            ? rename.error instanceof ApiError
              ? rename.error.message
              : 'class 제목을 저장하지 못했습니다.'
            : null
        }
      />
    )
  }

  const [statusTitle, statusDescription] = statusCopy(data.status)
  const canDelete = data.status === 'COMPLETED'
  const isRecordView = data.status === 'COMPLETED'

  return (
    <section
      className="course-form-page"
      aria-labelledby="session-detail-title"
    >
      <header className="course-form-heading">
        <p className="eyebrow">Class lifecycle</p>
        <span
          className={`status-chip status-chip--${data.status.toLowerCase()}`}
        >
          {statusTitle}
        </span>
        <h1 id="session-detail-title">{data.title}</h1>
        <p>{statusDescription}</p>
      </header>
      {canonicalRefreshWarning}
      <div className="panel course-form session-detail-card">
        <dl className="session-meta">
          <div>
            <dt>수업 날짜</dt>
            <dd>{data.lecture_date}</dd>
          </div>
          <div>
            <dt>시작 시각</dt>
            <dd>
              {data.started_at
                ? new Date(data.started_at).toLocaleString('ko-KR')
                : '아직 시작 전'}
            </dd>
          </div>
        </dl>

        {professor ? (
          <>
            <label>
              <span>class 제목</span>
              <input
                value={title ?? data.title}
                onChange={(event) => setTitle(event.target.value)}
              />
            </label>
            <p className="input-hint">
              비워 저장하면 생성 시각 기준의 서버 자동 제목으로 돌아갑니다.
            </p>
            {rename.isError && (
              <p className="form-error" role="alert">
                제목을 저장하지 못했습니다.
              </p>
            )}
            <div className="form-actions">
              <Button
                variant="secondary"
                disabled={rename.isPending}
                onClick={() => rename.mutate(title ?? data.title)}
              >
                {rename.isPending ? '저장 중…' : '제목 저장'}
              </Button>
              {canDelete && (
                <Button
                  variant="ghost"
                  onClick={() => {
                    remove.reset()
                    deleteKey.current = null
                    setDeleteOpen(true)
                  }}
                >
                  class 삭제
                </Button>
              )}
              <Link
                className="button button--ghost"
                to={`/courses/${data.course_id}`}
              >
                Course로 돌아가기
              </Link>
            </div>
          </>
        ) : (
          <>
            <p className="input-hint">
              학생은 class 상태와 수업 기록을 읽기 전용으로 확인합니다.
            </p>
            <div className="form-actions">
              <Link
                className="button button--ghost"
                to={`/courses/${data.course_id}`}
              >
                Course로 돌아가기
              </Link>
            </div>
          </>
        )}
        {professor && end.isError && (
          <p className="form-error" role="alert">
            상태를 변경하지 못했습니다. 현재 class를 다시 확인해 주세요.
          </p>
        )}
      </div>
      {isRecordView && (
        <SessionRecordPage sessionId={data.id} professor={professor} />
      )}
      {professor && (
        <Dialog
          open={deleteOpen}
          title="class를 삭제할까요?"
          description="삭제 후에는 되돌릴 수 없습니다."
          onOpenChange={(open) => {
            if (!open && !remove.isPending) {
              remove.reset()
              deleteKey.current = null
            }
            setDeleteOpen(open)
          }}
          actions={
            <>
              <Button
                variant="secondary"
                disabled={remove.isPending}
                onClick={() => {
                  remove.reset()
                  deleteKey.current = null
                  setDeleteOpen(false)
                }}
              >
                취소
              </Button>
              <Button
                variant="danger"
                disabled={remove.isPending}
                onClick={() => remove.mutate()}
              >
                {remove.isPending ? '삭제 중…' : '삭제'}
              </Button>
            </>
          }
        >
          {remove.isError && <p role="alert">class를 삭제하지 못했습니다.</p>}
        </Dialog>
      )}
    </section>
  )
}
