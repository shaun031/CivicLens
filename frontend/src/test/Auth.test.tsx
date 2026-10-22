import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import type { Principal, Role } from '../auth/types'
import { safeDestination } from '../auth/types'

const profile = (role: Role = 'CITIZEN'): Principal => ({
  id: 'test-user',
  email: 'user@example.com',
  display_name: 'Test User',
  role,
  provider: 'local',
  is_active: true,
  is_verified: true,
  is_authenticated: true,
})
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
const anonymous = () => json({ detail: 'Authentication required.' }, 401)

function setup(
  path: string,
  user: Principal | null = null,
  handler?: (url: string, init?: RequestInit) => Response,
) {
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    if (handler) return handler(url, init)
    if (url.endsWith('/auth/me')) return user ? json(user) : anonymous()
    if (url.includes('/portal/')) return json({ message: 'Access granted' })
    return json({})
  })
  vi.stubGlobal('fetch', fetch)
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
  return fetch
}
afterEach(() => {
  vi.unstubAllGlobals()
  window.history.replaceState({}, '', '/')
})

describe('Authentication UI and guards', () => {
  it('renders accessible login controls and password visibility', async () => {
    setup('/login')
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    expect(screen.getByLabelText('Email')).toHaveAttribute('type', 'email')
    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password')
    await userEvent.click(screen.getByRole('button', { name: 'Show password' }))
    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'text')
  })
  it('renders registration without any role selector and validates password confirmation', async () => {
    const fetch = setup('/register')
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Display name'), 'Test Citizen')
    await userEvent.type(screen.getByLabelText('Email'), 'citizen@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'long test passphrase')
    await userEvent.type(screen.getByLabelText('Confirm password'), 'different test passphrase')
    await userEvent.click(screen.getByRole('button', { name: 'Create citizen account' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Passwords must match')
    expect(fetch.mock.calls.some(([url]) => url.endsWith('/auth/register'))).toBe(false)
  })
  it('registers a citizen and confirms that sign-in is needed', async () => {
    setup('/register', null, (url) =>
      url.endsWith('/auth/me') ? anonymous() : json(profile(), 201),
    )
    for (const [label, value] of [
      ['Display name', 'Citizen'],
      ['Email', 'citizen@example.com'],
      ['Password', 'long test passphrase'],
      ['Confirm password', 'long test passphrase'],
    ])
      await userEvent.type(screen.getByLabelText(label), value)
    await userEvent.click(screen.getByRole('button', { name: 'Create citizen account' }))
    expect(
      await screen.findByText('Citizen account created. You can now sign in.'),
    ).toBeInTheDocument()
  })
  it('redirects an unauthenticated user to login and returns to the intended destination', async () => {
    let signedIn = false
    const fetch = setup('/citizen/dashboard', null, (url) => {
      if (url.endsWith('/auth/login')) {
        signedIn = true
        return json(profile())
      }
      if (url.endsWith('/auth/me')) return signedIn ? json(profile()) : anonymous()
      return json({ message: 'Access granted' })
    })
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Email'), 'citizen@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'long test passphrase')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('heading', { name: 'Citizen dashboard' })).toBeInTheDocument()
    expect(fetch.mock.calls.find(([url]) => url.endsWith('/auth/login'))?.[1]?.credentials).toBe(
      'include',
    )
  })
  it('shows a generic wrong-credential error', async () => {
    setup('/login', null, (url) =>
      url.endsWith('/auth/me') ? anonymous() : json({ detail: 'Invalid email or password.' }, 401),
    )
    await userEvent.type(screen.getByLabelText('Email'), 'citizen@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'incorrect')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password.')
  })
  it.each(['CITIZEN', 'OFFICER'] as const)('blocks %s from administrator routes', async (role) => {
    setup('/admin/dashboard', profile(role))
    expect(await screen.findByRole('heading', { name: 'Access denied' })).toBeInTheDocument()
    expect(
      screen.queryByRole('heading', { name: 'Administrator dashboard' }),
    ).not.toBeInTheDocument()
  })
  it('restores an administrator session on refresh and verifies the portal API', async () => {
    const fetch = setup('/admin/dashboard', profile('ADMIN'))
    expect(screen.getByText('Restoring your session…')).toBeInTheDocument()
    expect(
      await screen.findByRole('heading', { name: 'Administrator dashboard' }),
    ).toBeInTheDocument()
    expect(await screen.findByText('Access verified by the backend.')).toBeInTheDocument()
    expect(fetch.mock.calls.some(([url]) => url.endsWith('/portal/admin'))).toBe(true)
  })
  it('clears the current session after logout', async () => {
    setup('/profile', profile(), (url) =>
      url.endsWith('/auth/me') ? json(profile()) : new Response(null, { status: 204 }),
    )
    await screen.findByRole('heading', { name: 'Your profile' })
    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })
  it('handles a session-expiry event without exposing protected content', async () => {
    setup('/admin/dashboard', profile('ADMIN'))
    await screen.findByRole('heading', { name: 'Administrator dashboard' })
    fireEvent(window, new Event('civiclens:session-expired'))
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })
  it('sends only the editable display name for profile changes', async () => {
    const fetch = setup('/profile', profile(), (url) =>
      url.endsWith('/profile') ? json({ ...profile(), display_name: 'Updated' }) : json(profile()),
    )
    const input = await screen.findByLabelText('Display name')
    await userEvent.clear(input)
    await userEvent.type(input, 'Updated')
    await userEvent.click(screen.getByRole('button', { name: 'Save profile' }))
    expect(await screen.findByText('Profile updated.')).toBeInTheDocument()
    expect(
      JSON.parse(fetch.mock.calls.find(([url]) => url.endsWith('/profile'))?.[1]?.body as string),
    ).toEqual({ display_name: 'Updated' })
  })
  it('shows portal API errors', async () => {
    setup('/citizen/dashboard', profile(), (url) =>
      url.endsWith('/auth/me')
        ? json(profile())
        : json({ detail: 'Portal temporarily unavailable.' }, 503),
    )
    expect(await screen.findByRole('alert')).toHaveTextContent('Portal temporarily unavailable.')
  })
  it.each(['/forgot-password', '/reset-password'])(
    'renders accessible recovery controls at %s',
    async (path) => {
      setup(path)
      expect(screen.getByRole('heading', { name: /password/i })).toBeInTheDocument()
      if (path === '/forgot-password') expect(screen.getByLabelText('Email')).toBeInTheDocument()
      else expect(screen.getByLabelText('New password')).toBeInTheDocument()
    },
  )
  it('requests a local reset without claiming email delivery', async () => {
    setup('/forgot-password', null, (url) =>
      url.endsWith('/auth/me')
        ? anonymous()
        : json(
            {
              message: 'A link is in the private local outbox. No email was sent.',
            },
            202,
          ),
    )
    await userEvent.type(screen.getByLabelText('Email'), 'citizen@example.com')
    await userEvent.click(screen.getByRole('button', { name: 'Request reset link' }))
    expect(await screen.findByRole('status')).toHaveTextContent('No email was sent.')
  })
  it('submits a reset link from the URL fragment and removes it from the address bar', async () => {
    window.history.replaceState({}, '', '/reset-password#token=local-test-reset-token')
    setup('/reset-password', null, (url) =>
      url.endsWith('/auth/me')
        ? anonymous()
        : json({ message: 'Password reset. Sign in with your new password.' }),
    )
    await waitFor(() => expect(window.location.hash).toBe(''))
    await userEvent.type(screen.getByLabelText('New password'), 'long test passphrase')
    await userEvent.type(screen.getByLabelText('Confirm password'), 'long test passphrase')
    await userEvent.click(screen.getByRole('button', { name: 'Reset password' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Password reset.')
  })
  it('rejects unsafe post-login destinations', () => {
    for (const value of ['https://evil.example', '//evil.example', '/\\evil.example', '\n/admin'])
      expect(safeDestination(value)).toBe('/')
    expect(safeDestination('/profile')).toBe('/profile')
  })
  it('opens the officer dashboard only after restoring the officer identity', async () => {
    setup('/officer/dashboard', profile('OFFICER'))
    expect(await screen.findByRole('heading', { name: 'Officer dashboard' })).toBeInTheDocument()
    expect(screen.getByText('Assigned incident queue')).toBeInTheDocument()
  })
  it('does not let a late session-restoration failure erase a successful login', async () => {
    let resolveRestore: (response: Response) => void = () => undefined
    const restore = new Promise<Response>((resolve) => {
      resolveRestore = resolve
    })
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.endsWith('/auth/me')) return restore
        if (url.endsWith('/auth/login')) return Promise.resolve(json(profile()))
        return Promise.resolve(json({ message: 'Access granted' }))
      }),
    )
    render(
      <MemoryRouter initialEntries={['/login']}>
        <App />
      </MemoryRouter>,
    )
    await userEvent.type(screen.getByLabelText('Email'), 'citizen@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'long test passphrase')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await screen.findByRole('heading', { name: 'Citizen dashboard' })
    resolveRestore(anonymous())
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Citizen dashboard' })).toBeInTheDocument(),
    )
  })
})
