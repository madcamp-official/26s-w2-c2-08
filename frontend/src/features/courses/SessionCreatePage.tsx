import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { ApiError } from '../../api/errors'
import { StatePanel } from '../../components/feedback/StatePanel'
import { Button } from '../../components/ui/Button'
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
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const course = useQuery(courseDetailQueryOptions(courseId))
  const [title, setTitle] = useState('')
  const [lectureDate, setLectureDate] = useState(todayInSeoul)
  const [fieldError, setFieldError] = useState<string | null>(null)
  const idempotencyKey = useRef<string | null>(null)
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
      navigate(`/sessions/${created.id}`, { replace: true })
    },
  })

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!lectureDate) {
      setFieldError('수업 날짜를 선택해 주세요.')
      return
    }
    create.mutate()
  }

  if (course.isPending)
    return <StatePanel kind="loading" title="Course를 불러오는 중" />
  if (course.error instanceof ApiError && course.error.status === 403) {
    return (
      <StatePanel kind="forbidden" title="이 Course에 접근할 권한이 없습니다" />
    )
  }
  if (course.isError) {
    return (
      <StatePanel kind="error" title="Class 생성 정보를 불러오지 못했습니다" />
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
          navigate(`/sessions/${course.data.current_session?.id}`)
        }
      />
    )
  }

  return (
    <section
      className="course-form-page"
      aria-labelledby="session-create-title"
    >
      <header className="course-form-heading">
        <p className="eyebrow">New class</p>
        <h1 id="session-create-title">오늘의 class 준비</h1>
        <p>
          제목은 선택 사항입니다. 비워 두면 서버가 생성 시각(Asia/Seoul)을
          기준으로 자동 제목을 정합니다.
        </p>
      </header>
      <form className="panel course-form" onSubmit={submit} noValidate>
        <label>
          <span>class 제목 (선택)</span>
          <input
            value={title}
            onChange={(event) => {
              setTitle(event.target.value)
              idempotencyKey.current = null
            }}
            placeholder={`${course.data.title} · 자동 제목 사용`}
          />
        </label>
        <label>
          <span>수업 날짜</span>
          <input
            type="date"
            value={lectureDate}
            onChange={(event) => {
              setLectureDate(event.target.value)
              setFieldError(null)
              idempotencyKey.current = null
            }}
            aria-invalid={Boolean(fieldError)}
            aria-describedby={fieldError ? 'session-create-error' : undefined}
          />
        </label>
        {fieldError && (
          <p className="field-error" id="session-create-error" role="alert">
            {fieldError}
          </p>
        )}
        {create.isError && (
          <p className="form-error" role="alert">
            {create.error instanceof ApiError &&
            create.error.code === 'ACTIVE_SESSION_EXISTS'
              ? '다른 탭에서 class가 만들어졌습니다. Course를 다시 확인해 주세요.'
              : 'class를 만들지 못했습니다. 입력은 유지되며 다시 시도할 수 있습니다.'}
          </p>
        )}
        <div className="form-actions">
          <Button type="submit" disabled={create.isPending}>
            {create.isPending ? 'class 만드는 중…' : 'class 만들기'}
          </Button>
          <Link className="button button--ghost" to={`/courses/${courseId}`}>
            취소
          </Link>
        </div>
      </form>
    </section>
  )
}
