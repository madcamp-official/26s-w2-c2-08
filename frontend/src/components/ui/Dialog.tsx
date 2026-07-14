import { type ReactNode, useEffect, useId, useRef } from 'react'

import { Button } from './Button'

interface DialogProps {
  open: boolean
  title: string
  description?: string
  children: ReactNode
  actions?: ReactNode
  onOpenChange: (open: boolean) => void
}

export function Dialog({
  open,
  title,
  description,
  children,
  actions,
  onOpenChange,
}: DialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const titleId = useId()
  const descriptionId = useId()

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return

    if (open && !dialog.open) {
      dialog.showModal()
    } else if (!open && dialog.open) {
      dialog.close()
    }
  }, [open])

  return (
    <dialog
      ref={dialogRef}
      className="dialog"
      aria-labelledby={titleId}
      aria-describedby={description ? descriptionId : undefined}
      onCancel={(event) => {
        event.preventDefault()
        onOpenChange(false)
      }}
      onClose={() => onOpenChange(false)}
    >
      <div className="dialog__header">
        <div>
          <h2 id={titleId}>{title}</h2>
          {description && <p id={descriptionId}>{description}</p>}
        </div>
        <Button
          variant="ghost"
          aria-label="대화상자 닫기"
          onClick={() => onOpenChange(false)}
        >
          닫기
        </Button>
      </div>
      <div>{children}</div>
      {actions && <div className="dialog__actions">{actions}</div>}
    </dialog>
  )
}
