import { useMutation, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { useToast } from '../../components/feedback/toast-context'
import { Button } from '../../components/ui/Button'
import { createCourse, type CourseCreateInput } from './api'
import { courseKeys } from './queries'

function newIdempotencyKey() {
  return crypto.randomUUID()
}

export function CourseCreatePage() {
  const [title, setTitle] = useState('')
  const [semester, setSemester] = useState('')
  const [fieldError, setFieldError] = useState<string | null>(null)
  const idempotencyKey = useRef<string | null>(null)
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const create = useMutation({
    mutationFn: ({ input, key }: { input: CourseCreateInput; key: string }) =>
      createCourse(input, key),
    onSuccess: (course) => {
      idempotencyKey.current = null
      void queryClient.invalidateQueries({ queryKey: courseKeys.all })
      queryClient.setQueryData(courseKeys.detail(course.id), course)
    },
  })

  function updateTitle(value: string) {
    setTitle(value)
    setFieldError(null)
    idempotencyKey.current = null
  }

  function updateSemester(value: string) {
    setSemester(value)
    setFieldError(null)
    idempotencyKey.current = null
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!title.trim() || !semester.trim()) {
      setFieldError('과목명과 학기를 모두 입력해 주세요.')
      return
    }
    idempotencyKey.current ??= newIdempotencyKey()
    create.mutate({
      input: { title: title.trim(), semester: semester.trim() },
      key: idempotencyKey.current,
    })
  }

  async function copyCode(code: string) {
    try {
      await navigator.clipboard.writeText(code)
      showToast({ tone: 'success', message: '참여 코드를 복사했습니다.' })
    } catch {
      showToast({ tone: 'error', message: '참여 코드를 복사하지 못했습니다.' })
    }
  }

  if (create.data) {
    return (
      <section
        className="course-form-page"
        aria-labelledby="course-created-title"
      >
        <div className="panel course-result" tabIndex={-1}>
          <span className="status-chip status-chip--success">생성 완료</span>
          <h1 id="course-created-title">{create.data.title}</h1>
          <p>{create.data.semester} · 이 Course의 유일한 교수자 owner입니다.</p>
          <div className="join-code-box">
            <span>학생 참여 코드</span>
            <strong>{create.data.join_code}</strong>
            <Button
              variant="secondary"
              onClick={() => void copyCode(create.data.join_code ?? '')}
            >
              코드 복사
            </Button>
          </div>
          <div className="form-actions">
            <Link
              className="button button--primary"
              to={`/courses/${create.data.id}`}
            >
              Course로 이동
            </Link>
            <Link className="button button--ghost" to="/">
              대시보드로 이동
            </Link>
          </div>
        </div>
      </section>
    )
  }

  return (
    <section className="course-form-page" aria-labelledby="course-create-title">
      <header className="course-form-heading">
        <p className="eyebrow">Create course</p>
        <h1 id="course-create-title">한 학기 Course 만들기</h1>
        <p>
          생성한 Course에서만 교수자 역할이 생기며, Course당 교수자는 한
          명입니다.
        </p>
      </header>
      <form className="panel course-form" onSubmit={submit} noValidate>
        <label>
          <span>과목명</span>
          <input
            autoFocus
            value={title}
            onChange={(event) => updateTitle(event.target.value)}
            aria-invalid={Boolean(fieldError)}
            aria-describedby={fieldError ? 'course-create-error' : undefined}
          />
        </label>
        <label>
          <span>학기</span>
          <input
            value={semester}
            onChange={(event) => updateSemester(event.target.value)}
            placeholder="예: 2026 여름학기"
            aria-invalid={Boolean(fieldError)}
            aria-describedby={fieldError ? 'course-create-error' : undefined}
          />
        </label>
        {fieldError && (
          <p className="field-error" id="course-create-error" role="alert">
            {fieldError}
          </p>
        )}
        {create.isError && (
          <p className="form-error" role="alert">
            Course를 만들지 못했습니다. 입력은 유지됐으며 같은 요청으로 다시
            시도할 수 있습니다.
          </p>
        )}
        <div className="form-actions">
          <Button type="submit" disabled={create.isPending}>
            {create.isPending ? 'Course 만드는 중…' : 'Course 만들기'}
          </Button>
          <Link className="button button--ghost" to="/">
            취소
          </Link>
        </div>
      </form>
    </section>
  )
}
