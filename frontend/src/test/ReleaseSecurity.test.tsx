import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { NotificationItem } from '../components/notifications/NotificationItem'
import { liveNotificationTypes } from '../types/notification'

describe('Phase13 security contracts', () => {
  it('renders untrusted notification text literally instead of executing HTML', () => {
    const title = '<img src=x onerror=alert(1)> synthetic report'
    const message = '<script>window.secret = document.cookie</script>'
    const { container } = render(
      <MemoryRouter>
        <NotificationItem
          notification={{
            notificationId: 'synthetic-id',
            title,
            message,
            type: 'REPAIR_VERIFICATION_UPDATE',
            read: false,
            createdAt: '2026-10-21T00:00:00Z',
            targetUrl: '/citizen/verification',
            isSimulated: false,
          }}
          onRead={vi.fn()}
        />
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { name: title })).toBeVisible()
    expect(screen.getByText(message)).toBeVisible()
    expect(container.querySelector('img, script')).toBeNull()
    expect(screen.getByRole('link')).toHaveAttribute('href', '/citizen/verification')
  })

  it('offers both repair notification types supported by the backend filter', () => {
    expect(liveNotificationTypes.REPAIR_VERIFICATION_UPDATE).toBe('Repair verification update')
    expect(liveNotificationTypes.OFFICER_REPAIR_UPDATE).toBe('Officer repair update')
  })
})
