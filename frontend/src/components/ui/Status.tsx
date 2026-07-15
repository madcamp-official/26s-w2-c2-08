import type { HTMLAttributes, ReactNode } from 'react'

export type StatusTone = 'neutral' | 'info' | 'success' | 'warning' | 'danger'

interface StatusProps extends HTMLAttributes<HTMLSpanElement> {
  children: ReactNode
  tone?: StatusTone
}

export function Status({
  children,
  className = '',
  tone = 'neutral',
  ...props
}: StatusProps) {
  return (
    <span
      className={['ui-status', `ui-status--${tone}`, className]
        .filter(Boolean)
        .join(' ')}
      {...props}
    >
      <span className="ui-status__dot" aria-hidden="true" />
      {children}
    </span>
  )
}
