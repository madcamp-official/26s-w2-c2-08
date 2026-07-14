export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'

export function buttonClassName(
  variant: ButtonVariant = 'primary',
  className = '',
) {
  return ['button', `button--${variant}`, className].filter(Boolean).join(' ')
}
