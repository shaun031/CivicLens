import { expect, test, type Page } from './fixtures.js'
import AxeBuilder from '@axe-core/playwright'
import { randomUUID } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'

const screenshots = resolve('../build/phase14/screenshots')
const widths = [375, 768, 1024, 1440]
async function layout(page: Page) {
  expect(
    await page.evaluate(() => ({
      scroll: document.documentElement.scrollWidth,
      viewport: innerWidth,
    })),
  ).toEqual(expect.objectContaining({ scroll: await page.evaluate(() => innerWidth) }))
  await expect(page.locator('h1')).toHaveCount(1)
}
async function accessible(page: Page) {
  await page.evaluate(async () => {
    await Promise.all(
      document
        .getAnimations()
        .filter((animation) =>
          Number.isFinite(Number(animation.effect?.getComputedTiming().endTime)),
        )
        .map((animation) => animation.finished.catch(() => undefined)),
    )
  })
  const result = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
    .analyze()
  expect(
    result.violations.map((v) => ({ id: v.id, targets: v.nodes.map((n) => n.target) })),
  ).toEqual([])
}
function staff(email: string, password: string, role: string) {
  const provision = spawnSync(
    resolve('../backend/.venv/Scripts/python.exe'),
    [resolve('../tests/integration/provision_browser_admin.py')],
    {
      cwd: resolve('../backend'),
      windowsHide: true,
      encoding: 'utf8',
      env: {
        ...process.env,
        BROWSER_ADMIN_EMAIL: email,
        BROWSER_ADMIN_PASSWORD: password,
        BROWSER_STAFF_ROLE: role,
      },
    },
  )
  expect(provision.status, provision.stderr).toBe(0)
}
async function screenshot(page: Page, name: string) {
  mkdirSync(screenshots, { recursive: true })
  await page.screenshot({
    path: resolve(screenshots, `${name}.png`),
    fullPage: true,
    animations: 'disabled',
  })
}

test('redesign: public/auth and real citizen pages fit all target widths, navigation and reduced motion', async ({
  page,
}) => {
  test.setTimeout(240000)
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.route('https://tile.openstreetmap.org/**', (r) => r.abort())
  for (const width of widths) {
    await page.setViewportSize({ width, height: 900 })
    for (const route of ['/', '/login', '/register']) {
      await page.goto(route)
      await expect(page.locator('h1')).toBeVisible()
      await layout(page)
      await accessible(page)
      if (width === 375 || width === 1440)
        await screenshot(page, `${route === '/' ? 'landing' : route.slice(1)}-${width}`)
    }
  }
  const origin = { Origin: 'http://localhost:5180' }
  const email = `redesign-citizen-${randomUUID()}@example.com`
  const password = `Private redesign passphrase ${randomUUID()}`
  // Registration is covered by existing real HTTP journeys. Provision this extra fixture
  // through the guarded test helper so all-suite runs preserve the production IP rate limit.
  staff(email, password, 'CITIZEN')
  expect(
    (
      await page.request.post('/api/auth/login', { headers: origin, data: { email, password } })
    ).status(),
  ).toBe(200)
  for (const width of widths) {
    await page.setViewportSize({ width, height: 900 })
    for (const route of [
      'dashboard',
      'report',
      'complaints',
      'nearby',
      'verification',
      'notifications',
      'profile',
    ]) {
      await page.goto(`/citizen/${route}`)
      await expect(page.locator('h1')).toBeVisible()
      await expect(page.getByText('Loading content…', { exact: true })).toHaveCount(0)
      await layout(page)
      await accessible(page)
      if ((width === 375 || width === 1440) && ['dashboard', 'report', 'nearby'].includes(route))
        await screenshot(page, `citizen-${route}-${width}`)
    }
    await page.goto('/citizen/dashboard')
    if (width < 1024) {
      const button = page.getByRole('button', { name: 'Open citizen menu' })
      await button.click()
      await expect(page.getByRole('dialog', { name: 'Citizen menu' })).toBeVisible()
      await accessible(page)
      await page.keyboard.press('Escape')
      await expect(button).toBeFocused()
    } else {
      await page.getByRole('button', { name: 'Collapse sidebar' }).click()
      await expect(page.getByRole('button', { name: 'Expand sidebar' })).toBeVisible()
      await layout(page)
      await page.getByRole('button', { name: 'Expand sidebar' }).click()
    }
    await page.getByText('Your reporting insights', { exact: true }).click()
    await expect(page.getByLabel('Submission trend period')).toBeVisible()
    await page.getByLabel('Submission trend period').selectOption('7')
    await expect(page.getByLabel('Submission trend period')).toBeVisible()
    await expect(page.getByLabel('Submission trend period')).toHaveValue('7')
    await page.locator('.account-menu > summary').click()
    await expect(page.locator('.account-dropdown')).toBeVisible()
    await page.keyboard.press('Tab')
    await page.keyboard.press('Escape')
    await expect(page.locator('.account-dropdown')).toHaveCount(0)
    await expect(page.locator('.account-menu > summary')).toBeFocused()
  }
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.setViewportSize({ width: 375, height: 900 })
  await page.goto('/citizen/report')
  await expect(page.getByLabel('Complaint title')).toBeVisible()
  expect(
    await page.locator('.page-transition').evaluate((e) => getComputedStyle(e).animationName),
  ).toBe('none')
  expect(
    await page
      .locator('.ui-card')
      .first()
      .evaluate((e) => getComputedStyle(e).animationName),
  ).toBe('none')
  const before = await page.request.get('/api/complaints?')
  const countBefore = (await before.json()).items.length
  const drop = page.locator('.upload-dropzone')
  const invalidFiles = await page.evaluateHandle(() => {
    const dt = new DataTransfer()
    dt.items.add(new File(['unsafe'], 'unsafe.svg', { type: 'image/svg+xml' }))
    return dt
  })
  await drop.dispatchEvent('drop', { dataTransfer: invalidFiles })
  await expect(page.getByRole('alert')).toContainText('Only JPEG, PNG, and WebP')
  const after = await page.request.get('/api/complaints?')
  expect((await after.json()).items.length).toBe(countBefore)
  expect(errors).toEqual([])
})

test('redesign: real administrator/officer APIs, all operational routes, responsive tables and grouped navigation', async ({
  page,
}) => {
  test.setTimeout(360000)
  const errors: string[] = [],
    failures: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('response', (r) => {
    if (r.url().includes('/api/') && r.status() >= 500) failures.push(`${r.status()} ${r.url()}`)
  })
  await page.route('https://tile.openstreetmap.org/**', (r) => r.abort())
  const origin = { Origin: 'http://localhost:5180' }
  const password = `Municipal redesign passphrase ${randomUUID()}`
  const administrator = `redesign-admin-${randomUUID()}@example.com`
  const officer = `redesign-officer-${randomUUID()}@example.com`
  staff(administrator, password, 'ADMIN')
  staff(officer, password, 'OFFICER')
  await page.goto('/')
  expect(
    (
      await page.request.post('/api/auth/login', {
        headers: origin,
        data: { email: administrator, password },
      })
    ).status(),
  ).toBe(200)
  const adminRoutes = [
    'command-center',
    'dashboard',
    'incidents',
    'priorities',
    'departments',
    'assignments',
    'duplicate-candidates',
    'publication-review',
    'repair-verification',
    'recurrences',
    'fairness',
    'hotspots',
    'reports',
    'workflows',
    ...[
      'complaint-trends',
      'incidents',
      'priorities',
      'departments',
      'officers',
      'sla',
      'backlog',
      'response-times',
    ].map((v) => `analytics/${v}`),
  ]
  for (const width of widths) {
    await page.setViewportSize({ width, height: 900 })
    for (const route of adminRoutes) {
      await page.goto(`/admin/${route}`)
      await expect(page.locator('h1')).toBeVisible()
      await expect(page.getByRole('status', { name: 'Loading content' })).toHaveCount(0)
      await layout(page)
      if (
        [
          'command-center',
          'priorities',
          'departments',
          'repair-verification',
          'recurrences',
          'fairness',
          'reports',
          'workflows',
        ].includes(route)
      )
        await accessible(page)
      if (
        (width === 375 || width === 1440) &&
        ['command-center', 'priorities', 'fairness', 'repair-verification'].includes(route)
      )
        await screenshot(page, `admin-${route}-${width}`)
    }
  }
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/admin/command-center')
  const nav = page.getByRole('navigation', { name: 'Administrator navigation' })
  await nav.getByText('Review & quality', { exact: true }).click()
  await expect(nav.getByRole('link', { name: 'Duplicate review' })).toBeVisible()
  await nav.getByRole('link', { name: 'Duplicate review' }).click()
  await expect(page).toHaveURL(/admin\/duplicate-candidates$/)
  await page.request.post('/api/auth/logout', { headers: origin })
  expect(
    (
      await page.request.post('/api/auth/login', {
        headers: origin,
        data: { email: officer, password },
      })
    ).status(),
  ).toBe(200)
  for (const width of widths) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/officer/dashboard')
    await expect(page.getByRole('heading', { name: 'Assigned incident queue' })).toBeVisible()
    await layout(page)
    await accessible(page)
    if (width === 375 || width === 1440) await screenshot(page, `officer-${width}`)
  }
  expect((await page.request.get('/api/admin/incidents')).status()).toBe(403)
  expect(failures).toEqual([])
  expect(errors).toEqual([])
})
