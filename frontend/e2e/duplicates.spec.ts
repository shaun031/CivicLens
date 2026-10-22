import { expect, test } from './fixtures.js'
import AxeBuilder from '@axe-core/playwright'
import { randomUUID } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { resolve } from 'node:path'

test('private duplicate review, filters, responsive comparison and durable dismissal', async ({
  page,
}) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const password = `Phase six browser passphrase ${randomUUID()}`
  const origin = { Origin: 'http://localhost:5180' }
  await page.goto('/')
  const ids: string[] = []
  for (let index = 0; index < 2; index++) {
    const email = `phase6-citizen-${randomUUID()}@example.com`
    expect(
      (
        await page.request.post('/api/auth/register', {
          headers: origin,
          data: {
            display_name: 'Synthetic Matching Citizen',
            email,
            password,
            confirm_password: password,
          },
        })
      ).status(),
    ).toBe(201)
    expect(
      (
        await page.request.post('/api/auth/login', { headers: origin, data: { email, password } })
      ).status(),
    ).toBe(200)
    const response = await page.request.post('/api/complaints', {
      headers: { ...origin, 'Idempotency-Key': randomUUID() },
      multipart: {
        title: 'Large pothole at phase six school entrance',
        description:
          'Large deep pothole near school entrance dangerous road traffic requires inspection.',
        category: 'POTHOLE',
        reportedSeverity: 'HIGH',
        latitude: String(12.94 + index * 0.00001),
        longitude: '77.56',
      },
    })
    expect(response.status()).toBe(201)
    ids.push((await response.json()).complaintId)
    expect((await page.request.get('/api/admin/duplicate-candidates')).status()).toBe(403)
    await page.request.post('/api/auth/logout', { headers: origin })
  }
  const administrator = `phase6-admin-${randomUUID()}@example.com`
  const provision = spawnSync(
    resolve('../backend/.venv/Scripts/python.exe'),
    [resolve('../tests/integration/provision_browser_admin.py')],
    {
      cwd: resolve('../backend'),
      encoding: 'utf8',
      env: { ...process.env, BROWSER_ADMIN_EMAIL: administrator, BROWSER_ADMIN_PASSWORD: password },
    },
  )
  expect(provision.status).toBe(0)
  await page.goto('/admin/duplicate-candidates')
  await page.getByLabel('Email', { exact: true }).fill(administrator)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.getByLabel('Complaint ID to recheck').fill(ids[1])
  const matchingResponse = page.waitForResponse(
    (response) =>
      response.url().includes(`/complaints/${ids[1]}/duplicate-check`) &&
      response.request().method() === 'POST',
  )
  await page.getByRole('button', { name: 'Recheck complaint' }).click()
  expect((await matchingResponse).status()).toBe(200)
  await expect(page.getByText(/Matching state: COMPLETE/)).toBeVisible()
  await page.getByLabel('Search titles').fill('phase six school')
  await page.getByRole('button', { name: 'Apply filters' }).click()
  await page.getByRole('link', { name: 'Compare evidence' }).click()
  await expect(page.getByText('Unavailable — not zero')).toBeVisible()
  await expect(
    page.getByRole('heading', { name: 'Large pothole at phase six school entrance' }),
  ).toHaveCount(2)
  await expect(
    page.getByText(/Effective weights: geographic 0.50, text 0.50, image 0.00/),
  ).toBeVisible()
  for (const width of [375, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true)
    expect(
      (await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze())
        .violations,
    ).toEqual([])
    await page.screenshot({ path: `test-results/phase6-comparison-${width}.png`, fullPage: true })
  }
  await expect(page.getByRole('button', { name: /^merge/i })).toHaveCount(0)
  await page.getByRole('button', { name: 'Dismiss candidate' }).click()
  await expect(page.getByText('DISMISSED', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Rerun matching' }).click()
  await expect(page.getByText('Matching state: COMPLETE', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByText('DISMISSED', { exact: true })).toBeVisible()
  expect(errors).toEqual([])
})
