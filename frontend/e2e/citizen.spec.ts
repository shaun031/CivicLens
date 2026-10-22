import { expect, test } from './fixtures.js'
import type { Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { randomUUID } from 'node:crypto'

const identity = {
  id: 'browser-fixture-citizen',
  email: 'fixture@example.com',
  display_name: 'Browser Citizen',
  role: 'CITIZEN',
  provider: 'local',
  is_active: true,
  is_verified: true,
  is_authenticated: true,
}
async function mockIdentity(page: Page) {
  await page.route('**/api/**', (route) =>
    route.fulfill({
      json: route.request().url().endsWith('/auth/me')
        ? identity
        : route.request().url().includes('/complaints/summary')
          ? { total: 0, counts: {}, recent: [] }
          : route.request().url().includes('/complaints?')
            ? { items: [], nextCursor: null }
            : { message: 'Access granted.' },
    }),
  )
  // Browser tests never contact shared OSM infrastructure.
  await page.route('https://tile.openstreetmap.org/**', (route) => route.abort())
}
async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  )
}
async function accessibility(page: Page) {
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
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze()
  expect(
    result.violations.map((item) => ({
      id: item.id,
      nodes: item.nodes.map((node) => node.target),
    })),
  ).toEqual([])
}

for (const width of [375, 768, 1024, 1440]) {
  test(`public and citizen screens are accessible and fit ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    await mockIdentity(page)
    const pageErrors: string[] = []
    page.on('pageerror', (error) => pageErrors.push(error.message))
    await page.goto('/')
    await expect(page.getByRole('heading', { name: /Smarter reporting/i })).toBeVisible()
    await noOverflow(page)
    await accessibility(page)
    await page.screenshot({ path: `test-results/home-${width}.png`, fullPage: true })
    await page.goto('/citizen/dashboard')
    await expect(page.getByRole('heading', { name: 'No complaints yet' })).toBeVisible()
    await noOverflow(page)
    await accessibility(page)
    await page.screenshot({ path: `test-results/dashboard-${width}.png`, fullPage: true })
    await page.getByRole('checkbox', { name: 'Show sample data' }).check()
    if (width < 1024) {
      const menuButton = page.getByRole('button', { name: 'Open citizen menu' })
      await menuButton.click()
      await expect(page.getByRole('dialog', { name: 'Citizen menu' })).toBeVisible()
      await page.keyboard.press('Escape')
      await expect(menuButton).toBeFocused()
    }
    for (const path of ['report', 'complaints', 'nearby', 'notifications', 'profile']) {
      // Navigate with client links so preview state remains in-memory.
      if (width < 1024) await page.getByRole('button', { name: 'Open citizen menu' }).click()
      const labels: Record<string, string> = {
        report: 'Report an Issue',
        complaints: 'My Complaints',
        nearby: 'Nearby Issues',
        notifications: 'Notifications',
        profile: 'Profile',
      }
      const nav =
        width < 1024
          ? page.getByRole('dialog')
          : page.getByRole('navigation', { name: 'Citizen navigation' })
      await nav.getByRole('link', { name: labels[path], exact: true }).click()
      await expect(page.locator('h1')).toBeVisible()
      if (['report', 'nearby'].includes(path))
        await expect(page.getByRole('region', { name: 'Infrastructure issue map' })).toBeVisible()
      await noOverflow(page)
      await accessibility(page)
      await page.screenshot({ path: `test-results/${path}-${width}.png`, fullPage: true })
      if (path === 'complaints') {
        await page
          .getByRole('article')
          .filter({
            has: page.getByRole('heading', { name: 'Pothole beside the community library' }),
          })
          .getByRole('link', { name: /View details/ })
          .click()
        await expect(
          page.getByRole('heading', { name: 'Pothole beside the community library' }),
        ).toBeVisible()
        await noOverflow(page)
        await accessibility(page)
        await page.screenshot({ path: `test-results/details-${width}.png`, fullPage: true })
      }
    }
    expect(pageErrors).toEqual([])
  })
}

test('map markers, popups, filters, blocked tiles, and geolocation denial work in a real browser', async ({
  page,
  context,
}) => {
  await mockIdentity(page)
  await context.clearPermissions()
  await page.goto('/citizen/nearby')
  await page.getByRole('checkbox', { name: 'Show sample data' }).check()
  await expect(page.locator('.civic-map-marker')).toHaveCount(6)
  await page.getByLabel('Map category').selectOption('POTHOLE')
  await expect(page.locator('.civic-map-marker')).toHaveCount(1)
  await page.locator('.civic-map-marker').first().click()
  await expect(page.getByRole('link', { name: 'View simulated complaint' })).toBeVisible()
  await expect(page.getByText("Map tiles couldn't load.", { exact: false })).toBeVisible()
  await page.getByRole('button', { name: 'Use My Location' }).click()
  await expect(page.getByText('Location permission denied.', { exact: false })).toBeVisible()
  await page.getByRole('button', { name: 'List view' }).click()
  await expect(
    page.getByRole('heading', { name: 'Pothole beside the community library' }),
  ).toBeVisible()
  await expect(page.getByRole('region', { name: 'Infrastructure issue map' })).toHaveCount(0)
})

test('report preview validates, contains focus, restores focus, and never submits', async ({
  page,
}) => {
  await mockIdentity(page)
  const complaintCalls: string[] = []
  page.on('request', (request) => {
    if (/\/api\/(complaints|incidents|uploads)/.test(request.url()))
      complaintCalls.push(request.url())
  })
  await page.goto('/citizen/report')
  const preview = page.getByRole('button', { name: /Preview locally/ })
  await preview.click()
  await expect(page.getByLabel('Complaint category')).toBeFocused()
  await page.getByLabel('Complaint category').selectOption('POTHOLE')
  await page.getByLabel('Complaint title').fill('Uneven road near library')
  await page
    .getByLabel('Description', { exact: true })
    .fill('A large uneven patch is difficult to navigate for cyclists.')
  await page.getByLabel('Location / landmark').fill('Community Library Road')
  await page.getByLabel('Latitude', { exact: true }).fill('12.9716')
  await page.getByLabel('Longitude', { exact: true }).fill('77.5946')
  await page.getByLabel('Photograph evidence (optional)').setInputFiles({
    name: 'road.png',
    mimeType: 'image/png',
    buffer: Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=',
      'base64',
    ),
  })
  await expect(page.getByAltText('Selected evidence: road.png')).toBeVisible()
  await preview.click()
  const dialog = page.getByRole('dialog', { name: 'Local report preview — not submitted' })
  await expect(dialog).toBeVisible()
  await accessibility(page)
  await page.keyboard.press('Tab')
  expect(
    await page.evaluate(() =>
      Boolean(document.querySelector('dialog')?.contains(document.activeElement)),
    ),
  ).toBe(true)
  await page.keyboard.press('Escape')
  await expect(preview).toBeFocused()
  expect(complaintCalls).toEqual([])
})

test('real proxy-backed citizen registration, login, refresh, profile edit and logout remain operational', async ({
  page,
}) => {
  const email = `browser-${randomUUID()}@example.com`
  const password = `Test passphrase ${randomUUID()}`
  await page.goto('/citizen/report')
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
  // Register against the isolated real SQLite API, then follow the protected return route.
  const registered = await page.request.post('/api/auth/register', {
    headers: { Origin: 'http://localhost:5180' },
    data: { display_name: 'Live Browser Citizen', email, password, confirm_password: password },
  })
  expect(registered.status()).toBe(201)
  await page.getByLabel('Email', { exact: true }).fill(email)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page).toHaveURL(/\/citizen\/report$/)
  await expect(page.getByLabel('Complaint title')).toBeVisible()
  await page.reload()
  await expect(page.getByLabel('Complaint title')).toBeVisible()
  await page.goto('/citizen/profile')
  await expect(page.getByText(email, { exact: true })).toBeVisible()
  await page.getByLabel('Display name').fill('Updated Real Citizen')
  await page.getByRole('button', { name: 'Save profile' }).click()
  await expect(page.getByText('Profile updated.')).toBeVisible()
  await page.reload()
  await expect(page.getByLabel('Display name')).toHaveValue('Updated Real Citizen')
  const denied = await page.request.get('/api/portal/admin')
  expect(denied.status()).toBe(403)
  await page.getByRole('button', { name: 'Sign out', exact: true }).last().click()
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
  expect((await page.request.get('/api/auth/me')).status()).toBe(401)
})

test('real complaint submission, private photo, dashboard, refresh and ownership isolation work end to end', async ({
  page,
}) => {
  await page.route('https://tile.openstreetmap.org/**', (route) => route.abort())
  const email = `complaint-${randomUUID()}@example.com`
  const password = `Private test passphrase ${randomUUID()}`
  const origin = { Origin: 'http://localhost:5180' }
  await page.goto('/citizen/report')
  const registered = await page.request.post('/api/auth/register', {
    headers: origin,
    data: {
      display_name: 'Complaint Browser Citizen',
      email,
      password,
      confirm_password: password,
    },
  })
  expect(registered.status()).toBe(201)
  await page.getByLabel('Email', { exact: true }).fill(email)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Submit Complaint' })).toBeVisible()
  const description = 'A pothole near the library creates a hazard for cyclists and pedestrians.'
  await page.getByLabel('Complaint category').selectOption('POTHOLE')
  await page.getByLabel('Complaint title').fill('Pothole beside the local library')
  await page.getByLabel('Description', { exact: true }).fill(description)
  await page.getByLabel('Location / landmark').fill('Library Road')
  await page.getByLabel('Landmark (optional)').fill('Library gate')
  await page.getByLabel('Latitude', { exact: true }).fill('12.9716')
  await page.getByLabel('Longitude', { exact: true }).fill('77.5946')
  await page.getByLabel('User-reported severity').selectOption('HIGH')
  const photo = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAABQAAAAKCAIAAAA7N+mxAAAAGklEQVR4nGNkYPjPQC5gIlsnw6hmksEQDW0AdvUBE1VypFEAAAAASUVORK5CYII=',
    'base64',
  )
  await page
    .getByLabel('Photograph evidence (optional)')
    .setInputFiles({ name: 'road.png', mimeType: 'image/png', buffer: photo })
  const pending = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/complaints') && response.request().method() === 'POST',
  )
  await page.getByRole('button', { name: 'Submit Complaint' }).click()
  const response = await pending
  expect(response.status()).toBe(201)
  const created = await response.json()
  expect(created.status).toBe('SUBMITTED')
  expect(created.incidentId).toBeNull()
  expect(created.images).toHaveLength(1)
  expect(created.images[0]).not.toHaveProperty('storageKey')
  await expect(page.getByText(created.complaintId, { exact: true })).toBeVisible()
  await page.screenshot({ path: 'test-results/phase4-submitted.png', fullPage: true })
  await page.getByRole('link', { name: 'View complaint details' }).click()
  await expect(
    page.getByRole('heading', { name: 'Pothole beside the local library' }),
  ).toBeVisible()
  await expect(page.getByText(description, { exact: true })).toBeVisible()
  const image = page.getByAltText('Submitted photo evidence')
  await expect(image).toBeVisible()
  await expect
    .poll(() => image.evaluate((element) => (element as HTMLImageElement).naturalWidth))
    .toBe(20)
  await accessibility(page)
  await page.screenshot({ path: 'test-results/phase4-private-details.png', fullPage: true })
  await page.reload()
  await expect(page.getByAltText('Submitted photo evidence')).toBeVisible()
  const photoUrl = '/api' + created.images[0].url
  const retrieved = await page.request.get(photoUrl)
  expect(retrieved.status()).toBe(200)
  expect(retrieved.headers()['content-type']).toBe('image/jpeg')
  expect(retrieved.headers()['cache-control']).toContain('no-store')
  await page.goto('/citizen/complaints')
  await expect(page.getByRole('heading', { name: created.title })).toBeVisible()
  await page.goto('/citizen/dashboard')
  await expect(page.getByRole('heading', { name: created.title })).toBeVisible()
  expect((await page.request.get('/api/complaints/summary')).status()).toBe(200)
  await page.request.post('/api/auth/logout', { headers: origin })
  expect((await page.request.get(photoUrl)).status()).toBe(401)
  await page.goto(`/citizen/complaints/${created.complaintId}`)
  await page.getByLabel('Email', { exact: true }).fill(email)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('heading', { name: created.title })).toBeVisible()
  const otherEmail = `other-${randomUUID()}@example.com`
  await page.request.post('/api/auth/logout', { headers: origin })
  expect(
    (
      await page.request.post('/api/auth/register', {
        headers: origin,
        data: {
          display_name: 'Other Citizen',
          email: otherEmail,
          password,
          confirm_password: password,
        },
      })
    ).status(),
  ).toBe(201)
  expect(
    (
      await page.request.post('/api/auth/login', {
        headers: origin,
        data: { email: otherEmail, password },
      })
    ).status(),
  ).toBe(200)
  await page.goto(`/citizen/complaints/${created.complaintId}`)
  await expect(page.getByRole('heading', { name: 'Complaint not found' })).toBeVisible()
  expect((await page.request.get(photoUrl)).status()).toBe(404)
  await page.goto('/citizen/complaints')
  await expect(page.getByRole('heading', { name: 'No complaints yet' })).toBeVisible()
})
