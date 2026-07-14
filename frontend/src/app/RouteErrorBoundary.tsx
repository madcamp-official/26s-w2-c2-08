import { isRouteErrorResponse, useRouteError } from 'react-router-dom'

import { AppShell } from '../components/layout/AppShell'
import {
  StatePanel,
  type StatePanelKind,
} from '../components/feedback/StatePanel'

function stateKindForStatus(status: number): StatePanelKind {
  if (status === 401) return 'unauthorized'
  if (status === 403) return 'forbidden'
  if (status === 404) return 'not-found'
  if (status === 409) return 'conflict'
  if (status === 422) return 'validation'
  return 'error'
}

export function RouteErrorBoundary() {
  const error = useRouteError()
  const kind = isRouteErrorResponse(error)
    ? stateKindForStatus(error.status)
    : 'error'

  return (
    <AppShell standalone>
      <StatePanel
        kind={kind}
        actionLabel="홈으로 이동"
        onAction={() => window.location.assign('/')}
      />
    </AppShell>
  )
}
