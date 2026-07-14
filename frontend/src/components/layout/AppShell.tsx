import type { ReactNode } from 'react'
import { Link, Outlet } from 'react-router-dom'

interface AppShellProps {
  children?: ReactNode
  standalone?: boolean
}

export function AppShell({ children, standalone = false }: AppShellProps) {
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
              <small>God Of All Lectures</small>
            </span>
          </Link>
          <span className="badge">Frontend foundation</span>
        </div>
      </header>
      <main className="container page-main" id="main-content" tabIndex={-1}>
        {standalone ? children : <Outlet />}
      </main>
    </div>
  )
}
