import { defineConfig } from '@playwright/test'
import { randomUUID } from 'node:crypto'
import { basename, dirname, resolve } from 'node:path'
import { existsSync } from 'node:fs'
const installedChrome =
  process.platform === 'win32' &&
  [
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  ].some((path) => existsSync(path))
const browserRunId = process.env.CIVICLENS_BROWSER_RUN_ID ?? randomUUID()
const fixtureId = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const fixtureRoot = resolve('../backend/data')
if (!fixtureId.test(browserRunId))
  throw new Error('Browser run ID must be a UUID; unsafe fixture paths are forbidden.')
function requireNewFixtureDatabase(path: string) {
  // Playwright reloads config inside workers after its owned servers create the DB.
  const workerReload = /^\d+$/.test(process.env.TEST_WORKER_INDEX ?? '')
  const absolute = resolve(path)
  const id = basename(absolute)
    .replace(/^phase5-browser-/, '')
    .replace(/\.db$/, '')
  if (
    dirname(absolute).toLowerCase() !== fixtureRoot.toLowerCase() ||
    basename(absolute) !== `phase5-browser-${id}.db` ||
    !fixtureId.test(id) ||
    (!workerReload && (existsSync(absolute) || existsSync(absolute.replace(/\.db$/, '-evidence'))))
  )
    throw new Error(
      'Browser fixtures require new isolated UUID databases; existing/developer data is forbidden.',
    )
  return absolute
}
process.env.CIVICLENS_BROWSER_RUN_ID = browserRunId
process.env.CIVICLENS_BROWSER_DB_PATH = requireNewFixtureDatabase(
  resolve('../backend/data', `phase5-browser-${browserRunId}.db`),
)
process.env.CIVICLENS_ALLOCATION_BROWSER_DB_PATH = requireNewFixtureDatabase(
  process.env.CIVICLENS_ALLOCATION_BROWSER_DB_PATH ??
    resolve('../backend/data', `phase5-browser-${randomUUID()}.db`),
)
// Dedicated servers/database: never reuse the developer's account store or ports.
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  projects: [
    { name: 'regression', testIgnore: '**/assignment.spec.ts' },
    {
      name: 'allocation',
      testMatch: '**/assignment.spec.ts',
      use: { baseURL: 'http://localhost:5181' },
    },
  ],
  timeout: 90000,
  use: {
    baseURL: 'http://localhost:5180',
    browserName: 'chromium',
    channel: process.env.CIVICLENS_BROWSER_CHANNEL ?? (installedChrome ? 'chrome' : 'chromium'),
    headless: true,
    trace: 'retain-on-failure',
  },
  reporter: [['list']],
  webServer: [
    {
      command: '".venv/Scripts/python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8002',
      cwd: '../backend',
      url: 'http://127.0.0.1:8002/api/health',
      reuseExistingServer: false,
      env: {
        APP_ENV: 'test',
        AUTH_PROVIDER: 'local',
        DEBUG: 'false',
        COOKIE_SECURE: 'false',
        CORS_ORIGINS: 'http://localhost:5180',
        LOCAL_DB_PATH: process.env.CIVICLENS_BROWSER_DB_PATH,
        LOCAL_EVIDENCE_ROOT: resolve('../backend/data', `phase5-browser-${browserRunId}-evidence`),
        COMPLAINT_PROVIDER: 'sqlite',
        EVIDENCE_PROVIDER: 'local',
      },
    },
    {
      command: 'npm run dev -- --port 5180',
      url: 'http://localhost:5180',
      reuseExistingServer: false,
      env: {
        CIVICLENS_API_PROXY_TARGET: 'http://127.0.0.1:8002',
        VITE_AUTH_MODE: 'local',
        VITE_API_BASE_URL: '/api',
      },
    },
    {
      command: '".venv/Scripts/python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8003',
      cwd: '../backend',
      url: 'http://127.0.0.1:8003/api/health',
      reuseExistingServer: false,
      env: {
        APP_ENV: 'test',
        AUTH_PROVIDER: 'local',
        DEBUG: 'false',
        COOKIE_SECURE: 'false',
        CORS_ORIGINS: 'http://localhost:5181',
        LOCAL_DB_PATH: process.env.CIVICLENS_ALLOCATION_BROWSER_DB_PATH,
        LOCAL_EVIDENCE_ROOT: process.env.CIVICLENS_ALLOCATION_BROWSER_DB_PATH + '-evidence',
        COMPLAINT_PROVIDER: 'sqlite',
        EVIDENCE_PROVIDER: 'local',
      },
    },
    {
      command: 'npm run dev -- --port 5181',
      url: 'http://localhost:5181',
      reuseExistingServer: false,
      env: {
        CIVICLENS_API_PROXY_TARGET: 'http://127.0.0.1:8003',
        VITE_AUTH_MODE: 'local',
        VITE_API_BASE_URL: '/api',
      },
    },
  ],
})
