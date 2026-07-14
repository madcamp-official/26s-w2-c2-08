import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FormEvent, useId, useState } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'

import { ApiError } from '../../api/errors'
import { StatePanel } from '../../components/feedback/StatePanel'
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
    registration.mutate({ display_name: displayName, email, password })
  }

  return (
    <div className="auth-grid">
      <section className="auth-copy" aria-labelledby="signup-title">
        <p className="eyebrow">Email account</p>
        <h1 className="page-title" id="signup-title">
          나만의 강의 흐름을 시작하세요.
        </h1>
        <p className="page-description">
          이메일 계정은 Google 로그인과 같은 안전한 서버 Session으로 동작합니다.
          교수자와 학생 역할은 Course에 참여한 뒤에만 정해집니다.
        </p>
      </section>

      <section className="panel auth-card" aria-label="이메일 계정 가입">
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
            className="auth-card__content email-auth-form"
            onSubmit={submitRegistration}
          >
            <div className="form-field">
              <label htmlFor={nameId}>표시 이름</label>
              <input
                autoComplete="name"
                id={nameId}
                maxLength={100}
                onChange={(event) => setDisplayName(event.target.value)}
                required
                value={displayName}
              />
            </div>
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
                autoComplete="new-password"
                id={passwordId}
                maxLength={128}
                minLength={12}
                onChange={(event) => setPassword(event.target.value)}
                required
                type="password"
                value={password}
              />
              <small>12자 이상 128자 이하로 입력해 주세요.</small>
            </div>
            {registration.isError && (
              <p className="auth-notice auth-notice--warning" role="alert">
                {registration.error instanceof ApiError &&
                registration.error.code === 'EMAIL_ALREADY_REGISTERED'
                  ? '이미 등록된 이메일입니다. 기존 로그인 방식을 사용해 주세요.'
                  : '계정을 만들지 못했습니다. 입력을 확인한 뒤 다시 시도해 주세요.'}
              </p>
            )}
            <button
              className="button button--primary"
              disabled={registration.isPending}
              type="submit"
            >
              {registration.isPending
                ? '계정 만드는 중…'
                : '이메일 계정 만들기'}
            </button>
            <p className="auth-switch">
              이미 계정이 있나요?{' '}
              <Link to={`/login?return_to=${encodeURIComponent(returnTo)}`}>
                로그인
              </Link>
            </p>
          </form>
        )}
      </section>
    </div>
  )
}
