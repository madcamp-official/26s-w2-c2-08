import {
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'

import { ToastContext, type ToastInput, type ToastTone } from './toast-context'

interface ToastItem {
  id: string
  message: string
  tone: ToastTone
}

interface ToastProviderProps {
  children: ReactNode
}

export function ToastProvider({ children }: ToastProviderProps) {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const sequence = useRef(0)
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>())

  useEffect(
    () => () => {
      for (const timer of timers.current.values()) {
        clearTimeout(timer)
      }
      timers.current.clear()
    },
    [],
  )

  const dismissToast = useCallback((id: string) => {
    const timer = timers.current.get(id)
    if (timer) clearTimeout(timer)
    timers.current.delete(id)
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  const showToast = useCallback(
    ({ message, tone = 'info', duration = 4_000 }: ToastInput) => {
      sequence.current += 1
      const id = `toast-${sequence.current}`
      setToasts((current) => [...current, { id, message, tone }])

      if (duration > 0) {
        timers.current.set(
          id,
          setTimeout(() => dismissToast(id), duration),
        )
      }

      return id
    },
    [dismissToast],
  )

  const value = useMemo(
    () => ({ showToast, dismissToast }),
    [dismissToast, showToast],
  )

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-region" aria-live="polite" aria-label="알림">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className="toast"
            data-tone={toast.tone}
            role={toast.tone === 'error' ? 'alert' : 'status'}
          >
            <span>{toast.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
