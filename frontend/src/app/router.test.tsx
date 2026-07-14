import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { AppProviders } from './providers'
import { appRoutes } from './router'

describe('application router', () => {
  it('shows the common not-found state for an unknown route', () => {
    const router = createMemoryRouter(appRoutes, {
      initialEntries: ['/missing-page'],
    })

    render(
      <AppProviders>
        <RouterProvider router={router} />
      </AppProviders>,
    )

    expect(
      screen.getByRole('heading', {
        name: '요청한 페이지를 찾을 수 없습니다',
      }),
    ).toBeInTheDocument()
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })
})
