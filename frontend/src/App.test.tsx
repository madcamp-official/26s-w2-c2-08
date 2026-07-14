import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import App from './App'

describe('App', () => {
  it('shows the API health status returned through the typed client', async () => {
    render(<App />)

    expect(screen.getByText('API 상태 확인 중')).toBeInTheDocument()
    expect(await screen.findByText('API 연결 정상 · ok')).toBeInTheDocument()
  })
})
