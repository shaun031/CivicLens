import { expect, test } from './fixtures.js'
import { preview } from 'vite'
import { resolve } from 'node:path'
import AxeBuilder from '@axe-core/playwright'

// Compiled asset probe only. Real submission/authorization is exercised separately
// by location.spec.ts and discovery.spec.ts against their disposable SQLite API.
test('compiled production category markers, crosshair, radius circle and mobile legend', async ({
  page,
}, info) => {
  const server = await preview({
    configFile: false,
    root: resolve('.'),
    preview: { host: '127.0.0.1', port: 0, strictPort: true },
  })
  try {
    const address = server.httpServer.address()
    if (!address || typeof address === 'string')
      throw new Error('Preview did not bind a local port')
    const colors = {
      POTHOLE: '#ea580c',
      DAMAGED_ROAD: '#dc2626',
      BROKEN_STREETLIGHT: '#facc15',
      GARBAGE: '#16a34a',
      DRAINAGE: '#2563eb',
      PUBLIC_PROPERTY_DAMAGE: '#9333ea',
      OTHER: '#64748b',
    }
    const items = Object.keys(colors).map((category, index) => ({
      issueId: `compiled-${index}`,
      title: `Compiled fixture ${category}`,
      category,
      status: 'SUBMITTED',
      latitude: 12.972 + index * 0.008,
      longitude: 77.595 + index * 0.004,
      distanceMeters: index * 1000,
      createdAt: '2026-10-21T10:00:00.000Z',
      dateLabel: 'Reported',
      isOwn: true,
      isPublic: false,
      detailsUrl: `/citizen/complaints/compiled-${index}`,
    }))
    await page.route('**/api/**', (route) => {
      const url = new URL(route.request().url())
      const json = url.pathname.endsWith('/auth/me')
        ? {
            id: 'compiled-citizen',
            email: 'compiled@example.invalid',
            display_name: 'Compiled Asset Test',
            role: 'CITIZEN',
            provider: 'local',
            is_active: true,
            is_verified: true,
            is_authenticated: true,
          }
        : url.pathname.endsWith('/latest-location')
          ? { location: { latitude: 12.972, longitude: 77.595 } }
          : url.pathname.endsWith('/issues/nearby')
            ? {
                items: items.filter(
                  (item) =>
                    !url.searchParams.get('category') ||
                    item.category === url.searchParams.get('category'),
                ),
                nextCursor: null,
              }
            : url.pathname.endsWith('/notifications')
              ? { items: [], nextCursor: null, unreadCount: 0 }
              : { message: 'Isolated compiled UI fixture' }
      return route.fulfill({ json })
    })
    const errors: string[] = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.goto(`http://127.0.0.1:${address.port}/citizen/nearby`)
    await page.getByRole('button', { name: 'Search near my latest complaint' }).click()
    for (const [category, color] of Object.entries(colors)) {
      await page.getByLabel('Map category').selectOption(category)
      const marker = page.locator('.category-map-marker')
      await expect(marker).toHaveCount(1)
      await expect(marker).toHaveAttribute('title', `Compiled fixture ${category}`)
      await expect(marker.locator('svg path')).not.toHaveCount(0)
      const expected = `rgb(${[1, 3, 5].map((start) => parseInt(color.slice(start, start + 2), 16)).join(', ')})`
      expect(
        await marker.locator('span').evaluate((el) => getComputedStyle(el).backgroundColor),
      ).toBe(expected)
      // Filtering preserves the user's zoom; use the supported card action to
      // focus a different geographic point before clicking its marker.
      await page.getByRole('button', { name: 'Show on map' }).click()
      await marker.click()
      await expect(page.locator('.leaflet-popup')).toContainText(`Compiled fixture ${category}`)
      await expect(
        page.locator('.leaflet-popup').getByRole('link', { name: 'View complaint details' }),
      ).toHaveAttribute('href', items.find((item) => item.category === category)!.detailsUrl)
    }
    await expect(page.locator('.search-center-marker svg')).toHaveCount(1)
    await expect(page.locator('.leaflet-overlay-pane path')).toHaveCount(1)
    await page.getByRole('button', { name: '200 km', exact: true }).click()
    await expect(page.getByText(/visible reports loaded within 200 km/)).toBeVisible()
    // A report at/near the center must remain visible above the hollow crosshair.
    const issueZ = await page
      .locator('.category-map-marker')
      .evaluate((el) => Number(getComputedStyle(el).zIndex))
    const centerZ = await page
      .locator('.search-center-marker')
      .evaluate((el) => Number(getComputedStyle(el).zIndex))
    expect(issueZ).toBeGreaterThan(centerZ)
    for (const width of [375, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 900 })
      await expect
        .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
        .toBe(true)
      expect(
        (await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze())
          .violations,
      ).toEqual([])
      await page.screenshot({
        path: info.outputPath(`compiled-nearby-${width}.png`),
        fullPage: true,
        animations: 'disabled',
      })
    }
    await page.locator('.category-legend summary').click()
    await expect(page.getByRole('list', { name: 'Issue category legend' })).toBeHidden()
    expect(errors).toEqual([])
  } finally {
    await server.close()
  }
})
