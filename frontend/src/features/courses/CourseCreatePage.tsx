import { useMutation, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useRef, useState } from 'react'

import { ApiError } from '../../api/errors'
import { CourseRoleBadge } from '../../components/domain/LmsStatus'
import { useToast } from '../../components/feedback/toast-context'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/Button'
import { Field } from '../../components/ui/Field'
import { LinkButton } from '../../components/ui/LinkButton'
import { Status } from '../../components/ui/Status'
import { currentUserQueryKey } from '../auth/queries'
import { createCourse, type CourseCreateInput } from './api'
import {
  CourseFlowGuide,
  CourseFlowResult,
  CourseMutationExpiredState,
} from './CourseOnboarding'
import { courseKeys } from './queries'

function newIdempotencyKey() {
  return crypto.randomUUID()
}

export function CourseCreatePage() {
  const [title, setTitle] = useState('')
  const [semester, setSemester] = useState('')
  const [fieldErrors, setFieldErrors] = useState<{
    semester?: string
    title?: string
  }>({})
  const idempotencyKey = useRef<string | null>(null)
  const titleInputRef = useRef<HTMLInputElement>(null)
  const semesterInputRef = useRef<HTMLInputElement>(null)
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
    setFieldErrors((current) => ({ ...current, title: undefined }))
    idempotencyKey.current = null
    if (create.isError) create.reset()
  }

  function updateSemester(value: string) {
    setSemester(value)
    setFieldErrors((current) => ({ ...current, semester: undefined }))
    idempotencyKey.current = null
    if (create.isError) create.reset()
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (create.isPending) return
    const errors = {
      title: title.trim() ? undefined : '공백이 아닌 과목명을 입력해 주세요.',
      semester: semester.trim()
        ? undefined
        : '공백이 아닌 학기를 입력해 주세요.',
    }
    if (errors.title || errors.semester) {
      setFieldErrors(errors)
      if (errors.title) titleInputRef.current?.focus()
      else semesterInputRef.current?.focus()
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

  const createError =
    create.error instanceof ApiError ? create.error : undefined

  if (createError?.status === 401) {
    return (
      <CourseMutationExpiredState
        description="입력한 Course 정보와 생성 결과는 숨겼습니다. 다시 로그인한 뒤 Course 만들기를 계속해 주세요."
        onBeforeNavigate={() => {
          queryClient.removeQueries({ queryKey: currentUserQueryKey })
          queryClient.removeQueries({ queryKey: courseKeys.all })
        }}
        returnTo="/courses/new"
      />
    )
  }

  if (create.data) {
    const joinCode = create.data.join_code
    return (
      <CourseFlowResult
        statusLabel="생성 완료"
        title={`${create.data.title} Course를 만들었습니다`}
        description={
          <>
            이 Course에서 <strong>유일한 교수자 owner</strong>가 되었습니다.
            학생에게 아래 참여 코드를 안전하게 공유해 주세요.
          </>
        }
        details={[
          { label: 'Course', value: create.data.title },
          { label: '학기', value: create.data.semester },
          {
            label: '내 역할',
            value: <CourseRoleBadge role={create.data.role} />,
          },
        ]}
        actions={
          <>
            <LinkButton to={`/courses/${create.data.id}`}>
              Course로 이동
            </LinkButton>
            <LinkButton to="/" variant="ghost">
              대시보드로 이동
            </LinkButton>
          </>
        }
      >
        <div className="course-created-code">
          <div>
            <span>학생 참여 코드</span>
            {joinCode ? (
              <strong>{joinCode}</strong>
            ) : (
              <p role="alert">참여 코드를 표시하지 못했습니다.</p>
            )}
          </div>
          <Button
            variant="secondary"
            disabled={!joinCode}
            onClick={() => joinCode && void copyCode(joinCode)}
          >
            코드 복사
          </Button>
        </div>
      </CourseFlowResult>
    )
  }

  return (
    <section className="course-onboarding-page">
      <PageHeader
        eyebrow="COURSE_CREATE_PAGE · PRE-T-01"
        title="한 학기 Course 만들기"
        description={
          <p>
            과목 정보만 입력하면 바로 수업 공간을 준비합니다. 교수자 역할은
            생성한 Course 안에서만 적용됩니다.
          </p>
        }
        actions={
          <LinkButton to="/" variant="secondary">
            대시보드
          </LinkButton>
        }
      />
      <div className="course-onboarding-layout">
        <form
          className="course-onboarding-form"
          onSubmit={submit}
          noValidate
          aria-busy={create.isPending}
        >
          <header className="course-onboarding-form__header">
            <Status tone="info">기본 정보</Status>
            <h2>학생이 알아볼 Course 정보를 입력하세요</h2>
            <p>과목명과 학기는 Course 목록과 class 화면에 함께 표시됩니다.</p>
          </header>
          <div className="course-onboarding-fields">
            <Field
              htmlFor="course-title"
              label="과목명"
              hint={
                fieldErrors.title ? undefined : '예: 데이터 구조와 알고리즘'
              }
              error={fieldErrors.title}
            >
              <input
                ref={titleInputRef}
                autoFocus
                autoComplete="off"
                value={title}
                disabled={create.isPending}
                placeholder="데이터 구조와 알고리즘"
                onChange={(event) => updateTitle(event.target.value)}
                required
              />
            </Field>
            <Field
              htmlFor="course-semester"
              label="학기"
              hint={
                fieldErrors.semester
                  ? undefined
                  : '현재 API 계약의 표시용 문자열로 저장됩니다.'
              }
              error={fieldErrors.semester}
            >
              <input
                ref={semesterInputRef}
                autoComplete="off"
                value={semester}
                disabled={create.isPending}
                placeholder="2026 여름학기"
                onChange={(event) => updateSemester(event.target.value)}
                required
              />
            </Field>
          </div>
          {create.isError && (
            <div className="course-form-alert" role="alert">
              <strong>Course를 만들지 못했습니다.</strong>
              <p>
                입력 내용은 그대로 유지했습니다. 연결을 확인한 뒤 같은 요청으로
                다시 시도해 주세요.
              </p>
            </div>
          )}
          {create.isPending && (
            <p className="sr-only" role="status">
              Course와 교수자 멤버십을 생성하는 중입니다.
            </p>
          )}
          <footer className="course-onboarding-form__footer">
            <p>
              생성하면 이 Course의 <strong>교수자 owner</strong>가 됩니다.
            </p>
            <div className="form-actions">
              <LinkButton
                aria-disabled={create.isPending}
                to="/"
                variant="ghost"
              >
                취소
              </LinkButton>
              <Button type="submit" disabled={create.isPending}>
                {create.isPending ? 'Course 만드는 중…' : 'Course 만들기'}
              </Button>
            </div>
          </footer>
        </form>
        <CourseFlowGuide
          ariaLabel="Course 생성 안내"
          title="생성 후 흐름"
          steps={[
            '생성자는 이 Course의 유일한 교수자 owner가 됩니다.',
            '서버가 영문 대문자 6자리 참여 코드를 발급합니다.',
            '학생은 코드를 입력해 이 Course에만 참여합니다.',
          ]}
          note={
            <>
              참여 코드는 교수자 화면에서만 보입니다. 필요하면 새 코드로 교체해
              이전 코드를 즉시 무효화할 수 있습니다.
            </>
          }
        />
      </div>
    </section>
  )
}
