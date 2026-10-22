import { expect, test, type Page } from './fixtures.js'
import { randomUUID } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { resolve } from 'node:path'
import AxeBuilder from '@axe-core/playwright'

const origin = { Origin: 'http://localhost:5180' }
async function citizen(page: Page) {
  const email = `map-${randomUUID()}@example.com`
  const password = `Private map passphrase ${randomUUID()}`
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
        BROWSER_STAFF_ROLE: 'CITIZEN',
      },
    },
  )
  expect(provision.status, provision.stderr).toBe(0)
  expect(
    (
      await page.request.post('/api/auth/login', { headers: origin, data: { email, password } })
    ).status(),
  ).toBe(200)
}

test('removed development status is absent from desktop/mobile navigation; health remains operational', async ({
  page,
}) => {
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/')
    if (width === 375) await page.getByRole('button', { name: 'Toggle navigation' }).click()
    await expect(page.locator('a[href="/status"]')).toHaveCount(0)
    await expect(
      page.getByText(/Project status|Development status|Backend connectivity/),
    ).toHaveCount(0)
    await page.goto('/status')
    await expect(page.getByRole('heading', { name: 'Page not found' })).toBeVisible()
    await page.getByRole('link', { name: 'Return home' }).click()
    await expect(page).toHaveURL('http://localhost:5180/')
  }
  expect((await page.request.get('/api/health')).status()).toBe(200)
})

test('real map selection, marker drag, geolocation, responsive resizing and SQLite submission', async ({
  page,
  context,
}, testInfo) => {
  test.setTimeout(180000)
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  // Exercise the real Leaflet controls without bulk traffic to shared OSM services.
  await page.route('https://tile.openstreetmap.org/**', (route) => route.abort())
  await citizen(page)
  await page.goto('/citizen/report')
  const map = page.locator('.civic-location-map')
  const selected = page.getByRole('region', { name: 'Selected location', exact: true })
  await expect(map).toBeVisible()
  await expect(page.getByLabel('Latitude', { exact: true })).toHaveValue('')
  await expect(page.getByLabel('Longitude', { exact: true })).toHaveValue('')
  await expect(page.locator('.location-selection-marker')).toHaveCount(0)
  await expect(selected).toContainText('Click on the map or use your current location')
  await expect(page.getByText("Map tiles couldn't load.", { exact: false })).toBeVisible()
  await expect(page.locator('.leaflet-control-attribution')).toContainText('OpenStreetMap')
  expect(
    await page
      .locator('.leaflet-pane')
      .first()
      .evaluate((el) => getComputedStyle(el).position),
  ).toBe('absolute')

  // An unselected map center must never become a submitted complaint.
  await page.getByLabel('Complaint category').selectOption('POTHOLE')
  await page.getByLabel('Complaint title').fill('Pothole selected using the interactive map')
  await page
    .getByLabel('Description', { exact: true })
    .fill('Uneven road beside the library needs inspection for cyclist safety.')
  await page.getByRole('button', { name: 'Submit Complaint', exact: true }).click()
  await expect(page.locator('#latitude-error')).toBeVisible()

  for (const width of [375, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    await map.scrollIntoViewIfNeeded()
    await expect
      .poll(() => map.evaluate((el) => Math.round(el.getBoundingClientRect().height)))
      .toBe(width < 768 ? 330 : 450)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    const card = page.locator('.report-location')
    expect((await map.boundingBox())!.width).toBeGreaterThan(
      (await card.boundingBox())!.width * 0.7,
    )
    await map.click({ position: { x: (await map.boundingBox())!.width * 0.6, y: 150 } })
    await expect(page.locator('.location-selection-marker')).toHaveCount(1)
    const lat = await page.getByLabel('Latitude', { exact: true }).inputValue()
    await expect(selected).toContainText(lat)
    await page.screenshot({
      path: testInfo.outputPath(`location-${width}.png`),
      fullPage: true,
      animations: 'disabled',
    })
  }

  const marker = page.locator('.location-selection-marker')
  const latBefore = await page.getByLabel('Latitude', { exact: true }).inputValue()
  await marker.scrollIntoViewIfNeeded()
  const box = (await marker.boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width / 2 + 55, box.y + box.height / 2 - 30, { steps: 12 })
  await page.mouse.up()
  await expect(page.getByLabel('Latitude', { exact: true })).not.toHaveValue(latBefore)
  await expect(marker).toHaveCount(1)

  // A sidebar-only resize must update Leaflet's internal pixel origin, not just CSS.
  await page.getByRole('button', { name: 'Collapse sidebar' }).click()
  await page.getByRole('button', { name: 'Expand sidebar' }).click()
  await map.scrollIntoViewIfNeeded()
  await page.locator('.leaflet-control-zoom-in').click()
  await expect(marker).toBeVisible()

  await context.setGeolocation({ latitude: 13.0827, longitude: 80.2707, accuracy: 25 })
  await context.grantPermissions(['geolocation'])
  await page.getByRole('button', { name: 'Use my current location', exact: true }).click()
  await expect(page.getByLabel('Latitude', { exact: true })).toHaveValue('13.082700')
  await expect(page.getByLabel('Longitude', { exact: true })).toHaveValue('80.270700')

  // Explicit coordinate search works without any geocoding provider or external requests.
  await page.getByText('Find a location', { exact: true }).click()
  await page.getByLabel('Search location', { exact: true }).fill('12.975432, 77.612345')
  await page.getByLabel('Search location', { exact: true }).press('Enter')
  await page.getByRole('button', { name: 'Use Coordinates: 12.975432, 77.612345' }).click()
  await expect(page.getByLabel('Latitude', { exact: true })).toHaveValue('12.975432')
  await expect(marker).toHaveCount(1)

  await page.getByLabel('Latitude', { exact: true }).fill('91')
  await page.getByRole('button', { name: 'Submit Complaint', exact: true }).click()
  await expect(page.locator('#latitude-error')).toBeVisible()
  await expect(marker).toHaveCount(0)
  await page.getByLabel('Latitude', { exact: true }).fill('12.975432')

  const nav = page.getByRole('navigation', { name: 'Citizen navigation' })
  await nav.getByRole('link', { name: 'My Complaints', exact: true }).click()
  await nav.getByRole('link', { name: 'Report an Issue', exact: true }).click()
  await expect(page.getByLabel('Latitude', { exact: true })).toHaveValue('12.975432')
  await expect(page.getByLabel('Longitude', { exact: true })).toHaveValue('77.612345')
  await page.getByRole('button', { name: /Preview locally/ }).click()
  const preview = page.getByRole('dialog', { name: 'Local report preview — not submitted' })
  await expect(preview).toContainText('12.975432, 77.612345')
  await page.keyboard.press('Escape')

  const responsePromise = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/complaints') && response.request().method() === 'POST',
  )
  await page.getByRole('button', { name: 'Submit Complaint', exact: true }).click()
  const response = await responsePromise
  expect(response.status()).toBe(201)
  const saved = await response.json()
  expect(saved.latitude).toBe(12.975432)
  expect(saved.longitude).toBe(77.612345)
  const persisted = spawnSync(
    resolve('../backend/.venv/Scripts/python.exe'),
    [
      '-c',
      'import sqlite3,sys,json; from pathlib import Path; c=sqlite3.connect(Path(sys.argv[1]).resolve().as_uri()+"?mode=ro",uri=True); print(json.dumps(c.execute("SELECT latitude,longitude FROM complaints WHERE complaint_id=?",(sys.argv[2],)).fetchone())); c.close()',
      process.env.CIVICLENS_BROWSER_DB_PATH!,
      saved.complaintId,
    ],
    { encoding: 'utf8', windowsHide: true },
  )
  expect(persisted.status, persisted.stderr).toBe(0)
  expect(JSON.parse(persisted.stdout)).toEqual([saved.latitude, saved.longitude])
  await page.getByRole('link', { name: 'View complaint details' }).click()
  await expect(page.getByText('12.97543, 77.61235', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByText('12.97543, 77.61235', { exact: true })).toBeVisible()
  await nav.getByRole('link', { name: 'Nearby Issues', exact: true }).click()
  await page.getByRole('button', { name: 'Search near my latest complaint' }).click()
  await expect(page.getByRole('heading', { name: saved.title })).toBeVisible()
  await expect(page.getByText('My Report · Not Publicly Visible', { exact: true })).toBeVisible()
  const ownMarker = page
    .locator('.category-map-marker')
    .filter({ has: page.locator('svg') })
    .and(page.locator(`[title="${saved.title}"]`))
  await expect(ownMarker).toHaveCount(1)
  await expect(page.locator('.search-center-marker')).toHaveCount(1)
  const nearby = await page.request.get('/api/citizen/issues/nearby', {
    params: {
      latitude: String(saved.latitude),
      longitude: String(saved.longitude),
      radiusKm: '10',
    },
  })
  expect(nearby.status()).toBe(200)
  const ownNearby = (await nearby.json()).items
  expect(
    ownNearby.filter((item: { issueId: string }) => item.issueId === saved.complaintId),
  ).toHaveLength(1)
  expect(
    ownNearby.find((item: { issueId: string }) => item.issueId === saved.complaintId),
  ).toMatchObject({
    issueId: saved.complaintId,
    latitude: saved.latitude,
    longitude: saved.longitude,
    isOwn: true,
    isPublic: false,
    distanceMeters: 0,
  })
  await ownMarker.click()
  await expect(page.locator('.leaflet-popup')).toContainText(saved.title)
  await expect(
    page.locator('.leaflet-popup').getByRole('link', { name: 'View complaint details' }),
  ).toHaveAttribute('href', '/citizen/complaints/' + saved.complaintId)
  await expect(page.locator('.nearby-result-focused')).toContainText(saved.title)
  for (const width of [375, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
      .toBe(true)
    await expect(ownMarker).toBeVisible()
    await expect
      .poll(async () => {
        const mapBox = await map.boundingBox(),
          point = await ownMarker.boundingBox()
        return Boolean(
          mapBox &&
          point &&
          point.x >= mapBox.x &&
          point.y >= mapBox.y &&
          point.x + point.width <= mapBox.x + mapBox.width &&
          point.y + point.height <= mapBox.y + mapBox.height,
        )
      })
      .toBe(true)
    await expect
      .poll(async () => {
        const popup = await page.locator('.leaflet-popup').boundingBox()
        const mapBox = await map.boundingBox(),
          zoom = await page.locator('.leaflet-control-zoom').boundingBox()
        return Boolean(
          popup &&
          mapBox &&
          zoom &&
          popup.x >= mapBox.x &&
          popup.y >= mapBox.y &&
          popup.x + popup.width <= mapBox.x + mapBox.width &&
          popup.y + popup.height <= mapBox.y + mapBox.height &&
          (popup.x >= zoom.x + zoom.width ||
            popup.y >= zoom.y + zoom.height ||
            popup.x + popup.width <= zoom.x),
        )
      })
      .toBe(true)
    if (width === 375 || width === 1440)
      await page.screenshot({
        path: testInfo.outputPath(`nearby-private-${width}.png`),
        fullPage: true,
        animations: 'disabled',
      })
  }
  await page.getByRole('button', { name: '200 km', exact: true }).click()
  await expect(page.getByRole('slider')).toHaveValue('200')
  await expect(page.getByText(/visible reports loaded within 200 km/)).toBeVisible()
  await page.getByLabel('Map category').selectOption('GARBAGE')
  await expect(
    page.getByRole('heading', { name: 'No visible issues were found within the selected radius.' }),
  ).toBeVisible()
  await expect(page.locator('.category-map-marker')).toHaveCount(0)
  await page.getByRole('button', { name: 'Clear Filters' }).click()
  await expect(ownMarker).toHaveCount(1)
  const previousCenter = await page.getByLabel('Map latitude').inputValue()
  await page.locator('.civic-location-map').click({ position: { x: 250, y: 150 } })
  await expect(page.getByLabel('Map latitude')).not.toHaveValue(previousCenter)
  await expect(page.getByRole('slider')).toHaveValue('200')
  const result = await page.request.get(
    '/api/public/issues/nearby?latitude=12.975432&longitude=77.612345&radiusMeters=1000',
  )
  expect(result.status()).toBe(200)
  expect(JSON.stringify(await result.json())).not.toContain(saved.complaintId)
  expect(JSON.stringify(await result.json())).not.toContain(saved.title)
  await page.getByLabel('Map latitude').fill('90')
  await page.getByLabel('Map longitude').fill('180')
  await page.getByRole('button', { name: 'Set map center' }).click()
  await expect(page.getByText(/Polar search: this map projection/)).toBeVisible()
  await expect(page.locator('.leaflet-overlay-pane path')).toHaveCount(0)
  await expect(
    page.getByRole('heading', { name: 'No visible issues were found within the selected radius.' }),
  ).toBeVisible()
  expect(errors).toEqual([])
})

test('one opt-in real OSM viewport renders actual image tiles in the browser', async ({
  page,
}, testInfo) => {
  test.skip(
    process.env.CIVICLENS_LIVE_MAP_CHECK !== '1',
    'Explicit live network check only; default regression suite does not burden OSM.',
  )
  test.setTimeout(60000)
  await citizen(page)
  await page.setViewportSize({ width: 1024, height: 900 })
  const responses: { status: number; url: string }[] = []
  page.on('response', (response) => {
    if (response.url().startsWith('https://tile.openstreetmap.org/'))
      responses.push({ status: response.status(), url: response.url() })
  })
  await page.goto('/citizen/report')
  const map = page.locator('.civic-location-map')
  await map.scrollIntoViewIfNeeded()
  const tile = page.locator('.leaflet-tile-loaded').first()
  await expect(tile).toBeVisible({ timeout: 20000 })
  expect(await tile.evaluate((el) => (el as HTMLImageElement).naturalWidth)).toBe(256)
  await expect
    .poll(
      () =>
        page
          .locator('.leaflet-tile')
          .evaluateAll(
            (tiles) =>
              tiles.length > 0 &&
              tiles.every(
                (tile) =>
                  (tile as HTMLImageElement).complete &&
                  (tile as HTMLImageElement).naturalWidth === 256,
              ),
          ),
      { timeout: 20000 },
    )
    .toBe(true)
  expect(responses.some((response) => response.status === 200)).toBe(true)
  await expect(page.locator('.leaflet-control-attribution')).toContainText('OpenStreetMap')
  const issues = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze()
  expect(issues.violations.map((issue) => issue.id)).toEqual([])
  await map.click({ position: { x: 300, y: 200 } })
  await expect(page.locator('.location-selection-marker')).toHaveCount(1)
  await map.screenshot({
    path: testInfo.outputPath('real-osm-selection.png'),
    animations: 'disabled',
  })
  await page.screenshot({
    path: testInfo.outputPath('real-osm-map.png'),
    fullPage: true,
    animations: 'disabled',
  })
  await testInfo.attach('real-tile-responses', {
    body: JSON.stringify(responses),
    contentType: 'application/json',
  })
})
