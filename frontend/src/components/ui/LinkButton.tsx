import type { ComponentProps, MouseEvent } from 'react'
import { Link } from 'react-router-dom'

import { buttonClassName, type ButtonVariant } from './button-class-name'

interface LinkButtonProps extends ComponentProps<typeof Link> {
  variant?: ButtonVariant
}

export function LinkButton({
  'aria-disabled': ariaDisabled,
  className = '',
  onClick,
  tabIndex,
  variant = 'primary',
  ...props
}: LinkButtonProps) {
  const disabled = ariaDisabled === true || ariaDisabled === 'true'

  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (disabled) {
      event.preventDefault()
      return
    }
    onClick?.(event)
  }

  return (
    <Link
      aria-disabled={disabled || undefined}
      className={buttonClassName(variant, className)}
      onClick={handleClick}
      tabIndex={disabled ? -1 : tabIndex}
      {...props}
    />
  )
}
