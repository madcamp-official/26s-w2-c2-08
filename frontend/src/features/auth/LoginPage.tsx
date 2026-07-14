import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FormEvent, useId, useState } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'

import { ApiError } from '../../api/errors'
import { StatePanel } from '../../components/feedback/StatePanel'
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
    login.mutate({ email, password })
  }

  return (
    <div className="auth-grid">
      <section className="auth-copy" aria-labelledby="login-title">
        <p className="eyebrow">GOAL account</p>
        <h1 className="page-title" id="login-title">
          강의의 흐름으로 다시 들어오세요.
        </h1>
        <p className="page-description">
          GOAL은 Google 또는 이메일 로그인 뒤 별도의 안전한 서버 Session을
          발급합니다. 교수자와 학생 역할은 계정 전체가 아니라 Course마다
          결정됩니다.
        </p>
      </section>

      <section className="panel auth-card" aria-label="로그인">
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
          <div className="auth-card__content">
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
            <form className="email-auth-form" onSubmit={submitEmailLogin}>
              <div className="form-field">
                <label htmlFor={emailId}>이메일</label>
                <input
                  autoComplete="email"
                  id={emailId}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                  type="email"
                  value={email}
                />
              </div>
              <div className="form-field">
                <label htmlFor={passwordId}>비밀번호</label>
                <input
                  autoComplete="current-password"
                  id={passwordId}
                  maxLength={128}
                  minLength={1}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  type="password"
                  value={password}
                />
              </div>
              {login.isError && (
                <p className="auth-notice auth-notice--warning" role="alert">
                  {login.error instanceof ApiError &&
                  login.error.code === 'INVALID_CREDENTIALS'
                    ? '이메일 또는 비밀번호가 올바르지 않습니다.'
                    : '로그인하지 못했습니다. 잠시 후 다시 시도해 주세요.'}
                </p>
              )}
              <button
                className="button button--primary"
                disabled={login.isPending}
                type="submit"
              >
                {login.isPending ? '로그인 중…' : '이메일로 로그인'}
              </button>
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
            <p>
              로그인 후 <code>{returnTo}</code> 경로로 돌아갑니다. Google token,
              비밀번호와 GOAL Session ID는 브라우저 JavaScript에 저장하지
              않습니다.
            </p>
          </div>
        )}
      </section>
    </div>
  )
}
