import { useMutation, useQueryClient } from '@tanstack/react-query'
import { type ClipboardEvent, type FormEvent, useRef, useState } from 'react'

import { ApiError } from '../../api/errors'
import { CourseRoleBadge } from '../../components/domain/LmsStatus'
import { useToast } from '../../components/feedback/toast-context'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/Button'
import { Field } from '../../components/ui/Field'
import { LinkButton } from '../../components/ui/LinkButton'
import { Status } from '../../components/ui/Status'
import { currentUserQueryKey } from '../auth/queries'
import { joinCourse } from './api'
import {
  CourseFlowGuide,
  CourseFlowResult,
  CourseMutationExpiredState,
} from './CourseOnboarding'
import { courseKeys } from './queries'

export function CourseJoinPage() {
  const [joinCode, setJoinCode] = useState('')
  const [fieldError, setFieldError] = useState<string | null>(null)
  const idempotencyKey = useRef<string | null>(null)
  const codeInputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const join = useMutation({
    mutationFn: ({ code, key }: { code: string; key: string }) =>
      joinCourse({ join_code: code }, key),
    onSuccess: ({ course, created }) => {
      idempotencyKey.current = null
      void queryClient.invalidateQueries({ queryKey: courseKeys.all })
      queryClient.setQueryData(courseKeys.detail(course.id), course)
      showToast({
        tone: created ? 'success' : 'info',
        message: created
          ? 'Course에 참여했습니다.'
          : '기존 Course 멤버십을 확인했습니다.',
      })
    },
    onError: (error) => {
      if (error instanceof ApiError && [404, 422].includes(error.status ?? 0)) {
        setFieldError('참여 코드를 확인해 주세요.')
        codeInputRef.current?.focus()
        showToast({ tone: 'error', message: '참여 코드를 확인해 주세요.' })
        return
      }
      if (error instanceof ApiError && error.code === 'MEMBERSHIP_CONFLICT') {
        showToast({
          tone: 'warning',
          message: '이 Course의 교수자 역할을 그대로 유지합니다.',
        })
      }
    },
  })

  function updateCode(value: string) {
    setJoinCode(value.trim().toUpperCase())
    setFieldError(null)
    idempotencyKey.current = null
    if (join.isError) join.reset()
  }

  function pasteCode(event: ClipboardEvent<HTMLInputElement>) {
    event.preventDefault()
    updateCode(event.clipboardData.getData('text'))
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (join.isPending) return
    const normalized = joinCode.trim().toUpperCase()
    if (!/^[A-Z]{6}$/.test(normalized)) {
      setFieldError('영문 대문자 6자로 된 참여 코드를 입력해 주세요.')
      codeInputRef.current?.focus()
      showToast({
        tone: 'error',
        message: '영문 대문자 6자리 참여 코드를 입력해 주세요.',
      })
      return
    }
    idempotencyKey.current ??= crypto.randomUUID()
    join.mutate({ code: normalized, key: idempotencyKey.current })
  }

  function clearSensitiveCache() {
    queryClient.removeQueries({ queryKey: currentUserQueryKey })
    queryClient.removeQueries({ queryKey: courseKeys.all })
  }

  function resetJoinForm() {
    join.reset()
    setJoinCode('')
    setFieldError(null)
    idempotencyKey.current = null
    queueMicrotask(() => codeInputRef.current?.focus())
  }

  const joinError = join.error instanceof ApiError ? join.error : undefined
  const membershipConflict = joinError?.code === 'MEMBERSHIP_CONFLICT'

  if (joinError?.status === 401) {
    return (
      <CourseMutationExpiredState
        description="입력한 참여 코드와 Course 정보는 숨겼습니다. 다시 로그인한 뒤 참여를 계속해 주세요."
        onBeforeNavigate={clearSensitiveCache}
        returnTo="/courses/join"
      />
    )
  }

  if (join.data) {
    const { course, created } = join.data
    return (
      <CourseFlowResult
        statusLabel={created ? '참여 완료' : '이미 참여 중'}
        statusTone={created ? 'success' : 'info'}
        title={
          created
            ? `${course.title} Course에 참여했습니다`
            : '이미 참여 중인 Course입니다'
        }
        description={
          created
            ? '이 Course에서 학생 역할로 참여합니다. 다른 Course의 역할에는 영향을 주지 않습니다.'
            : '새 멤버십을 만들지 않고 기존 학생 멤버십을 확인했습니다. 현재 class와 기록을 이어서 볼 수 있습니다.'
        }
        details={[
          { label: 'Course', value: course.title },
          { label: '학기', value: course.semester },
          { label: '내 역할', value: <CourseRoleBadge role={course.role} /> },
        ]}
        actions={
          <>
            <LinkButton to={`/courses/${course.id}`}>Course로 이동</LinkButton>
            <LinkButton to="/" variant="ghost">
              대시보드로 이동
            </LinkButton>
          </>
        }
      />
    )
  }

  if (membershipConflict) {
    return (
      <CourseFlowResult
        statusLabel="교수자 역할 유지"
        statusTone="warning"
        title="교수자 역할을 그대로 유지합니다"
        description="이미 이 Course의 교수자이므로 학생 멤버십으로 변경하지 않았습니다. 대시보드에서 관리 중인 Course를 확인해 주세요."
        actions={
          <>
            <LinkButton to="/#course-professor">관리 Course 보기</LinkButton>
            <Button onClick={resetJoinForm} variant="ghost">
              다른 코드 입력
            </Button>
          </>
        }
      />
    )
  }

  if (joinError?.status === 403) {
    return (
      <CourseFlowResult
        statusLabel="요청 차단"
        statusTone="warning"
        title="Course 참여 요청을 처리할 수 없습니다"
        description="입력한 코드는 숨겼습니다. 현재 로그인과 요청 권한을 확인한 뒤 다시 시도해 주세요."
        actions={
          <>
            <Button onClick={resetJoinForm}>다시 입력</Button>
            <LinkButton to="/" variant="ghost">
              대시보드로 이동
            </LinkButton>
          </>
        }
      />
    )
  }

  const responseFieldError = [404, 422].includes(joinError?.status ?? 0)

  return (
    <section className="course-onboarding-page">
      <PageHeader
        eyebrow="COURSE_JOIN_PAGE · PRE-S-01"
        title="참여 코드로 들어가기"
        description={
          <p>
            교수자가 공유한 영문 대문자 6자리 코드를 입력하세요. 참여 후 학생
            역할은 이 Course 안에서만 적용됩니다.
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
          aria-busy={join.isPending}
        >
          <header className="course-onboarding-form__header">
            <Status tone="info">참여 코드</Status>
            <h2>Course 참여 코드를 확인합니다</h2>
            <p>코드가 올바르면 이 Course의 학생 멤버십을 안전하게 만듭니다.</p>
          </header>
          <div className="course-onboarding-fields">
            <Field
              className="course-code-field"
              htmlFor="course-join-code"
              label="참여 코드"
              hint={
                fieldError
                  ? undefined
                  : '앞뒤 공백을 제거하고 영문을 대문자로 바꿔 확인합니다.'
              }
              error={fieldError ?? undefined}
            >
              <input
                ref={codeInputRef}
                autoFocus
                autoCapitalize="characters"
                autoComplete="off"
                disabled={join.isPending}
                inputMode="text"
                maxLength={6}
                onChange={(event) => updateCode(event.target.value)}
                onPaste={pasteCode}
                placeholder="ABCDEF"
                required
                spellCheck={false}
                value={joinCode}
              />
            </Field>
          </div>
          {join.isError && !responseFieldError && (
            <div className="course-form-alert" role="alert">
              <strong>Course에 참여하지 못했습니다.</strong>
              <p>
                입력한 코드는 유지했습니다. 연결을 확인한 뒤 같은 요청으로 다시
                시도해 주세요.
              </p>
            </div>
          )}
          {join.isPending && (
            <p className="sr-only" role="status">
              참여 코드와 Course 접근 가능 여부를 확인하는 중입니다.
            </p>
          )}
          <footer className="course-onboarding-form__footer">
            <p>
              참여하면 이 Course의 <strong>학생</strong>이 됩니다.
            </p>
            <div className="form-actions">
              <LinkButton aria-disabled={join.isPending} to="/" variant="ghost">
                취소
              </LinkButton>
              <Button type="submit" disabled={join.isPending}>
                {join.isPending ? '참여 확인 중…' : 'Course 참여하기'}
              </Button>
            </div>
          </footer>
        </form>
        <CourseFlowGuide
          ariaLabel="Course 참여 안내"
          title="Course별 역할"
          steps={[
            '코드 참여자는 이 Course의 학생으로 등록됩니다.',
            '이미 학생이면 새 멤버십 없이 기존 Course로 이동합니다.',
            '기존 교수자 역할은 학생 역할로 덮어쓰지 않습니다.',
          ]}
          note="잘못되었거나 교체된 코드는 Course 정보를 노출하지 않는 같은 안내로 처리합니다."
        />
      </div>
    </section>
  )
}
