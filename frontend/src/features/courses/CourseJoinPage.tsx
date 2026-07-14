import { useMutation, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { ApiError } from '../../api/errors'
import { Button } from '../../components/ui/Button'
import { joinCourse } from './api'
import { courseKeys } from './queries'

export function CourseJoinPage() {
  const [joinCode, setJoinCode] = useState('')
  const [fieldError, setFieldError] = useState<string | null>(null)
  const idempotencyKey = useRef<string | null>(null)
  const queryClient = useQueryClient()
  const join = useMutation({
    mutationFn: ({ code, key }: { code: string; key: string }) =>
      joinCourse({ join_code: code }, key),
    onSuccess: ({ course }) => {
      idempotencyKey.current = null
      void queryClient.invalidateQueries({ queryKey: courseKeys.all })
      queryClient.setQueryData(courseKeys.detail(course.id), course)
    },
  })

  function updateCode(value: string) {
    setJoinCode(value.trim().toUpperCase().slice(0, 6))
    setFieldError(null)
    idempotencyKey.current = null
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const normalized = joinCode.trim().toUpperCase()
    if (!/^[A-Z]{6}$/.test(normalized)) {
      setFieldError('영문 대문자 6자로 된 참여 코드를 입력해 주세요.')
      return
    }
    idempotencyKey.current ??= crypto.randomUUID()
    join.mutate({ code: normalized, key: idempotencyKey.current })
  }

  if (join.data) {
    return (
      <section
        className="course-form-page"
        aria-labelledby="course-joined-title"
      >
        <div className="panel course-result" tabIndex={-1}>
          <span className="status-chip status-chip--success">
            {join.data.created ? '참여 완료' : '이미 참여 중'}
          </span>
          <h1 id="course-joined-title">{join.data.course.title}</h1>
          <p>{join.data.course.semester} · 학생 역할로 참여합니다.</p>
          <div className="form-actions">
            <Link
              className="button button--primary"
              to={`/courses/${join.data.course.id}`}
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

  const invalidCode =
    join.error instanceof ApiError && join.error.status === 404
  const membershipConflict =
    join.error instanceof ApiError && join.error.code === 'MEMBERSHIP_CONFLICT'

  return (
    <section className="course-form-page" aria-labelledby="course-join-title">
      <header className="course-form-heading">
        <p className="eyebrow">Join course</p>
        <h1 id="course-join-title">참여 코드로 들어가기</h1>
        <p>
          참여하면 이 Course에서 학생 역할이 생깁니다. 계정 전체 역할은 바뀌지
          않습니다.
        </p>
      </header>
      <form
        className="panel course-form course-form--code"
        onSubmit={submit}
        noValidate
      >
        <label>
          <span>참여 코드</span>
          <input
            autoFocus
            value={joinCode}
            maxLength={6}
            autoCapitalize="characters"
            autoComplete="off"
            spellCheck={false}
            placeholder="ABCDEF"
            onChange={(event) => updateCode(event.target.value)}
            aria-invalid={Boolean(fieldError || invalidCode)}
            aria-describedby={
              fieldError || invalidCode ? 'course-join-error' : undefined
            }
          />
        </label>
        {(fieldError || invalidCode) && (
          <p className="field-error" id="course-join-error" role="alert">
            {fieldError ?? '참여 코드를 확인해 주세요.'}
          </p>
        )}
        {membershipConflict && (
          <p className="form-error" role="alert">
            이미 이 Course의 교수자입니다. 교수자 역할은 학생으로 변경되지
            않습니다.
          </p>
        )}
        {join.isError && !invalidCode && !membershipConflict && (
          <p className="form-error" role="alert">
            Course에 참여하지 못했습니다. 같은 코드로 다시 시도해 주세요.
          </p>
        )}
        <div className="form-actions">
          <Button type="submit" disabled={join.isPending}>
            {join.isPending ? '참여 확인 중…' : 'Course 참여하기'}
          </Button>
          <Link className="button button--ghost" to="/">
            취소
          </Link>
        </div>
      </form>
    </section>
  )
}
