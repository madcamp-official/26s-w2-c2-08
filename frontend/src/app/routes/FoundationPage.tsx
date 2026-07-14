import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { ApiError } from '../../api/errors'
import { HealthStatus } from '../../features/health/HealthStatus'
import { currentUserQueryOptions } from '../../features/auth/queries'

export function FoundationPage() {
  const currentUser = useQuery(currentUserQueryOptions)
  const authenticated = currentUser.isSuccess
  const unauthenticated =
    currentUser.error instanceof ApiError && currentUser.error.status === 401

  return (
    <div className="foundation-grid">
      <section className="foundation-hero" aria-labelledby="page-title">
        <p className="eyebrow">God Of All Lectures</p>
        <h1 className="page-title" id="page-title">
          강의의 흐름을 놓치지 않도록
        </h1>
        <p className="page-description">
          익명 질문과 실시간 학습 지원, 수업 기록 기반 복습을 하나의 흐름으로
          연결합니다.
        </p>
        <div className="foundation-actions">
          {authenticated && (
            <>
              <span className="auth-greeting">
                {currentUser.data.display_name}님, 다시 오신 것을 환영합니다.
              </span>
              <Link className="button button--primary" to="/account">
                내 정보 보기
              </Link>
            </>
          )}
          {unauthenticated && (
            <Link className="button button--primary" to="/login?return_to=/">
              Google로 시작하기
            </Link>
          )}
          {currentUser.isPending && (
            <span role="status">로그인 상태 확인 중…</span>
          )}
          {currentUser.isError && !unauthenticated && (
            <button
              className="button button--secondary"
              type="button"
              onClick={() => void currentUser.refetch()}
            >
              로그인 상태 다시 확인
            </button>
          )}
        </div>
      </section>

      <aside className="panel foundation-status" aria-labelledby="status-title">
        <div>
          <p className="eyebrow">System status</p>
          <h2 id="status-title">서비스 준비 상태</h2>
          <p>화면 기능을 시작하기 전에 API 연결 상태를 확인합니다.</p>
        </div>
        <HealthStatus />
      </aside>
    </div>
  )
}
