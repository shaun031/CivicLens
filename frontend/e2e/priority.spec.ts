import { expect, test } from './fixtures.js'
import AxeBuilder from '@axe-core/playwright'
import { randomUUID } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { resolve } from 'node:path'

test('verified priority assessments, hazard-first policy, override removal, ranking and privacy', async ({
  page,
}) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const headers = { Origin: 'http://localhost:5180' }
  const password = `Phase eight secure browser phrase ${randomUUID()}`
  const citizen = `priority-citizen-${randomUUID()}@example.com`
  const administrator = `priority-admin-${randomUUID()}@example.com`
  const title = `Phase eight pothole ${randomUUID().slice(0, 8)}`
  const privateReason = 'Private site inspection confirms the defect at this access point'
  await page.goto('/')
  expect(
    (
      await page.request.post('/api/auth/register', {
        headers,
        data: {
          display_name: 'Priority Test Citizen',
          email: citizen,
          password,
          confirm_password: password,
        },
      })
    ).status(),
  ).toBe(201)
  await page.request.post('/api/auth/login', { headers, data: { email: citizen, password } })
  const created = await page.request.post('/api/complaints', {
    headers: { ...headers, 'Idempotency-Key': randomUUID() },
    multipart: {
      title,
      description: 'Deep pothole at the marked pedestrian crossing requires inspection.',
      category: 'POTHOLE',
      reportedSeverity: 'HIGH',
      latitude: '12.92',
      longitude: '77.52',
    },
  })
  expect(created.status()).toBe(201)
  const report = (await created.json()).complaintId
  expect((await page.request.get('/api/admin/incidents/priorities')).status()).toBe(403)
  await page.request.post('/api/auth/logout', { headers })
  const provision = spawnSync(
    resolve('../backend/.venv/Scripts/python.exe'),
    [resolve('../tests/integration/provision_browser_admin.py')],
    {
      cwd: resolve('../backend'),
      encoding: 'utf8',
      env: { ...process.env, BROWSER_ADMIN_EMAIL: administrator, BROWSER_ADMIN_PASSWORD: password },
    },
  )
  expect(provision.status, provision.stderr).toBe(0)
  await page.goto('/admin/priorities')
  await page.getByLabel('Email', { exact: true }).fill(administrator)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Incident priority queue' })).toBeVisible()
  expect(
    (
      await page.request.post(`/api/admin/complaints/${report}/duplicate-check`, { headers })
    ).status(),
  ).toBe(200)
  const catalog = await (await page.request.get('/api/admin/incidents?limit=50')).json()
  const incident = catalog.items.find(
    (row: { representativeComplaintId: string }) => row.representativeComplaintId === report,
  )
  expect(incident).toBeTruthy()
  await page.goto(`/admin/incidents/${incident.incidentId}`)
  await expect(page.getByText('Priority not calculated', { exact: true })).toBeVisible()
  async function confirm() {
    const dialog = page.getByRole('dialog')
    await dialog.getByLabel('Priority assessment or correction reason').fill(privateReason)
    await dialog.getByLabel(/I confirm this assessed change/).check()
    await dialog.getByRole('button', { name: 'Save confirmed priority operation' }).click()
    await expect(dialog).toHaveCount(0)
  }
  await page.getByRole('button', { name: 'Recalculate priority', exact: true }).click()
  await confirm()
  await expect(page.getByRole('progressbar', { name: 'Severity contribution' })).toHaveAttribute(
    'aria-valuenow',
    '12',
  )
  await page.getByRole('button', { name: 'Assess severity', exact: true }).click()
  await page.getByRole('dialog').getByLabel('Assessment score (0–10)').fill('8')
  await page.getByRole('dialog').getByLabel(title, { exact: true }).check()
  await confirm()
  await page.getByRole('button', { name: 'Assess public impact', exact: true }).click()
  await page.getByRole('dialog').getByLabel('Assessment score (0–10)').fill('7')
  await page.getByRole('dialog').getByLabel(title, { exact: true }).check()
  await confirm()
  await expect(page.getByText('VERIFIED', { exact: true }).first()).toBeVisible()
  await page.getByRole('button', { name: 'Review urgent hazard', exact: true }).click()
  await page
    .getByRole('dialog')
    .getByLabel(/I verified an urgent hazard/)
    .check()
  await page.getByRole('dialog').getByLabel(title, { exact: true }).check()
  await confirm()
  await expect(page.getByText('VERIFIED URGENT HAZARD', { exact: true }).first()).toBeVisible()
  await page.getByRole('button', { name: 'Create priority override', exact: true }).click()
  await page.getByRole('dialog').getByLabel('Override score (0–100)').fill('10')
  await confirm()
  await expect(page.getByText('100/100 · CRITICAL', { exact: true }).first()).toBeVisible()
  await page.getByRole('button', { name: 'Remove priority override', exact: true }).click()
  await confirm()
  await page.getByRole('button', { name: 'Review urgent hazard', exact: true }).click()
  // An explicit unchecked flag removes escalation, with the same mandatory audited reason.
  await confirm()
  await page.reload()
  await expect(page.getByText('Override: REMOVED', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('VERIFIED URGENT HAZARD', { exact: true }).first()).not.toBeVisible()
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true)
    expect(
      (await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze())
        .violations,
    ).toEqual([])
    await page.screenshot({ path: `test-results/phase8-breakdown-${width}.png`, fullPage: true })
  }
  await page.goto('/admin/priorities')
  await page.getByLabel('Search priority incidents').fill(title)
  await page.getByRole('button', { name: 'Apply priority filters' }).click()
  await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible()
  await page.screenshot({ path: 'test-results/phase8-priority-queue.png', fullPage: true })
  await page.request.post('/api/auth/logout', { headers })
  await page.request.post('/api/auth/login', { headers, data: { email: citizen, password } })
  await page.goto(`/citizen/complaints/${report}`)
  await expect(page.getByRole('heading', { name: 'Associated incident' })).toBeVisible()
  await expect(page.getByText(privateReason, { exact: true })).toHaveCount(0)
  expect(
    (await page.request.get(`/api/admin/incidents/${incident.incidentId}/priority`)).status(),
  ).toBe(403)
  expect(
    Object.keys(await (await page.request.get(`/api/complaints/${report}/incident`)).json()).sort(),
  ).toEqual(['category', 'incidentId', 'processing', 'status'])
  expect(errors).toEqual([])
})
