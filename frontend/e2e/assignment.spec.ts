import { expect, test, type Page } from './fixtures.js'
import AxeBuilder from '@axe-core/playwright'
import { randomUUID } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { resolve } from 'node:path'

async function accessibility(page: Page) {
  await page.evaluate(async () => {
    await Promise.all(document.getAnimations().filter(animation => Number.isFinite(Number(animation.effect?.getComputedTiming().endTime))).map(animation => animation.finished.catch(() => undefined)))
  })
  return new AxeBuilder({ page }).analyze()
}

test('trusted department membership, manual allocation, officer progress, reassignment and privacy', async ({
  page,
}) => {
  test.setTimeout(240000)
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const headers = { Origin: 'http://localhost:5181' }
  const password = `Municipal browser passphrase ${randomUUID()}`
  const administrator = `allocation-admin-${randomUUID()}@example.com`
  const officer = `allocation-officer-${randomUUID()}@example.com`
  const citizen = `allocation-citizen-${randomUUID()}@example.com`
  function provision(email: string, role: string) {
    const result = spawnSync(
      resolve('../backend/.venv/Scripts/python.exe'),
      [resolve('../tests/integration/provision_browser_admin.py')],
      {
        cwd: resolve('../backend'),
        windowsHide: true,
        encoding: 'utf8',
        env: {
          ...process.env,
          CIVICLENS_BROWSER_DB_PATH: process.env.CIVICLENS_ALLOCATION_BROWSER_DB_PATH,
          BROWSER_ADMIN_EMAIL: email,
          BROWSER_ADMIN_PASSWORD: password,
          BROWSER_STAFF_ROLE: role,
        },
      },
    )
    expect(result.status, result.stderr).toBe(0)
    return result.stdout.trim()
  }
  function processEvents() {
    const result = spawnSync(
      resolve('../backend/.venv/Scripts/python.exe'),
      ['-m', 'app.scripts.run_worker', '--max-batches', '10'],
      {
        cwd: resolve('../backend'),
        windowsHide: true,
        encoding: 'utf8',
        env: {
          ...process.env,
          APP_ENV: 'test',
          AUTH_PROVIDER: 'local',
          COMPLAINT_PROVIDER: 'sqlite',
          EVIDENCE_PROVIDER: 'local',
          DEBUG: 'false',
          LOG_LEVEL: 'ERROR',
          LOCAL_DB_PATH: process.env.CIVICLENS_ALLOCATION_BROWSER_DB_PATH,
          LOCAL_EVIDENCE_ROOT: process.env.CIVICLENS_ALLOCATION_BROWSER_DB_PATH + '-evidence',
        },
      },
    )
    expect(result.status, result.stderr).toBe(0)
  }
  await page.goto('/')
  expect(
    (
      await page.request.post('/api/auth/register', {
        headers,
        data: {
          display_name: 'Allocation Citizen',
          email: citizen,
          password,
          confirm_password: password,
        },
      })
    ).status(),
  ).toBe(201)
  await page.request.post('/api/auth/login', { headers, data: { email: citizen, password } })
  const title = `Municipal work pothole ${randomUUID().slice(0, 8)}`
  const response = await page.request.post('/api/complaints', {
    headers: { ...headers, 'Idempotency-Key': randomUUID() },
    multipart: {
      title,
      description:
        'Synthetic municipal road defect near the public library for assignment inspection.',
      category: 'POTHOLE',
      reportedSeverity: 'LOW',
      latitude: '12.97',
      longitude: '77.59',
    },
  })
  expect(response.status()).toBe(201)
  const complaint = (await response.json()).complaintId
  expect((await page.request.get('/api/admin/assignments')).status()).toBe(403)
  await page.request.post('/api/auth/logout', { headers })
  provision(administrator, 'ADMIN')
  const officerId = provision(officer, 'OFFICER')
  await page.goto('/admin/departments')
  await page.getByLabel('Email', { exact: true }).fill(administrator)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Municipal departments' })).toBeVisible()
  async function confirm() {
    const dialog = page.getByRole('dialog')
    await dialog
      .getByLabel('Assignment or progress reason')
      .fill('Private operational allocation review confirms the recorded municipal decision')
    await dialog.getByLabel(/I confirm this municipal work change/).check()
    await dialog.getByRole('button', { name: 'Confirm and save work change' }).click()
    await expect(dialog).toHaveCount(0)
  }
  await page.getByRole('button', { name: 'Seed demonstration departments' }).click()
  await confirm()
  const departments = await (await page.request.get('/api/admin/departments')).json()
  const department = departments.items.find((d: { code: string }) => d.code === 'ROAD_MAINTENANCE')
  expect(department).toBeTruthy()
  await page.goto(`/admin/departments/${department.id}`)
  await page.getByRole('button', { name: 'Add officer membership' }).click()
  const directory = await (await page.request.get('/api/admin/officers')).json()
  expect(directory.items.some((o: { officerId: string }) => o.officerId === officerId)).toBe(true)
  await page.getByLabel('Provisioned officer').selectOption(officerId)
  await page.getByLabel('Weighted workload capacity (blank means unknown)').fill('20')
  await confirm()
  await expect(page.getByText('AVAILABLE', { exact: true })).toBeVisible()
  expect(
    (
      await page.request.post(`/api/admin/complaints/${complaint}/duplicate-check`, { headers })
    ).status(),
  ).toBe(200)
  const catalog = await (await page.request.get('/api/admin/incidents?limit=50')).json()
  const incident = catalog.items.find(
    (i: { representativeComplaintId: string }) => i.representativeComplaintId === complaint,
  )
  expect(incident).toBeTruthy()
  await page.goto(`/admin/assignments/${incident.incidentId}`)
  await page.getByRole('button', { name: 'Route department automatically' }).click()
  await confirm()
  await expect(page.getByRole('heading', { name: /Recommended officers/ })).toBeVisible()
  await expect(page.getByText('No officer assigned', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Assign or reassign work' }).click()
  await page.getByLabel('Eligible officer ID (blank removes officer)').fill(officerId)
  await confirm()
  await expect(page.getByText('OFFICER_ASSIGNED', { exact: true }).first()).toBeVisible()
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true)
    expect(
      (await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze()).violations,
    ).toEqual([])
    await page.screenshot({ path: `test-results/phase9-assignment-${width}.png`, fullPage: true })
  }
  await page.request.post('/api/auth/logout', { headers })
  await page.goto('/officer/dashboard')
  await page.getByLabel('Email', { exact: true }).fill(officer)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Officer dashboard' })).toBeVisible()
  await page.getByRole('link', { name: 'Open assigned incident' }).click()
  await page.getByRole('button', { name: 'Start work', exact: true }).click()
  await page
    .getByLabel('Private operational progress note')
    .fill('Crew inspected the road surface and prepared a safe temporary working area')
  await page.getByLabel('Work percentage (not verified resolution)').fill('10')
  await confirm()
  await expect(page.getByRole('button', { name: 'Record progress' })).toBeVisible()
  await page.getByRole('button', { name: 'Record progress' }).click()
  await page
    .getByLabel('Private operational progress note')
    .fill('Municipal work is blocked pending equipment; administrator review requested')
  await page.getByLabel('Work percentage (not verified resolution)').fill('30')
  await page.getByLabel('Blocked work: request administrative review').check()
  await confirm()
  await expect(page.getByText('NEEDS_REVIEW', { exact: true }).first()).toBeVisible()
  await page.reload()
  await expect(page.getByText(/Municipal work is blocked pending equipment/)).toBeVisible()
  expect(
    (
      await page.request.post(`/api/admin/incidents/${incident.incidentId}/unassign-officer`, {
        headers,
        data: {},
      })
    ).status(),
  ).toBe(403)
  await page.request.post('/api/auth/logout', { headers })
  await page.request.post('/api/auth/login', { headers, data: { email: administrator, password } })
  const state = await (
    await page.request.get(`/api/admin/incidents/${incident.incidentId}/assignment`)
  ).json()
  expect(state.incidentStatus).toBe('OPEN')
  expect(
    (
      await page.request.post(`/api/admin/incidents/${incident.incidentId}/unassign-officer`, {
        headers,
        data: {
          operationId: randomUUID(),
          expectedIncidentVersion: state.incidentVersion,
          expectedAssignmentVersion: state.assignment.version,
          confirmed: true,
          reason: 'Administrator reviewed blocked work and returned allocation for reassignment',
        },
      })
    ).status(),
  ).toBe(200)
  await page.request.post('/api/auth/logout', { headers })
  await page.request.post('/api/auth/login', { headers, data: { email: officer, password } })
  expect((await page.request.get(`/api/officer/incidents/${incident.incidentId}`)).status()).toBe(
    404,
  )
  await page.request.post('/api/auth/logout', { headers })
  await page.request.post('/api/auth/login', { headers, data: { email: citizen, password } })
  const own = await page.request.get(`/api/complaints/${complaint}/incident`)
  expect(own.status()).toBe(200)
  processEvents()
  await page.goto('/citizen/notifications')
  await expect(page.getByRole('heading', { name: 'Complaint received', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Work started', exact: true })).toBeVisible()
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true)
    expect((await accessibility(page)).violations).toEqual([])
    await page.screenshot({
      path: `test-results/phase10-notifications-${width}.png`,
      fullPage: true,
    })
  }
  await page.getByRole('button', { name: 'Mark all as read' }).click()
  await expect(page.getByText('Unread: 0', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByText('Unread: 0', { exact: true })).toBeVisible()
  await page.request.post('/api/auth/logout', { headers })
  await page.request.post('/api/auth/login', { headers, data: { email: administrator, password } })
  await page.goto('/admin/workflows')
  await expect(page.getByRole('heading', { name: 'Workflow operations' })).toBeVisible()
  await expect(page.getByText('IncidentTriageWorkflow', { exact: false }).first()).toBeVisible()
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true)
    expect((await accessibility(page)).violations).toEqual([])
    await page.screenshot({ path: `test-results/phase10-workflows-${width}.png`, fullPage: true })
  }
  expect(await own.text()).not.toContain('Private operational')
  expect(
    (await page.request.get(`/api/officer/incidents/${incident.incidentId}/history`)).status(),
  ).toBe(403)
  await page.goto('/admin/command-center')
  await page.getByText('Additional operational context', { exact: true }).click()
  await page.getByText('Source snapshot & reporting context', { exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Eligible complaint reports' })).toBeVisible()
  await expect(page.getByText(/Consistent source snapshot/)).toBeVisible()
  await page.getByLabel('Infrastructure category').selectOption('POTHOLE')
  await page.getByRole('button', { name: 'Apply analytics filters' }).click()
  await expect(page).toHaveURL(/category=POTHOLE/)
  await expect(page.getByRole('heading', { name: 'Urgent incident queue' })).toBeVisible()
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true)
    expect((await accessibility(page)).violations).toEqual([])
    await page.screenshot({
      path: `test-results/phase11-command-center-${width}.png`,
      fullPage: true,
    })
  }
  await page.goto('/admin/analytics/departments')
  await expect(page.getByRole('heading', { name: 'Department operations' })).toBeVisible()
  await page.goto('/admin/analytics/officers')
  await expect(page.getByRole('heading', { name: 'Officer workloads and capacity' })).toBeVisible()
  await page.goto('/admin/hotspots')
  await expect(page.getByRole('heading', { name: 'Accessible occupied-cell list' })).toBeVisible()
  await expect(page.locator('.leaflet-container')).toBeVisible()
  await page.getByLabel('Map measure').selectOption('reportCount')
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true)
    expect((await accessibility(page)).violations).toEqual([])
    await page.screenshot({ path: `test-results/phase11-hotspots-${width}.png`, fullPage: true })
  }
  await page.goto('/admin/reports')
  await expect(page.getByRole('heading', { name: 'Report preview' })).toBeVisible()
  const downloadEvent = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export CSV', exact: true }).click()
  const download = await downloadEvent
  expect(download.suggestedFilename()).toMatch(/^civiclens-citywide-\d{4}-\d{2}-\d{2}\.csv$/)
  expect(await download.failure()).toBeNull()
  expect((await accessibility(page)).violations).toEqual([])
  await page.screenshot({ path: 'test-results/phase11-reports.png', fullPage: true })
  expect(await page.locator('main').innerText()).not.toContain(
    'Municipal work is blocked pending equipment',
  )
  // Phase12: restore eligible work, submit repair, record citizen feedback, approve and inspect
  // private geographic indicators. This remains the isolated browser fixture database.
  const repairAssignment = await (
    await page.request.get(`/api/admin/incidents/${incident.incidentId}/assignment`)
  ).json()
  const reassignRepair = await page.request.post(
    `/api/admin/incidents/${incident.incidentId}/assign-officer`,
    {
      headers,
      data: {
        operationId: randomUUID(),
        confirmed: true,
        reason: 'Administrator reviewed and restored the officer for actual repair verification',
        expectedIncidentVersion: repairAssignment.incidentVersion,
        expectedAssignmentVersion: repairAssignment.assignment.version,
        officerId,
      },
    },
  )
  expect(reassignRepair.status(), await reassignRepair.text()).toBe(200)
  await page.request.post('/api/auth/logout', { headers })
  await page.request.post('/api/auth/login', { headers, data: { email: officer, password } })
  const repairWork = await (
    await page.request.get(`/api/officer/incidents/${incident.incidentId}`)
  ).json()
  const startRepair = await page.request.post(
    `/api/officer/incidents/${incident.incidentId}/start`,
    {
      headers,
      data: {
        operationId: randomUUID(),
        confirmed: true,
        reason: 'Officer starting reviewed physical repair work',
        expectedIncidentVersion: repairWork.incidentVersion,
        expectedAssignmentVersion: repairWork.assignment.version,
        percentage: 0,
        note: 'New repair cycle started after work-allocation review',
      },
    },
  )
  expect(startRepair.status(), await startRepair.text()).toBe(200)
  await page.goto(`/officer/incidents/${incident.incidentId}/repair`)
  await page
    .getByLabel('Repair description', { exact: true })
    .fill('The reported physical road surface was repaired and inspected for citizen verification.')
  const localTime = await page.evaluate(() => {
    const value = new Date(Date.now() - 1000)
    value.setMinutes(value.getMinutes() - value.getTimezoneOffset())
    return value.toISOString().slice(0, 19)
  })
  await page.getByLabel('Repair completed at (your local time)').fill(localTime)
  await page.getByRole('button', { name: 'Submit repair for verification' }).click()
  await expect(
    page.getByRole('heading', { name: 'Attempt 1 · PENDING_VERIFICATION' }),
  ).toBeVisible()
  expect((await page.request.get('/api/admin/repairs/pending')).status()).toBe(403)
  await page.request.post('/api/auth/logout', { headers })
  await page.request.post('/api/auth/login', { headers, data: { email: citizen, password } })
  await page.goto('/citizen/verification')
  await page.getByRole('button', { name: 'Verify repair / view response' }).click()
  await page.getByLabel('Repair response').selectOption('CONFIRMED_FIXED')
  await page
    .getByLabel('Optional feedback')
    .fill('The repaired road is usable at my reported location.')
  await page.getByRole('button', { name: 'Record verification response' }).click()
  await expect(page.getByText(/Your recorded response: CONFIRMED_FIXED/)).toBeVisible()
  expect(
    (
      await page.request.post(`/api/admin/repairs/${incident.incidentId}/approve`, {
        headers,
        data: {},
      })
    ).status(),
  ).toBe(403)
  await page.request.post('/api/auth/logout', { headers })
  await page.request.post('/api/auth/login', { headers, data: { email: administrator, password } })
  await page.goto('/admin/repair-verification')
  await page.getByRole('button', { name: 'Review repair attempt' }).click()
  await page
    .getByLabel('Decision reason / independent verification basis')
    .fill(
      'Independent administrator site inspection reviewed the physical repair, hazard assessment and the recorded citizen confirmation.',
    )
  await page
    .getByLabel('I reviewed current evidence, feedback, hazards and incident membership.')
    .check()
  await page.getByRole('button', { name: 'approve', exact: true }).click()
  await expect(page.getByText(/Recorded verified resolution:/)).toBeVisible()
  await page.goto('/admin/recurrences')
  await expect(
    page.getByRole('heading', { name: 'Recurring infrastructure failures' }),
  ).toBeVisible()
  await page.goto('/admin/fairness')
  await expect(page.getByRole('heading', { name: 'Geographic service comparison' })).toBeVisible()
  await expect(page.locator('.leaflet-container')).toBeVisible()
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true)
    expect((await accessibility(page)).violations).toEqual([])
    await page.screenshot({ path: `test-results/phase12-fairness-${width}.png`, fullPage: true })
  }
  expect(errors).toEqual([])
})
