# Administrative reports and protected CSV

ADMIN `/admin/reports` supports citywide summary, categories, priorities, departments, officers,
SLA/escalation, active backlog and geographic-cell reports. Preview and CSV use the same validated
server-side filters/calculations as the dashboard. No raw SQL or arbitrary table/column export exists.

GET `/api/admin/analytics/reports` lists report types and configuration. GET `/reports/{kind}` previews
an allowlisted report; POST `/reports/{kind}/csv` generates an authenticated file and audit record.
Unsafe local-cookie export requires trusted Origin and a durable10/minute/user limiter. Citizen and
officer access is denied on every route. Private responses use no-store; cloud JWT/RBAC remains active.

CSV uses explicit columns, RFC-compatible quoting, UTF-8 BOM and CRLF. Leading formula markers after
whitespace/control characters are prefixed with an apostrophe. No credentials, citizen contacts,
report descriptions, evidence keys/content or exact private report coordinates are exported.
Officer IDs/display names are narrowly permitted internal workload columns, not public citizen data.
Exports are audited with actor, type, normalized filters, row count and timestamp; report contents
are not logged. Audit failure prevents a false successful export.

Reports include title, generated UTC time, reporting zone, UTC window, applied filters, definitions,
freshness and sample/row count. Unavailable values remain unavailable. At most2000 aggregate rows
and1MiB are generated. Department/officer detail reports are explicitly page-scoped (1–50 rows,
default25); use nextCursor/Next report page. No truncated detail page is labelled a complete dataset.
CSV filenames contain only allowlisted type and date. The UI reports actual failure, not fake success.

Counts are current-state creation-date cohorts, not historic snapshots. Missing repair-verification
data cannot be filled by officer progress. See [metric definitions](MUNICIPAL_ANALYTICS.md).
