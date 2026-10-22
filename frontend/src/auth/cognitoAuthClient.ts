import { InMemoryWebStorage, UserManager, WebStorageStateStore } from 'oidc-client-ts'
import { safeDestination } from './types'

let manager: UserManager | undefined

export function getCognitoManager(): UserManager {
  if (manager) return manager
  const authority = import.meta.env.VITE_COGNITO_ISSUER
  const clientId = import.meta.env.VITE_COGNITO_CLIENT_ID
  const domain = import.meta.env.VITE_COGNITO_DOMAIN
  const redirectUri = import.meta.env.VITE_COGNITO_REDIRECT_URI
  const logoutUri = import.meta.env.VITE_COGNITO_LOGOUT_URI
  if (!authority || !clientId || !domain || !redirectUri || !logoutUri)
    throw new Error(
      'Cognito public configuration is incomplete. Local authentication is not used as a fallback.',
    )
  if (![authority, domain, redirectUri, logoutUri].every((url) => url.startsWith('https://')))
    throw new Error('AWS authentication requires HTTPS URLs.')
  manager = new UserManager({
    authority,
    client_id: clientId,
    redirect_uri: redirectUri,
    post_logout_redirect_uri: logoutUri,
    response_type: 'code',
    scope: 'openid email profile aws.cognito.signin.user.admin civiclens/access',
    disablePKCE: false,
    automaticSilentRenew: true,
    // Tokens stay in memory; sessionStorage holds only transient OAuth state/PKCE data.
    userStore: new WebStorageStateStore({ store: new InMemoryWebStorage() }),
    stateStore: new WebStorageStateStore({ store: window.sessionStorage }),
    metadata: {
      issuer: authority,
      authorization_endpoint: `${domain}/oauth2/authorize`,
      token_endpoint: `${domain}/oauth2/token`,
      userinfo_endpoint: `${domain}/oauth2/userInfo`,
      jwks_uri: `${authority}/.well-known/jwks.json`,
      revocation_endpoint: `${domain}/oauth2/revoke`,
      end_session_endpoint: `${domain}/logout`,
    },
  })
  manager.events.addAccessTokenExpired(() => {
    window.dispatchEvent(new Event('civiclens:session-expired'))
  })
  return manager
}

export async function beginCognitoLogin(returnTo: string) {
  await getCognitoManager().signinRedirect({
    state: { returnTo: safeDestination(returnTo) },
  })
}

export async function finishCognitoLogin(): Promise<string> {
  const user = await getCognitoManager().signinRedirectCallback()
  window.history.replaceState({}, '', '/auth/callback')
  const state = user.state as { returnTo?: unknown } | undefined
  return safeDestination(state?.returnTo)
}

export async function logoutCognito() {
  const client = getCognitoManager()
  // Revoke refresh/access tokens before leaving; remove in-memory state even on failure.
  try {
    await client.revokeTokens(['refresh_token', 'access_token'])
  } catch {
    // Cognito logout must still clear the browser SSO cookie if revocation is unavailable.
  } finally {
    await client.removeUser()
  }
  const url = new URL(`${import.meta.env.VITE_COGNITO_DOMAIN}/logout`)
  url.searchParams.set('client_id', import.meta.env.VITE_COGNITO_CLIENT_ID ?? '')
  url.searchParams.set('logout_uri', import.meta.env.VITE_COGNITO_LOGOUT_URI ?? '')
  window.location.assign(url.toString())
}
