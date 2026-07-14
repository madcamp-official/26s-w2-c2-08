import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'

import { Button } from './Button'
import { Dialog } from './Dialog'

function DialogExample() {
  const [open, setOpen] = useState(false)

  return (
    <>
      <Button onClick={() => setOpen(true)}>열기</Button>
      <Dialog
        open={open}
        title="Course 만들기"
        description="새 Course 정보를 입력합니다."
        onOpenChange={setOpen}
      >
        <label>
          Course 이름
          <input name="course-name" />
        </label>
      </Dialog>
    </>
  )
}

describe('Dialog', () => {
  it('uses a modal dialog and closes from its accessible close button', () => {
    render(<DialogExample />)

    fireEvent.click(screen.getByRole('button', { name: '열기' }))
    expect(screen.getByRole('dialog')).toHaveAttribute('open')
    expect(screen.getByRole('heading', { name: 'Course 만들기' })).toBeVisible()

    fireEvent.click(screen.getByRole('button', { name: '대화상자 닫기' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
