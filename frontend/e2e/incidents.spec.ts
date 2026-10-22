import { expect, test } from './fixtures.js'
import AxeBuilder from '@axe-core/playwright'
import { randomUUID } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { resolve } from 'node:path'

test('private master incidents merge, split, responsive map, history and safe citizen association', async ({
  page,
}) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const headers = { Origin: 'http://localhost:5180' }
  const password = `Phase seven browser passphrase ${randomUUID()}`
  const citizen = `incident-citizen-${randomUUID()}@example.com`
  const admin = `incident-admin-${randomUUID()}@example.com`
  await page.goto('/')
  const registered = await page.request.post('/api/auth/register', {
    headers,
    data: {
      display_name: 'Synthetic Incident Citizen',
      email: citizen,
      password,
      confirm_password: password,
    },
  })
  expect(registered.status()).toBe(201)
  expect(
    (
      await page.request.post('/api/auth/login', { headers, data: { email: citizen, password } })
    ).status(),
  ).toBe(200)
  const ids: string[] = []
  for (let index = 0; index < 2; index++) {
    const result = await page.request.post('/api/complaints', {
      headers: {
        ...headers,
        'Idempotency-Key': randomUUID(),
      },
      multipart: {
        title: `Phase seven pothole report ${index + 1}`,
        description: 'Deep pothole at the same school entrance near the traffic crossing.',
        category: 'POTHOLE',
        reportedSeverity: 'HIGH',
        latitude: String(12.91 + index * 0.00001),
        longitude: '77.51',
      },
    })
    expect(result.status()).toBe(201)
    ids.push((await result.json()).complaintId)
  }
  expect((await page.request.get('/api/admin/incidents')).status()).toBe(403)
  await page.request.post('/api/auth/logout', { headers })
  const provision = spawnSync(
    resolve('../backend/.venv/Scripts/python.exe'),
    [resolve('../tests/integration/provision_browser_admin.py')],
    {
      cwd: resolve('../backend'),
      encoding: 'utf8',
      env: {
        ...process.env,
        BROWSER_ADMIN_EMAIL: admin,
        BROWSER_ADMIN_PASSWORD: password,
      },
    },
  )
  expect(provision.status, provision.stderr).toBe(0)
  await page.goto('/admin/incidents')
  await page.getByLabel('Email', { exact: true }).fill(admin)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Master incidents', exact: true })).toBeVisible()
  for (const id of ids)
    expect(
      (
        await page.request.post(`/api/admin/complaints/${id}/duplicate-check`, { headers })
      ).status(),
    ).toBe(200)
  const catalog = await (await page.request.get('/api/admin/incidents?limit=50')).json()
  const incidents = catalog.items.filter((item: { representativeComplaintId: string }) =>
    ids.includes(item.representativeComplaintId),
  )
  expect(incidents).toHaveLength(2)
  const [source, target] = incidents
  await page.goto(`/admin/incidents/${source.incidentId}`)
  await expect(
    page.getByRole('region', { name: 'Private administrator incident map' }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Merge incidents', exact: true }).click()
  await page.getByLabel('Target incident ID').fill(target.incidentId)
  await page.getByRole('button', { name: 'Load target for confirmation' }).click()
  await expect(page.getByText(/Target: Phase seven pothole report/)).toBeVisible()
  await page
    .getByLabel('Written correction reason')
    .fill('Administrator reviewed the same physical pothole and both reports')
  await page.getByLabel(/I reviewed the locations/).check()
  await page.getByLabel(/I confirm this membership/).check()
  await page.getByRole('button', { name: 'Apply confirmed operation' }).click()
  await expect(page).toHaveURL(new RegExp(`/admin/incidents/${target.incidentId}$`))
  await expect(page.getByLabel(/^Select Phase seven pothole report/)).toHaveCount(2)
  await expect(page.getByRole('heading', { name: 'MERGE', exact: true })).toBeVisible()
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true)
    expect(
      (await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze())
        .violations,
    ).toEqual([])
    await page.screenshot({ path: `test-results/phase7-incident-${width}.png`, fullPage: true })
  }
  await page
    .getByLabel(/^Select Phase seven pothole report/)
    .first()
    .check()
  await page.getByRole('button', { name: 'Split selected reports' }).click()
  await page
    .getByLabel('Written correction reason')
    .fill('Correcting the grouping after additional physical issue review')
  await page.getByLabel(/I confirm this membership/).check()
  await page.getByRole('button', { name: 'Apply confirmed operation' }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.getByLabel(/^Select Phase seven pothole report/)).toHaveCount(1)
  await expect(page.getByRole('heading', { name: 'SPLIT', exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByLabel(/^Select Phase seven pothole report/)).toHaveCount(1)
  await page.request.post('/api/auth/logout', { headers })
  await page.request.post('/api/auth/login', { headers, data: { email: citizen, password } })
  await page.goto(`/citizen/complaints/${ids[0]}`)
  await expect(page.getByRole('heading', { name: 'Associated incident' })).toBeVisible()
  const safe = await (await page.request.get(`/api/complaints/${ids[0]}/incident`)).json()
  expect(Object.keys(safe).sort()).toEqual(['category', 'incidentId', 'processing', 'status'])
  await expect(page.getByText('Eligible unique reporters', { exact: true })).toHaveCount(0)
  expect(errors).toEqual([])
})
