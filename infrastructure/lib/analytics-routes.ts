/** Exact analytics routes; FastAPI independently enforces verified ADMIN authorization. */
export const ANALYTICS_ROUTES = [
  ['GET', '/api/admin/analytics/overview'],
  ['GET', '/api/admin/analytics/complaint-trends'],
  ['GET', '/api/admin/analytics/incidents'],
  ['GET', '/api/admin/analytics/priorities'],
  ['GET', '/api/admin/analytics/departments'],
  ['GET', '/api/admin/analytics/officers'],
  ['GET', '/api/admin/analytics/sla'],
  ['GET', '/api/admin/analytics/backlog'],
  ['GET', '/api/admin/analytics/hotspots'],
  ['GET', '/api/admin/analytics/response-times'],
  ['GET', '/api/admin/analytics/reports'],
  ['GET', '/api/admin/analytics/reports/{kind}'],
  ['POST', '/api/admin/analytics/reports/{kind}/csv'],
] as const
