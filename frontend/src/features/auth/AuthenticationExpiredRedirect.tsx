import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

import { StatePanel } from '../../components/feedback/StatePanel'

export function AuthenticationExpiredRedirect({
  returnTo,
}: {
  returnTo: string
}) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  useEffect(() => {
    queryClient.removeQueries()
    void navigate(`/login?return_to=${encodeURIComponent(returnTo)}`, {
      replace: true,
    })
  }, [navigate, queryClient, returnTo])

  return <StatePanel kind="loading" title="로그인 화면으로 이동하는 중" />
}
