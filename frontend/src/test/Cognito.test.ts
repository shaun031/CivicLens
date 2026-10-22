import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  constructor: vi.fn(),
  redirect: vi.fn(),
  callback: vi.fn(),
  getUser: vi.fn(),
  revoke: vi.fn(),
  remove: vi.fn(),
}))
vi.mock('oidc-client-ts', () => ({
  InMemoryWebStorage: class {},
  WebStorageStateStore: class {},
  UserManager: class {
    constructor(options: unknown) {
      mocks.constructor(options)
    }
    events = { addAccessTokenExpired: vi.fn() }
    signinRedirect = mocks.redirect
    signinRedirectCallback = mocks.callback
    getUser = mocks.getUser
    revokeTokens = mocks.revoke
    removeUser = mocks.remove
  },
}))

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
  vi.clearAllMocks()
  vi.resetModules()
})
function configure() {
  vi.stubEnv('VITE_AUTH_MODE', 'aws')
  vi.stubEnv('VITE_COGNITO_ISSUER', 'https://cognito-idp.ap-south-1.amazonaws.com/ap-south-1_Test')
  vi.stubEnv('VITE_COGNITO_CLIENT_ID', 'testclient')
  vi.stubEnv('VITE_COGNITO_DOMAIN', 'https://civic-test.auth.ap-south-1.amazoncognito.com')
  vi.stubEnv('VITE_COGNITO_REDIRECT_URI', 'https://civic.example.org/auth/callback')
  vi.stubEnv('VITE_COGNITO_LOGOUT_URI', 'https://civic.example.org/')
}
describe('Cognito browser preparation', () => {
  it('uses the maintained OIDC client with code flow, PKCE, and no client secret', async () => {
    configure()
    const { beginCognitoLogin } = await import('../auth/cognitoAuthClient')
    await beginCognitoLogin('/profile')
    expect(mocks.constructor).toHaveBeenCalledWith(
      expect.objectContaining({
        response_type: 'code',
        disablePKCE: false,
        client_id: 'testclient',
      }),
    )
    expect(mocks.constructor.mock.calls[0][0]).not.toHaveProperty('client_secret')
    expect(mocks.redirect).toHaveBeenCalledWith({
      state: { returnTo: '/profile' },
    })
  })
  it('passes only an access token to the protected API', async () => {
    configure()
    mocks.getUser.mockResolvedValue({
      access_token: 'test-access-token',
      id_token: 'never-send-this-id-token',
      expired: false,
    })
    const fetch = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetch)
    const { authRequest } = await import('../auth/authClient')
    await authRequest('/auth/me')
    expect(fetch).toHaveBeenCalledWith(
      '/api/auth/me',
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer test-access-token',
        }),
        credentials: 'omit',
      }),
    )
  })
  it('rejects missing cloud configuration without a local fallback', async () => {
    vi.stubEnv('VITE_AUTH_MODE', 'aws')
    const { getCognitoManager } = await import('../auth/cognitoAuthClient')
    expect(getCognitoManager).toThrow('configuration is incomplete')
    expect(mocks.constructor).not.toHaveBeenCalled()
  })
  it('completes the library callback and rejects an external return target', async () => {
    configure()
    mocks.callback.mockResolvedValue({ state: { returnTo: '//evil.example' } })
    const { finishCognitoLogin } = await import('../auth/cognitoAuthClient')
    expect(await finishCognitoLogin()).toBe('/')
  })
})
