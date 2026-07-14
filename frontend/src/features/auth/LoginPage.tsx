import { useQuery } from '@tanstack/react-query'
import { Navigate, useSearchParams } from 'react-router-dom'

import { ApiError } from '../../api/errors'
import { StatePanel } from '../../components/feedback/StatePanel'
import { currentUserQueryOptions } from './queries'
import { googleLoginUrl } from './api'
import { safeReturnTo } from './return-to'

export function LoginPage() {
  const [searchParams] = useSearchParams()
  const returnTo = safeReturnTo(searchParams.get('return_to'))
  const authError = searchParams.get('auth_error')
  const loggedOut = searchParams.get('logged_out') === '1'
  const currentUser = useQuery(currentUserQueryOptions)

  if (currentUser.isSuccess) {
    return <Navigate replace to={returnTo} />
  }

  const unauthenticated =
    currentUser.error instanceof ApiError && currentUser.error.status === 401

  return (
    <div className="auth-grid">
      <section className="auth-copy" aria-labelledby="login-title">
        <p className="eyebrow">Google OpenID Connect</p>
        <h1 className="page-title" id="login-title">
          강의의 흐름으로 다시 들어오세요.
        </h1>
        <p className="page-description">
          GOAL은 Google 인증 뒤 별도의 안전한 서버 Session을 발급합니다.
          교수자와 학생 역할은 계정 전체가 아니라 Course마다 결정됩니다.
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
            <a className="google-login" href={googleLoginUrl(returnTo)}>
              <span aria-hidden="true">G</span>
              Google 계정으로 계속하기
            </a>
            <p>
              로그인 후 <code>{returnTo}</code> 경로로 돌아갑니다. Google
              token과 GOAL Session ID는 브라우저 JavaScript에 저장하지 않습니다.
            </p>
          </div>
        )}
      </section>
    </div>
  )
}
