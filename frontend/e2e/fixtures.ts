import { test as base } from '@playwright/test'

export { expect, type Page } from '@playwright/test'

// Deterministic regression checks must not repeatedly request shared public tiles.
// The separate, explicitly opted-in single viewport test exercises real OSM images.
export const test = base.extend<{ mapNetworkGuard: void }>({
  mapNetworkGuard: [
    async ({ page }, use, info) => {
      const live =
        process.env.CIVICLENS_LIVE_MAP_CHECK === '1' && info.title.startsWith('one opt-in real OSM')
      if (!live) await page.route('https://tile.openstreetmap.org/**', (route) => route.abort())
      await use()
    },
    { auto: true },
  ],
})
