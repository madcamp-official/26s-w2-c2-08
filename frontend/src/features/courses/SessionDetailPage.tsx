import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'

import { ApiError } from '../../api/errors'
import { PartialFailurePanel } from '../../components/feedback/PartialFailurePanel'
import { StatePanel } from '../../components/feedback/StatePanel'
import { useToast } from '../../components/feedback/toast-context'
import { Button } from '../../components/ui/Button'
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
import { ProfessorEndedClassView } from '../records/ProfessorEndedClassView'
import { StudentEndedClassView } from '../records/StudentEndedClassView'
import { ReadyClassView } from './ReadyClassView'

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
    mutationFn: (nextTitle: string) => updateSessionTitle(sessionId, nextTitle),
    onSuccess: (updated) => {
      queryClient.setQueryData(courseKeys.session(sessionId), updated)
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
      deleteKey.current = null
      if (session.data) {
        void queryClient.invalidateQueries({
          queryKey: courseKeys.detail(session.data.course_id),
        })
      }
      showToast({ tone: 'success', message: '완료 class를 삭제했습니다.' })
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

  if (!professor) {
    return (
      <StudentEndedClassView
        key={data.id}
        course={courseData}
        session={data}
        refreshWarning={canonicalRefreshWarning}
      />
    )
  }

  return (
    <ProfessorEndedClassView
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
      onDelete={() => remove.mutateAsync()}
      deletePending={remove.isPending}
      deleteError={remove.isError ? remove.error : undefined}
      onResetDelete={() => {
        remove.reset()
        deleteKey.current = null
      }}
    />
  )
}
