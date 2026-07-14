import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Button } from '../ui/Button'
import { ToastProvider } from './ToastProvider'
import { useToast } from './toast-context'

function ToastExample() {
  const { showToast } = useToast()
  return (
    <Button
      onClick={() =>
        showToast({ message: '저장되었습니다.', tone: 'success', duration: 0 })
      }
    >
      알림 표시
    </Button>
  )
}

describe('ToastProvider', () => {
  it('announces feedback in a live region', () => {
    render(
      <ToastProvider>
        <ToastExample />
      </ToastProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: '알림 표시' }))

    expect(screen.getByRole('status', { name: '' })).toHaveTextContent(
      '저장되었습니다.',
    )
  })
})
