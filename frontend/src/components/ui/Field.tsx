import { cloneElement, type ReactElement } from 'react'

interface FieldControlProps {
  'aria-describedby'?: string
  'aria-invalid'?: boolean
  'aria-required'?: boolean
  id?: string
  required?: boolean
}

interface FieldProps {
  children: ReactElement<FieldControlProps>
  className?: string
  error?: string
  hint?: string
  htmlFor: string
  label: string
  required?: boolean
}

export function Field({
  children,
  className = '',
  error,
  hint,
  htmlFor,
  label,
  required = false,
}: FieldProps) {
  const descriptionId = hint || error ? `${htmlFor}-description` : undefined
  const describedBy = [children.props['aria-describedby'], descriptionId]
    .filter(Boolean)
    .join(' ')
  const control = cloneElement(children, {
    'aria-describedby': describedBy || undefined,
    'aria-invalid': error ? true : children.props['aria-invalid'],
    'aria-required': required || children.props['aria-required'],
    id: htmlFor,
    required: required || children.props.required,
  })

  return (
    <div
      className={['ui-field', error && 'ui-field--error', className]
        .filter(Boolean)
        .join(' ')}
    >
      <label htmlFor={htmlFor}>
        {label}
        {required && <span aria-hidden="true"> *</span>}
      </label>
      {control}
      {descriptionId && (
        <p id={descriptionId} role={error ? 'alert' : undefined}>
          {error ?? hint}
        </p>
      )}
    </div>
  )
}
