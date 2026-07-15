import type { ReactNode } from 'react'

interface PartialFailurePanelProps {
  actions?: ReactNode
  description: string
  title: string
}

export function PartialFailurePanel({
  actions,
  description,
  title,
}: PartialFailurePanelProps) {
  return (
    <section className="partial-failure" role="alert">
      <span className="partial-failure__icon" aria-hidden="true">
        !
      </span>
      <div className="partial-failure__copy">
        <h3>{title}</h3>
        <p>{description}</p>
      </div>
      {actions && <div className="partial-failure__actions">{actions}</div>}
    </section>
  )
}
