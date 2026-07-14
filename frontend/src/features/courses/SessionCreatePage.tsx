import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useEffect, useId, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'

import { ApiError } from '../../api/errors'
import { StatePanel } from '../../components/feedback/StatePanel'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/Button'
import { Card } from '../../components/ui/Card'
import { Field } from '../../components/ui/Field'
import { LinkButton } from '../../components/ui/LinkButton'
import { AuthenticationExpiredRedirect } from '../auth/AuthenticationExpiredRedirect'
import { createCourseSession } from './api'
import { courseDetailQueryOptions, courseKeys } from './queries'

function todayInSeoul() {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date())
}

export function SessionCreatePage() {
  const { courseId = '' } = useParams()
  return <SessionCreatePageContent key={courseId} courseId={courseId} />
}

function SessionCreatePageContent({ courseId }: { courseId: string }) {
  const titleId = useId()
  const lectureDateId = useId()
  const location = useLocation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const course = useQuery(courseDetailQueryOptions(courseId))
  const [title, setTitle] = useState('')
  const [lectureDate, setLectureDate] = useState(todayInSeoul)
  const [fieldError, setFieldError] = useState<string | null>(null)
  const dateInputRef = useRef<HTMLInputElement>(null)
  const requestErrorRef = useRef<HTMLDivElement>(null)
  const idempotencyKey = useRef<string | null>(null)
  const mounted = useRef(false)
  const create = useMutation({
    mutationFn: () =>
      createCourseSession(
        courseId,
        { title: title.trim() || undefined, lecture_date: lectureDate },
        (idempotencyKey.current ??= crypto.randomUUID()),
      ),
    onSuccess: (created) => {
      void queryClient.invalidateQueries({
        queryKey: courseKeys.detail(courseId),
      })
      void queryClient.invalidateQueries({
        queryKey: courseKeys.sessions(courseId),
      })
      if (mounted.current) {
        void navigate(`/sessions/${created.id}`, { replace: true })
      }
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === 'ACTIVE_SESSION_EXISTS') {
        void queryClient.invalidateQueries({
          queryKey: courseKeys.detail(courseId),
        })
      }
    },
  })

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  useEffect(() => {
    if (create.isError) requestErrorRef.current?.focus()
  }, [create.isError])

  function resetRequest() {
    idempotencyKey.current = null
    if (create.isError) create.reset()
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (create.isPending) return
    if (!lectureDate) {
      setFieldError('수업 날짜를 선택해 주세요.')
      dateInputRef.current?.focus()
      return
    }
    setFieldError(null)
    create.mutate()
  }

  if (course.isPending) {
    return <StatePanel kind="loading" title="Course를 불러오는 중" />
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
  if (course.isError) {
    return (
      <StatePanel
        kind="error"
        title="Class 생성 정보를 불러오지 못했습니다"
        actionLabel="다시 시도"
        onAction={() => void course.refetch()}
      />
    )
  }
  if (course.data.role !== 'PROFESSOR') {
    return (
      <StatePanel
        kind="forbidden"
        title="교수자만 새 class를 만들 수 있습니다"
      />
    )
  }
  if (course.data.current_session) {
    return (
      <StatePanel
        kind="error"
        title="진행 중인 class가 있습니다"
        description="현재 class가 완료된 뒤에 다음 class를 만들 수 있습니다."
        actionLabel="현재 class 보기"
        onAction={() =>
          void navigate(`/sessions/${course.data.current_session?.id}`)
        }
      />
    )
  }

  return (
    <section
      className="class-create-page"
      aria-labelledby="session-create-title"
    >
      <PageHeader
        eyebrow="CLASS_CREATE_PAGE · New class"
        title="오늘의 class 준비"
        titleId="session-create-title"
        description={`${course.data.title}에 READY class를 만들고 선택적으로 PDF를 준비합니다.`}
        actions={
          <LinkButton variant="ghost" to={`/courses/${courseId}`}>
            Course로 돌아가기
          </LinkButton>
        }
      />

      <div className="class-create-layout">
        <form
          className="ui-card ui-card--elevated class-create-form"
          aria-busy={create.isPending}
          noValidate
          onSubmit={submit}
        >
          <div className="class-ready-step-heading">
            <span aria-hidden="true">1</span>
            <div>
              <p className="eyebrow">Class information</p>
              <h2>기본 정보 입력</h2>
              <p>날짜는 필수이며 제목은 서버 자동 제목을 사용할 수 있습니다.</p>
            </div>
          </div>

          <div className="class-create-fields">
            <Field
              htmlFor={titleId}
              label="class 제목 (선택)"
              hint={`비우면 ${course.data.title} · YYYY.MM.DD HH:mm 형식의 자동 제목을 사용합니다.`}
            >
              <input
                value={title}
                disabled={create.isPending}
                placeholder="예: 그래프 탐색과 최단 경로"
                onChange={(event) => {
                  setTitle(event.target.value)
                  resetRequest()
                }}
              />
            </Field>
            <Field
              htmlFor={lectureDateId}
              label="수업 날짜"
              error={fieldError ?? undefined}
              required
            >
              <input
                ref={dateInputRef}
                type="date"
                value={lectureDate}
                disabled={create.isPending}
                onChange={(event) => {
                  setLectureDate(event.target.value)
                  setFieldError(null)
                  resetRequest()
                }}
              />
            </Field>
          </div>

          <div className="class-create-note" role="note">
            <strong>한 Course에는 active class가 하나뿐입니다.</strong>
            <p>
              READY, LIVE, PROCESSING class가 있으면 새 class 요청은 거부됩니다.
            </p>
          </div>

          {create.isError && (
            <div
              className="course-form-alert"
              ref={requestErrorRef}
              role="alert"
              tabIndex={-1}
            >
              <strong>
                {create.error instanceof ApiError &&
                create.error.code === 'ACTIVE_SESSION_EXISTS'
                  ? '다른 탭에서 class가 만들어졌습니다.'
                  : 'class를 만들지 못했습니다.'}
              </strong>
              <p>
                {create.error instanceof ApiError &&
                create.error.code === 'ACTIVE_SESSION_EXISTS'
                  ? 'Course의 최신 active class를 확인해 주세요.'
                  : '입력은 유지되며 같은 요청으로 다시 시도할 수 있습니다.'}
              </p>
            </div>
          )}

          <div className="class-create-form__footer">
            <p>생성 직후 READY 준비 화면으로 이동합니다.</p>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? 'class 만드는 중…' : 'class 만들기'}
            </Button>
          </div>
        </form>

        <aside className="class-create-guide" aria-label="class 준비 순서">
          <Card>
            <p className="eyebrow">Preparation flow</p>
            <h2>생성 후 이어서 할 일</h2>
            <ol>
              <li>
                <span>1</span>
                READY class 생성
              </li>
              <li>
                <span>2</span>
                선택적으로 PDF 업로드
              </li>
              <li>
                <span>3</span>
                자료 상태 확인 후 수업 시작
              </li>
            </ol>
          </Card>
          <Card className="class-create-guide__note">
            <strong>PDF가 없어도 괜찮습니다.</strong>
            <p>
              처리 중인 PDF만 시작을 막고, READY 자료만 AI 근거로 사용합니다.
            </p>
          </Card>
        </aside>
      </div>
    </section>
  )
}
