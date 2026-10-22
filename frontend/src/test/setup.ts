import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup, configure } from '@testing-library/react'

afterEach(() => cleanup())
// Auth restoration + scheduled React renders can exceed DOM Testing Library's1s default
// under concurrent Windows/browser verification. Keep assertions, allow bounded CI headroom.
configure({ asyncUtilTimeout: 5000 })
Object.defineProperty(navigator, 'geolocation', { configurable: true, get: () => undefined })

// JSDOM does not implement the browser dialog focus/inert APIs. Real behavior is covered by Playwright.
HTMLDialogElement.prototype.showModal = function () {
  this.setAttribute('open', '')
}
HTMLDialogElement.prototype.close = function () {
  this.removeAttribute('open')
}
