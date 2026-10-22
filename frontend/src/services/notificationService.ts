import { demoNotifications } from '../data/demoNotifications'
import type { CitizenNotification } from '../types/notification'
import { authRequest } from '../auth/authClient'
export interface NotificationPage {
  items: CitizenNotification[]
  nextCursor: string | null
}
export interface NotificationService {
  list(demo: boolean): Promise<CitizenNotification[]>
  page(filters?: { type?: string; read?: string; cursor?: string }): Promise<NotificationPage>
  unread(): Promise<{ unreadCount: number }>
  read(id: string): Promise<{ unreadCount: number }>
  readAll(): Promise<{ unreadCount: number }>
}
export const notificationService: NotificationService = {
  async list(demo) {
    return demo ? structuredClone(demoNotifications) : (await this.page()).items
  },
  async page(filters = {}) {
    const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => value !== ''))
    const page = await authRequest<NotificationPage>(`/notifications?${query}`)
    if (!Array.isArray(page.items))
      throw new Error('Invalid notification response. Refresh to retry.')
    return page
  },
  unread: () => authRequest('/notifications/unread-count'),
  read: (id) => authRequest(`/notifications/${id}/read`, 'PATCH'),
  readAll: () => authRequest('/notifications/mark-all-read', 'POST'),
}
