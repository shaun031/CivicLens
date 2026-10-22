export type Stage = 'local' | 'demo' | 'production'
export type CloudStage = Exclude<Stage, 'local'>

export interface EnvironmentConfig {
  readonly stage: Stage
  readonly frontendOrigins: readonly string[]
  readonly account?: string
  readonly region?: string
  readonly callbackUrls: readonly string[]
  readonly logoutUrls: readonly string[]
}

export interface EnvironmentInput {
  readonly stage?: unknown
  readonly frontendOrigins?: unknown
  readonly account?: unknown
  readonly region?: unknown
  readonly callbackUrls?: unknown
  readonly logoutUrls?: unknown
}

export function loadEnvironment(input: EnvironmentInput = {}): EnvironmentConfig {
  const stage = input.stage ?? 'demo'
  if (stage !== 'local' && stage !== 'demo' && stage !== 'production') {
    throw new Error('stage must be local, demo, or production')
  }
  let origins: unknown = input.frontendOrigins
  if (typeof origins === 'string') {
    try { origins = JSON.parse(origins) } catch {
      throw new Error('frontendOrigins must be a JSON array of HTTP(S) origins')
    }
  }
  origins ??= stage === 'production' ? [] : ['http://localhost:5173', 'http://127.0.0.1:5173']
  if (!Array.isArray(origins) || !origins.every((origin): origin is string => typeof origin === 'string')) {
    throw new Error('frontendOrigins must be an array of origin strings')
  }
  for (const origin of origins) {
    let url: URL
    try { url = new URL(origin) } catch { throw new Error(`Invalid frontend origin: ${origin}`) }
    if (!['http:', 'https:'].includes(url.protocol) || origin !== url.origin || origin.includes('*')) {
      throw new Error(`Use an exact HTTP(S) origin without a path or wildcard: ${origin}`)
    }
    if (stage === 'production' && (url.protocol !== 'https:' || ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname))) {
      throw new Error('Production frontend origins must use HTTPS and cannot use loopback hosts')
    }
  }
  const { account, region } = input
  if (account !== undefined && (typeof account !== 'string' || !/^\d{12}$/.test(account))) {
    throw new Error('account must be a 12-digit AWS account ID when supplied')
  }
  if (region !== undefined && (typeof region !== 'string' || !/^[a-z]{2}(?:-[a-z]+)+-\d+$/.test(region))) {
    throw new Error('region must be a valid AWS region identifier when supplied')
  }
  function authUrls(value: unknown, path: string): readonly string[] {
    if (typeof value === 'string') {
      try { value = JSON.parse(value) } catch { throw new Error('OAuth URLs must be JSON arrays') }
    }
    value ??= [stage === 'production' ? `https://frontend.example.invalid${path}` : `http://localhost:5173${path}`]
    if (!Array.isArray(value) || value.length === 0 || !value.every((url) => typeof url === 'string')) throw new Error('OAuth URLs must be nonempty arrays')
    for (const item of value) {
      let url: URL
      try { url = new URL(item) } catch { throw new Error('Invalid OAuth callback/logout URL') }
      const loopback = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)
      if (item.includes('*') || url.hash || url.username || url.password || (url.protocol !== 'https:' && !(stage !== 'production' && loopback && url.protocol === 'http:'))) {
        throw new Error('OAuth URLs require HTTPS, or demo localhost HTTP, without wildcards or fragments')
      }
    }
    return Object.freeze([...new Set(value as string[])])
  }
  return Object.freeze({ stage, frontendOrigins: Object.freeze([...new Set(origins)]), account, region,
    callbackUrls: authUrls(input.callbackUrls, '/auth/callback'), logoutUrls: authUrls(input.logoutUrls, '/'),
  })
}
