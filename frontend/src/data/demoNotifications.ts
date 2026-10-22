import { notificationTypes, type CitizenNotification } from '../types/notification'

export const demoNotifications: CitizenNotification[] = (
  [
    'RECEIVED',
    'STATUS_UPDATED',
    'ASSIGNED',
    'RESOLVED',
    'INFORMATION',
    'ANNOUNCEMENT',
  ] as (keyof typeof notificationTypes)[]
).map((type, index) => ({
  notificationId: `sample-notification-${index + 1}`,
  type,
  title: notificationTypes[type],
  message:
    'Sample notification only. No real complaint, department, or account activity is associated with this message.',
  read: index > 3,
  createdAt: `2026-10-${String(10 + index).padStart(2, '0')}T09:00:00.000Z`,
  targetUrl: type === 'ANNOUNCEMENT' ? '/' : `/citizen/complaints/sample-${index + 1}`,
  isSimulated: true,
}))
