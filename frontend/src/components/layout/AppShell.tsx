import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'

import { ApiError } from '../../api/errors'
import { currentUserQueryOptions } from '../../features/auth/queries'
import { Button } from '../ui/Button'

interface AppShellProps {
  children?: ReactNode
  standalone?: boolean
}

export function AppShell({ children, standalone = false }: AppShellProps) {
  const currentUser = useQuery(currentUserQueryOptions)
  const unauthenticated =
    currentUser.error instanceof ApiError && currentUser.error.status === 401

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        본문으로 건너뛰기
      </a>
      <header className="site-header">
        <div className="container site-header__inner">
          <Link className="brand" to="/" aria-label="GOAL 홈">
            <span className="brand__mark" aria-hidden="true">
              G
            </span>
            <span className="brand__copy">
              <strong>GOAL</strong>
              <small>Live lecture workspace</small>
            </span>
          </Link>
          <nav className="header-nav" aria-label="주요 메뉴">
            {currentUser.isSuccess ? (
              <>
                <NavLink className="header-nav__link" end to="/">
                  내 Course
                </NavLink>
                <NavLink
                  aria-label="내 정보"
                  className="header-account"
                  to="/account"
                >
                  <span className="header-account__avatar" aria-hidden="true">
                    {currentUser.data.display_name.trim().slice(0, 1) || '?'}
                  </span>
                  <span>내 정보</span>
                </NavLink>
              </>
            ) : (
              <>
                {currentUser.isPending && (
                  <span
                    className="header-nav__skeleton"
                    aria-label="로그인 상태 확인 중"
                    role="status"
                  />
                )}
                {unauthenticated && (
                  <>
                    <NavLink className="header-nav__link" to="/login">
                      로그인
                    </NavLink>
                    <Link
                      className="button button--primary header-nav__cta"
                      to="/signup"
                    >
                      이메일로 시작
                    </Link>
                  </>
                )}
                {currentUser.isError && !unauthenticated && (
                  <Button
                    className="header-nav__retry"
                    variant="ghost"
                    onClick={() => void currentUser.refetch()}
                  >
                    계정 상태 다시 확인
                  </Button>
                )}
              </>
            )}
          </nav>
        </div>
      </header>
      <main className="container page-main" id="main-content" tabIndex={-1}>
        {standalone ? children : <Outlet />}
      </main>
    </div>
  )
}
