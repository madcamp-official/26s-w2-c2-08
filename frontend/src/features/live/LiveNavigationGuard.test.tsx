import { fireEvent, render, screen } from '@testing-library/react'
import { createMemoryRouter, Link, RouterProvider } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { LiveNavigationGuard } from './LiveNavigationGuard'

function renderFlow(active: boolean) {
  const router = createMemoryRouter(
    [
      {
        path: '/live',
        element: (
          <>
            <h1>LIVE 화면</h1>
            <Link to="/course">Course로 돌아가기</Link>
            <LiveNavigationGuard active={active} />
          </>
        ),
      },
      { path: '/course', element: <h1>Course 화면</h1> },
    ],
    { initialEntries: ['/live'] },
  )
  render(<RouterProvider router={router} />)
}

describe('LiveNavigationGuard', () => {
  it('blocks an internal route change until the user explicitly proceeds', async () => {
    renderFlow(true)

    fireEvent.click(screen.getByRole('link', { name: 'Course로 돌아가기' }))
    expect(
      await screen.findByRole('dialog', { name: 'LIVE 수업 화면을 나갈까요?' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: 'LIVE 화면' }),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '화면에 머무르기' }))
    expect(
      screen.queryByRole('dialog', { name: 'LIVE 수업 화면을 나갈까요?' }),
    ).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('link', { name: 'Course로 돌아가기' }))
    fireEvent.click(
      await screen.findByRole('button', { name: '전송을 중단하고 이동' }),
    )
    expect(
      await screen.findByRole('heading', { name: 'Course 화면' }),
    ).toBeInTheDocument()
  })

  it('allows navigation without a dialog when media is inactive', async () => {
    renderFlow(false)

    fireEvent.click(screen.getByRole('link', { name: 'Course로 돌아가기' }))

    expect(
      await screen.findByRole('heading', { name: 'Course 화면' }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
