/** Exact role-protected Phase12 routes. FastAPI independently enforces account eligibility. */
export const INTELLIGENCE_ROUTES = [
  ['GET', '/api/officer/incidents/{incidentId}/repair-attempts'],
  ['POST', '/api/officer/incidents/{incidentId}/repair-attempts'],
  ['GET', '/api/admin/incidents/{incidentId}/repair-attempts'],
  ['GET', '/api/incidents/{incidentId}/repair-attempts/{attemptId}/evidence/{imageId}'],
  ['GET', '/api/citizen/verification-requests'],
  ['GET', '/api/citizen/verification-history'],
  ['GET', '/api/citizen/verification-requests/{requestId}'],
  ['POST', '/api/citizen/verification-requests/{requestId}/respond'],
  ['GET', '/api/admin/repairs/pending'],
  ['GET', '/api/admin/repairs/{attemptId}'],
  ...['approve', 'reject', 'request-rework', 'reopen', 'request-information', 'approve-evidence'].map(action => ['POST', `/api/admin/repairs/{attemptId}/${action}`] as const),
  ['POST', '/api/admin/incidents/{incidentId}/check-recurrence'],
  ['GET', '/api/admin/recurrences'],
  ['GET', '/api/admin/recurrences/{recurrenceId}'],
  ...['confirm', 'dismiss', 'request-review'].map(action => ['POST', `/api/admin/recurrences/{recurrenceId}/${action}`] as const),
  ['GET', '/api/admin/analytics/fairness'],
  ['GET', '/api/admin/analytics/fairness/areas'],
  ['GET', '/api/admin/analytics/fairness/compare'],
  ['GET', '/api/admin/analytics/fairness/reviews'],
  ['POST', '/api/admin/analytics/fairness/reviews'],
  ['PATCH', '/api/admin/analytics/fairness/reviews/{reviewId}'],
] as const

export const INTELLIGENCE_EVENTS = ['RepairSubmitted', 'RepairVerificationRequested',
  'RepairVerificationResponded', 'RepairVerificationDisputed', 'RepairApproved', 'RepairRejected',
  'RepairReworkRequested', 'RepairInformationRequested', 'IncidentVerifiedResolved', 'IncidentReopened',
  'PotentialRecurrenceDetected', 'RecurrenceConfirmed', 'RecurrenceDismissed', 'FairnessReviewFlagged'] as const
