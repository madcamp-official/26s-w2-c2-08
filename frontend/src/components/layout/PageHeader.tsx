import type { ReactNode } from 'react'

interface PageHeaderProps {
  actions?: ReactNode
  description?: ReactNode
  eyebrow?: string
  title: string
}

export function PageHeader({
  actions,
  description,
  eyebrow,
  title,
}: PageHeaderProps) {
  return (
    <header className="ui-page-header">
      <div className="ui-page-header__copy">
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {description && (
          <div className="ui-page-header__description">{description}</div>
        )}
      </div>
      {actions && <div className="ui-page-header__actions">{actions}</div>}
    </header>
  )
}
