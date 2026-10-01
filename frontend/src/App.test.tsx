import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

describe('client-only color themes', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('changes the page palette without making a backend request', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      const body = path === '/api/history' ? [] : { status: 'ok' }
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    const { container } = render(<App />)
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    const callsBeforeThemeChange = fetchMock.mock.calls.length

    fireEvent.click(screen.getByRole('button', { name: '海洋配色' }))

    expect(container.querySelector('.app-shell')).toHaveAttribute('data-theme', 'ocean')
    expect(fetchMock).toHaveBeenCalledTimes(callsBeforeThemeChange)
  })
})
