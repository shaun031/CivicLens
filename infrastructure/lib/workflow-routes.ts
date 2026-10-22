/** Exact JWT-protected routes; shared by synthesis and the resource safety allowlist. */
export const WORKFLOW_ROUTES = [
  ['GET', '/api/notifications'], ['GET', '/api/notifications/unread-count'],
  ['PATCH', '/api/notifications/{notificationId}/read'], ['POST', '/api/notifications/mark-all-read'],
  ['GET', '/api/admin/workflows'], ['GET', '/api/admin/workflows/summary'],
  ['GET', '/api/admin/workflows/dead-letters'], ['GET', '/api/admin/workflows/{workflowId}'],
  ['POST', '/api/admin/workflows/{workflowId}/retry'],
  ['POST', '/api/admin/workflows/dead-letters/{messageId}/redrive'],
  ['POST', '/api/admin/workflows/dead-letters/{messageId}/acknowledge'],
  ['GET', '/api/admin/sla/policies'], ['PUT', '/api/admin/sla/policies/{policyId}'],
  ['GET', '/api/admin/sla/escalations'], ['POST', '/api/admin/sla/escalations/{escalationId}/acknowledge'],
] as const
