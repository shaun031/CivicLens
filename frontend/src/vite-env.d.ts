/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_APP_NAME?: string
  readonly VITE_LOCATION_SEARCH_URL?: string
  readonly VITE_API_BASE_URL?: string
  readonly VITE_AUTH_MODE?: 'local' | 'aws'
  readonly VITE_COGNITO_ISSUER?: string
  readonly VITE_COGNITO_CLIENT_ID?: string
  readonly VITE_COGNITO_DOMAIN?: string
  readonly VITE_COGNITO_REDIRECT_URI?: string
  readonly VITE_COGNITO_LOGOUT_URI?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
