import { StatePanel } from '../../components/feedback/StatePanel'

export function NotFoundPage() {
  return (
    <StatePanel
      kind="not-found"
      actionLabel="홈으로 이동"
      onAction={() => window.location.assign('/')}
    />
  )
}
