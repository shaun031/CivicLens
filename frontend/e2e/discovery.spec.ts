import { expect, test } from './fixtures.js'
import AxeBuilder from '@axe-core/playwright'
import { randomUUID } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { resolve } from 'node:path'

test('real search, charts, administrator-reviewed public map, radius and withdrawal', async ({
  page,
  browser,
}) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.route('https://tile.openstreetmap.org/**', (route) => route.abort())
  const password = `Browser verification passphrase ${randomUUID()}`
  const email = `phase5-citizen-${randomUUID()}@example.com`
  const origin = { Origin: 'http://localhost:5180' }
  await page.goto('/')
  expect(
    (
      await page.request.post('/api/auth/register', {
        headers: origin,
        data: { display_name: 'Phase Five Citizen', email, password, confirm_password: password },
      })
    ).status(),
  ).toBe(201)
  expect(
    (
      await page.request.post('/api/auth/login', { headers: origin, data: { email, password } })
    ).status(),
  ).toBe(200)
  const ids: string[] = []
  for (let index = 0; index < 3; index++) {
    const result = await page.request.post('/api/complaints', {
      headers: { ...origin, 'Idempotency-Key': randomUUID() },
      multipart: {
        title: `Phase five library surface defect ${index}`,
        description: 'Private complaint notes must not appear in the approved public map.',
        category: index === 2 ? 'DRAINAGE' : 'POTHOLE',
        reportedSeverity: 'HIGH',
        latitude: '12.982',
        longitude: '77.605',
        addressLabel: 'Library Road',
      },
    })
    expect(result.status()).toBe(201)
    ids.push((await result.json()).complaintId)
  }
  await page.goto('/citizen/complaints')
  await expect(
    page.getByRole('heading', { name: 'Phase five library surface defect 2' }),
  ).toBeVisible()
  await page.getByRole('searchbox').fill('library')
  await page.getByRole('combobox', { name: 'Category', exact: true }).selectOption('POTHOLE')
  await page.getByText('More filters', { exact: true }).click()
  await page.getByRole('combobox', { name: 'Reported severity', exact: true }).selectOption('HIGH')
  await expect(page.getByText(/2 account complaints matching/)).toBeVisible()
  expect(page.url()).toContain('category=POTHOLE')
  await page.reload()
  await expect(page.getByRole('combobox', { name: 'Reported severity', exact: true })).toHaveValue(
    'HIGH',
  )
  await expect(page.getByText(/2 account complaints matching/)).toBeVisible()
  await page.goto('/citizen/dashboard')
  await page.getByText('Your reporting insights', { exact: true }).click()
  await expect(page.getByRole('img', { name: /Complaints by category:.*Pothole 2/ })).toBeVisible()
  await expect(page.getByRole('img', { name: /Complaints by status: Submitted 3/ })).toBeVisible()
  await expect(page.getByRole('img', { name: /Submission trend.*3/ })).toBeVisible()
  const chart = page.locator('canvas').first()
  await expect
    .poll(() =>
      chart.evaluate((canvas) =>
        (canvas as HTMLCanvasElement)
          .getContext('2d')
          ?.getImageData(
            0,
            0,
            (canvas as HTMLCanvasElement).width,
            (canvas as HTMLCanvasElement).height,
          )
          .data.some((byte) => byte !== 0),
      ),
    )
    .toBe(true)
  await page.screenshot({ path: 'test-results/phase5-analytics.png', fullPage: true })
  for (const width of [375, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
      .toBe(true)
    if (width === 375 || width === 1440) {
      expect(
        (await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze())
          .violations,
      ).toEqual([])
      await page.screenshot({ path: `test-results/phase5-analytics-${width}.png`, fullPage: true })
    }
  }
  await page.goto(`/citizen/complaints/${ids[0]}`)
  await page.getByRole('button', { name: 'Request public map publication' }).click()
  await expect(page.getByText('Publication status: PENDING REVIEW')).toBeVisible()
  const region = {
    minLatitude: '12.96',
    maxLatitude: '13.0',
    minLongitude: '77.58',
    maxLongitude: '77.63',
  }
  const before = await page.request.get('/api/public/issues', { params: region })
  expect((await before.json()).items).toHaveLength(0)
  expect(
    (
      await page.request.patch(`/api/admin/complaints/${ids[0]}/publication`, {
        headers: origin,
        data: { decision: 'UNPUBLISH' },
      })
    ).status(),
  ).toBe(403)
  const administrator = `phase5-admin-${randomUUID()}@example.com`
  const provision = spawnSync(
    resolve('../backend/.venv/Scripts/python.exe'),
    [resolve('../tests/integration/provision_browser_admin.py')],
    {
      cwd: resolve('../backend'),
      encoding: 'utf8',
      env: { ...process.env, BROWSER_ADMIN_EMAIL: administrator, BROWSER_ADMIN_PASSWORD: password },
    },
  )
  expect(provision.status, 'Isolated trusted administrator provisioning succeeded').toBe(0)
  await page.request.post('/api/auth/logout', { headers: origin })
  await page.goto('/admin/publication-review')
  await page.getByLabel('Email', { exact: true }).fill(administrator)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.getByLabel('Complaint ID', { exact: true }).fill(ids[0])
  await page
    .getByLabel('Reviewed public summary')
    .fill('Reviewed road surface damage near the library junction')
  await page.getByLabel('Public latitude', { exact: true }).fill('12.982')
  await page.getByLabel('Public longitude', { exact: true }).fill('77.605')
  await page.getByRole('checkbox', { name: /I reviewed/ }).check()
  await page.getByRole('button', { name: 'Save audited decision' }).click()
  await expect(page.getByText('Audited publication decision saved: PUBLISHED')).toBeVisible()
  const published = (
    await (await page.request.get('/api/public/issues', { params: region })).json()
  ).items
  expect(published).toHaveLength(1)
  expect(published[0]).not.toHaveProperty('citizenId')
  expect(published[0]).not.toHaveProperty('images')
  expect(JSON.stringify(published)).not.toContain('Private complaint notes')
  await page.request.post('/api/auth/logout', { headers: origin })
  await page.request.post('/api/auth/login', { headers: origin, data: { email, password } })
  await page.goto('/citizen/nearby')
  await page.getByRole('button', { name: 'Search near my latest complaint' }).click()
  await expect(page.getByText(/3 visible reports loaded within 10 km/)).toBeVisible()
  await expect(page.locator('.nearby-result')).toHaveCount(3)
  await expect(page.locator('.nearby-cluster-marker')).toHaveText('3')
  const radiusBeforeZoom = await page.locator('.leaflet-overlay-pane path').getAttribute('d')
  await page.locator('.nearby-cluster-marker').click()
  await expect(page.locator('.leaflet-popup')).toContainText(
    '3 individual reports, not unique incidents',
  )
  await expect(page.locator('.leaflet-overlay-pane path')).not.toHaveAttribute(
    'd',
    radiusBeforeZoom!,
  )
  await page
    .locator('.leaflet-popup')
    .getByRole('button', { name: 'Phase five library surface defect 0' })
    .click()
  await expect(
    page.locator('.category-map-marker[title="Phase five library surface defect 0"]'),
  ).toBeVisible()
  await expect(page.locator('.leaflet-popup')).toHaveCount(1)
  await expect(page.getByLabel('Map latitude')).toHaveValue('12.982000')
  await expect(page.getByLabel('Map longitude')).toHaveValue('77.605000')
  await expect(page.getByRole('list', { name: 'Issue category legend' })).toBeVisible()
  await expect(
    page.locator('.nearby-result').getByText('My Report · Publicly Visible', { exact: true }),
  ).toHaveCount(1)
  await expect(
    page.locator('.nearby-result').getByText('My Report · Not Publicly Visible', { exact: true }),
  ).toHaveCount(2)
  await page.screenshot({ path: 'test-results/phase5-public-map.png', fullPage: true })
  await page
    .locator('.nearby-result')
    .filter({ hasText: 'Phase five library surface defect 0' })
    .getByRole('button', { name: 'Show on map' })
    .click()
  await expect(
    page.locator('.category-map-marker[title="Phase five library surface defect 0"]'),
  ).toBeVisible()
  await expect(page.locator('.leaflet-popup')).toContainText('My Report')
  // Switch to an independent citizen to verify public-only discovery and no owner-private IDs.
  const otherEmail = `nearby-viewer-${randomUUID()}@example.com`
  // Provision only this extra fixture through the existing guarded test CLI.
  // Do not consume another test's real public registration/login IP quota.
  const viewerFixture = spawnSync(
    resolve('../backend/.venv/Scripts/python.exe'),
    [resolve('../tests/integration/provision_browser_admin.py')],
    {
      cwd: resolve('../backend'),
      windowsHide: true,
      encoding: 'utf8',
      env: {
        ...process.env,
        BROWSER_ADMIN_EMAIL: otherEmail,
        BROWSER_ADMIN_PASSWORD: password,
        BROWSER_STAFF_ROLE: 'CITIZEN',
        BROWSER_CREATE_SESSION: '1',
      },
    },
  )
  expect(viewerFixture.status, viewerFixture.stderr).toBe(0)
  const fixture = JSON.parse(viewerFixture.stdout) as { id: string; session: string }
  const viewerContext = await browser.newContext({ baseURL: 'http://localhost:5180' })
  try {
    await viewerContext.addCookies([
      {
        name: 'civiclens_session',
        value: fixture.session,
        domain: 'localhost',
        path: '/api',
        httpOnly: true,
        secure: false,
        sameSite: 'Lax',
      },
    ])
    const viewer = await viewerContext.newPage()
    viewer.on('pageerror', (error) => errors.push(error.message))
    await viewer.route('https://tile.openstreetmap.org/**', (route) => route.abort())
    await viewer.goto('/citizen/nearby')
    await viewer.getByLabel('Map latitude').fill('12.982')
    await viewer.getByLabel('Map longitude').fill('77.605')
    await viewer.getByRole('button', { name: 'Set map center' }).click()
    await expect(viewer.locator('.category-map-marker')).toHaveCount(1)
    const visible = await (
      await viewer.request.get('/api/citizen/issues/nearby', {
        params: { latitude: '12.982', longitude: '77.605', radiusKm: '200' },
      })
    ).json()
    expect(visible.items).toHaveLength(1)
    expect(JSON.stringify(visible)).not.toContain(ids[0])
    expect(JSON.stringify(visible)).not.toContain(ids[1])
    expect(JSON.stringify(visible)).not.toContain(ids[2])
    await viewer.locator('.category-map-marker').click()
    await expect(
      viewer.locator('.leaflet-popup').getByRole('link', { name: 'View public issue' }),
    ).toHaveAttribute('href', '/issues/' + published[0].publicIssueId)
    await viewer.getByRole('button', { name: '200 km', exact: true }).click()
    await expect(viewer.getByText(/1 visible reports loaded within 200 km/)).toBeVisible()
    await viewer.getByRole('button', { name: 'List view' }).click()
    await expect(viewer.getByText(/0.00 km from search center/)).toBeVisible()
    await viewer.getByRole('link', { name: 'View public issue' }).click()
    await expect(viewer.getByRole('heading', { name: published[0].summary })).toBeVisible()
    await expect(
      viewer.getByText('Private complaint notes must not appear in the approved public map.'),
    ).toHaveCount(0)
    await viewer.screenshot({ path: 'test-results/phase5-public-issue.png', fullPage: true })
    expect(
      (await new AxeBuilder({ page: viewer }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze())
        .violations,
    ).toEqual([])
  } finally {
    await viewerContext.close()
  }
  await page.goto(`/citizen/complaints/${ids[0]}`)
  await page.getByRole('button', { name: 'Withdraw publication request' }).click()
  await expect(page.getByText('Publication status: PRIVATE')).toBeVisible()
  expect(
    (await page.request.get('/api/public/issues/' + published[0].publicIssueId)).status(),
  ).toBe(404)
  expect(
    (await (await page.request.get('/api/public/issues', { params: region })).json()).items,
  ).toHaveLength(0)
  await page.goto('/citizen/nearby')
  await page.getByRole('button', { name: 'Search near my latest complaint' }).click()
  await expect(page.locator('.nearby-result')).toHaveCount(3)
  await expect(page.getByText('My Report · Not Publicly Visible', { exact: true })).toHaveCount(3)
  expect(errors).toEqual([])
})
