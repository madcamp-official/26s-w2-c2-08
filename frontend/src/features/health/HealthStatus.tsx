import { useQuery } from '@tanstack/react-query'

import { StatePanel } from '../../components/feedback/StatePanel'
import { healthQueryOptions } from './queries'

export function HealthStatus() {
  const health = useQuery(healthQueryOptions)

  if (health.isPending) {
    return <StatePanel kind="loading" title="API 상태 확인 중" />
  }

  if (health.isError) {
    return (
      <StatePanel
        kind="error"
        title="API에 연결할 수 없습니다"
        actionLabel="다시 시도"
        onAction={() => void health.refetch()}
      />
    )
  }

  return (
    <p className="status-chip status-chip--success" role="status">
      API 연결 정상 · {health.data.status}
    </p>
  )
}
