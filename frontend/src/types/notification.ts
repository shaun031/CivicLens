export const liveNotificationTypes = {
  COMPLAINT_RECEIVED: 'Complaint received',
  INCIDENT_STATUS_CHANGED: 'Incident status updated',
  COMPLAINT_UNDER_REVIEW: 'Report review update',
  INCIDENT_ASSIGNED: 'Department assigned',
  OFFICER_ASSIGNED: 'Officer assignment',
  WORK_STARTED: 'Work started',
  WORK_PROGRESS_UPDATED: 'Work progress',
  INCIDENT_OVERDUE: 'SLA overdue alert',
  URGENT_HAZARD_REVIEW: 'Verified hazard review',
  ADMIN_ACTION_REQUIRED: 'Administrator review',
  REPAIR_VERIFICATION_UPDATE: 'Repair verification update',
  OFFICER_REPAIR_UPDATE: 'Officer repair update',
} as const
export const notificationTypes = {
  ...liveNotificationTypes,
  RECEIVED: 'Complaint received',
  STATUS_UPDATED: 'Status updated',
  ASSIGNED: 'Department assigned',
  RESOLVED: 'Issue resolved',
  INFORMATION: 'Additional information requested',
  ANNOUNCEMENT: 'Important announcement',
} as const
export interface CitizenNotification {
  notificationId: string
  title: string
  message: string
  type: keyof typeof notificationTypes
  read: boolean
  createdAt: string
  targetUrl: string
  isSimulated: boolean
}
