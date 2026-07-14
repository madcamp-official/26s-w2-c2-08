import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import App from './App'

describe('App', () => {
  it('shows the public learning flow while signed out', async () => {
    render(<App />)

    expect(
      await screen.findByRole('heading', {
        name: '강의의 흐름을 놓치지 않도록',
      }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: '실시간 Transcript' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: '익명 질문' }),
    ).toBeInTheDocument()
  })
})
