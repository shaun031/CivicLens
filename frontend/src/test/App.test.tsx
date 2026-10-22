import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
}

afterEach(() => vi.unstubAllGlobals())
const anonymous = () =>
  Promise.resolve(
    new Response(JSON.stringify({ detail: 'Authentication required.' }), {
      status: 401,
    }),
  )
beforeEach(() => vi.stubGlobal('fetch', vi.fn(anonymous)))

describe('CivicLens application', () => {
  it('renders the homepage and navigation', () => {
    renderAt('/')
    expect(screen.getByRole('heading', { name: /smarter reporting/i })).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: /main/i })).toBeInTheDocument()
    expect(
      screen.queryByRole('link', { name: /project status|development status|system status/i }),
    ).not.toBeInTheDocument()
    expect(document.querySelector('a[href="/status"]')).toBeNull()
  })

  it('returns a safe not-found page for the removed status URL without health polling', async () => {
    const fetchMock = vi.fn(anonymous)
    vi.stubGlobal('fetch', fetchMock)
    renderAt('/status')
    expect(screen.getByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Return home' })).toHaveAttribute('href', '/')
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
  })

  it('keeps mobile navigation free of removed development links', async () => {
    renderAt('/')
    await userEvent.click(screen.getByRole('button', { name: 'Toggle navigation' }))
    expect(screen.getByRole('button', { name: 'Toggle navigation' })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
    expect(document.querySelector('a[href="/status"]')).toBeNull()
    expect(screen.queryByText(/Backend connectivity|Development status|Current phase/i)).toBeNull()
  })
})
