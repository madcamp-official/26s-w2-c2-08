import type { HTMLAttributes, ReactNode } from 'react'

type CardElement = 'article' | 'aside' | 'div' | 'section'

interface CardProps extends HTMLAttributes<HTMLElement> {
  as?: CardElement
  children: ReactNode
  elevated?: boolean
}

export function Card({
  as: Component = 'div',
  children,
  className = '',
  elevated = false,
  ...props
}: CardProps) {
  return (
    <Component
      className={['ui-card', elevated && 'ui-card--elevated', className]
        .filter(Boolean)
        .join(' ')}
      {...props}
    >
      {children}
    </Component>
  )
}
