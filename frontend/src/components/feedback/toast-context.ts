import { createContext, useContext } from 'react'

export type ToastTone = 'info' | 'success' | 'warning' | 'error'

export interface ToastInput {
  message: string
  tone?: ToastTone
  duration?: number
}

export interface ToastContextValue {
  showToast: (toast: ToastInput) => string
  dismissToast: (id: string) => void
}

export const ToastContext = createContext<ToastContextValue | null>(null)

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext)
  if (!context) {
    throw new Error('useToast must be used within ToastProvider')
  }
  return context
}
