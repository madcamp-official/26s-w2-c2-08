import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FormEvent, useId, useState } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'

import { ApiError } from '../../api/errors'
import { StatePanel } from '../../components/feedback/StatePanel'
import { Button } from '../../components/ui/Button'
import { Field } from '../../components/ui/Field'
import { AuthPageLayout } from './AuthPageLayout'
import { registerWithEmailPassword } from './api'
import { currentUserQueryKey, currentUserQueryOptions } from './queries'
import { safeReturnTo } from './return-to'

export function SignupPage() {
  const [searchParams] = useSearchParams()
  const returnTo = safeReturnTo(searchParams.get('return_to'))
  const currentUser = useQuery(currentUserQueryOptions)
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const nameId = useId()
  const emailId = useId()
  const passwordId = useId()
  const [displayName, setDisplayName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const registration = useMutation({
    mutationFn: registerWithEmailPassword,
    onSuccess: (result) => {
      queryClient.setQueryData(currentUserQueryKey, result?.user)
      void navigate(returnTo, { replace: true })
    },
  })

  if (currentUser.isSuccess) return <Navigate replace to={returnTo} />

  const unauthenticated =
    currentUser.error instanceof ApiError && currentUser.error.status === 401

  function submitRegistration(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (registration.isPending) return
    registration.mutate({ display_name: displayName, email, password })
  }

  const emailAlreadyRegistered =
    registration.error instanceof ApiError &&
    registration.error.code === 'EMAIL_ALREADY_REGISTERED'
  const emailError = emailAlreadyRegistered
    ? '이미 등록된 이메일입니다. 기존 로그인 방식을 사용해 주세요.'
    : undefined

  return (
    <AuthPageLayout
      description="표시 이름과 이메일로 계정을 만들고, 참여하는 Course마다 교수자 또는 학생 역할로 학습을 시작하세요."
      eyebrow="Email account"
      formLabel="이메일 계정 가입"
      title="나만의 강의 흐름을 시작하세요."
      titleId="signup-title"
    >
      <div className="auth-panel__heading">
        <p className="eyebrow">Create account</p>
        <h2>이메일 계정 만들기</h2>
        <p>가입 후 같은 server Session으로 바로 시작합니다.</p>
      </div>

      <div className="auth-panel__body">
        {currentUser.isPending && (
          <StatePanel
            kind="loading"
            title="기존 로그인 확인 중"
            description="서버 Session을 확인하고 있습니다."
          />
        )}
        {currentUser.isError && !unauthenticated && (
          <StatePanel
            kind="error"
            title="로그인 상태를 확인하지 못했습니다"
            description="네트워크를 확인한 뒤 이 화면을 다시 시도해 주세요."
            actionLabel="다시 확인"
            onAction={() => void currentUser.refetch()}
          />
        )}
        {unauthenticated && (
          <form
            aria-busy={registration.isPending}
            className="auth-form auth-signup-form"
            onSubmit={submitRegistration}
          >
            <Field
              hint="Course와 강의 기록에 표시할 이름입니다."
              htmlFor={nameId}
              label="표시 이름"
            >
              <input
                autoComplete="name"
                disabled={registration.isPending}
                maxLength={100}
                minLength={1}
                onChange={(event) => {
                  setDisplayName(event.target.value)
                  if (registration.isError) registration.reset()
                }}
                required
                value={displayName}
              />
            </Field>
            <Field error={emailError} htmlFor={emailId} label="이메일">
              <input
                autoComplete="email"
                disabled={registration.isPending}
                maxLength={254}
                minLength={3}
                onChange={(event) => {
                  setEmail(event.target.value)
                  if (registration.isError) registration.reset()
                }}
                required
                type="email"
                value={email}
              />
            </Field>
            <Field
              hint="12자 이상 128자 이하로 입력해 주세요."
              htmlFor={passwordId}
              label="비밀번호"
            >
              <input
                autoComplete="new-password"
                disabled={registration.isPending}
                maxLength={128}
                minLength={12}
                onChange={(event) => {
                  setPassword(event.target.value)
                  if (registration.isError) registration.reset()
                }}
                required
                type="password"
                value={password}
              />
            </Field>
            {registration.isError && !emailAlreadyRegistered && (
              <p className="auth-notice auth-notice--warning" role="alert">
                계정을 만들지 못했습니다. 입력을 확인한 뒤 다시 시도해 주세요.
              </p>
            )}
            <Button
              className="auth-submit"
              disabled={registration.isPending}
              type="submit"
            >
              {registration.isPending
                ? '계정 만드는 중…'
                : '이메일 계정 만들기'}
            </Button>
            <p className="auth-switch">
              이미 계정이 있나요?{' '}
              <Link to={`/login?return_to=${encodeURIComponent(returnTo)}`}>
                로그인
              </Link>
            </p>
          </form>
        )}
      </div>
    </AuthPageLayout>
  )
}
