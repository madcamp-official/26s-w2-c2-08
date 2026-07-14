import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Navigate, useLocation } from 'react-router-dom'

import { ApiError } from '../../api/errors'
import { StatePanel } from '../../components/feedback/StatePanel'
import { currentUserQueryOptions } from '../auth/queries'

export function AuthenticatedCourseArea({ children }: { children: ReactNode }) {
  const currentUser = useQuery(currentUserQueryOptions)
  const location = useLocation()

  if (currentUser.isPending) {
    return <StatePanel kind="loading" title="로그인 상태를 확인하는 중" />
  }
  if (
    currentUser.error instanceof ApiError &&
    currentUser.error.status === 401
  ) {
    const returnTo = `${location.pathname}${location.search}${location.hash}`
    return (
      <Navigate
        replace
        to={`/login?return_to=${encodeURIComponent(returnTo)}`}
      />
    )
  }
  if (currentUser.isError) {
    return (
      <StatePanel
        kind="error"
        title="로그인 상태를 확인하지 못했습니다"
        actionLabel="다시 시도"
        onAction={() => void currentUser.refetch()}
      />
    )
  }
  return children
}
