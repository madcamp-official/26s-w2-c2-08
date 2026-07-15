import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FormEvent, useId, useState } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'

import { ApiError } from '../../api/errors'
import { StatePanel } from '../../components/feedback/StatePanel'
import { Button } from '../../components/ui/Button'
import { Field } from '../../components/ui/Field'
import { AuthPageLayout } from './AuthPageLayout'
import { googleLoginUrl, loginWithEmailPassword } from './api'
import { currentUserQueryKey, currentUserQueryOptions } from './queries'
import { safeReturnTo } from './return-to'

export function LoginPage() {
  const [searchParams] = useSearchParams()
  const returnTo = safeReturnTo(searchParams.get('return_to'))
  const authError = searchParams.get('auth_error')
  const loggedOut = searchParams.get('logged_out') === '1'
  const withdrawn = searchParams.get('withdrawn') === '1'
  const currentUser = useQuery(currentUserQueryOptions)
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const emailId = useId()
  const passwordId = useId()
  const formErrorId = useId()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const login = useMutation({
    mutationFn: loginWithEmailPassword,
    onSuccess: (result) => {
      queryClient.setQueryData(currentUserQueryKey, result?.user)
      void navigate(returnTo, { replace: true })
    },
  })

  if (currentUser.isSuccess) {
    return <Navigate replace to={returnTo} />
  }

  const unauthenticated =
    currentUser.error instanceof ApiError && currentUser.error.status === 401

  function submitEmailLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (login.isPending) return
    login.mutate({ email, password })
  }

  const invalidCredentials =
    login.error instanceof ApiError &&
    login.error.code === 'INVALID_CREDENTIALS'
  const loginErrorMessage = invalidCredentials
    ? '이메일 또는 비밀번호가 올바르지 않습니다.'
    : '로그인하지 못했습니다. 잠시 후 다시 시도해 주세요.'

  return (
    <AuthPageLayout
      description="Google 또는 이메일 계정으로 로그인하고, Course마다 정해진 역할과 강의 기록을 이어서 확인하세요."
      eyebrow="GOAL account"
      formLabel="로그인"
      title="강의의 흐름으로 다시 들어오세요."
      titleId="login-title"
    >
      <div className="auth-panel__heading">
        <p className="eyebrow">Welcome back</p>
        <h2>로그인</h2>
        <p>사용할 로그인 방식을 선택하세요.</p>
      </div>

      <div className="auth-panel__body">
        {currentUser.isPending && (
          <StatePanel
            kind="loading"
            title="기존 로그인 확인 중"
            description="남아 있는 서버 Session을 확인하고 있습니다."
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
          <div className="auth-form-stack">
            {authError === 'cancelled' && (
              <p className="auth-notice auth-notice--warning" role="alert">
                Google 로그인이 취소되었습니다. 준비되면 다시 시도해 주세요.
              </p>
            )}
            {loggedOut && (
              <p className="auth-notice" role="status">
                안전하게 로그아웃했습니다.
              </p>
            )}
            {withdrawn && (
              <p className="auth-notice" role="status">
                계정을 탈퇴했습니다. 다시 이용하려면 새 계정으로 로그인하세요.
              </p>
            )}
            <form
              aria-busy={login.isPending}
              className="auth-form"
              onSubmit={submitEmailLogin}
            >
              <Field htmlFor={emailId} label="이메일">
                <input
                  aria-describedby={
                    invalidCredentials ? formErrorId : undefined
                  }
                  aria-invalid={invalidCredentials}
                  autoComplete="email"
                  disabled={login.isPending}
                  onChange={(event) => {
                    setEmail(event.target.value)
                    if (login.isError) login.reset()
                  }}
                  required
                  type="email"
                  value={email}
                />
              </Field>
              <Field htmlFor={passwordId} label="비밀번호">
                <input
                  aria-describedby={
                    invalidCredentials ? formErrorId : undefined
                  }
                  aria-invalid={invalidCredentials}
                  autoComplete="current-password"
                  disabled={login.isPending}
                  maxLength={128}
                  minLength={1}
                  onChange={(event) => {
                    setPassword(event.target.value)
                    if (login.isError) login.reset()
                  }}
                  required
                  type="password"
                  value={password}
                />
              </Field>
              {login.isError && (
                <p
                  className="auth-notice auth-notice--warning"
                  id={formErrorId}
                  role="alert"
                >
                  {loginErrorMessage}
                </p>
              )}
              <Button
                className="auth-submit"
                disabled={login.isPending}
                type="submit"
              >
                {login.isPending ? '로그인 중…' : '이메일로 로그인'}
              </Button>
            </form>
            <p className="auth-switch">
              계정이 없나요?{' '}
              <Link to={`/signup?return_to=${encodeURIComponent(returnTo)}`}>
                이메일 계정 만들기
              </Link>
            </p>
            <div className="auth-divider" role="separator">
              또는
            </div>
            <a className="google-login" href={googleLoginUrl(returnTo)}>
              <span aria-hidden="true">G</span>
              Google 계정으로 계속하기
            </a>
          </div>
        )}
      </div>
    </AuthPageLayout>
  )
}
