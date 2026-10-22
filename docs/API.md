# Operational API — Phases 2–13

## Current Nearby Issues follow-up

Active verified CITIZEN-only `GET /api/citizen/issues/nearby` accepts required finite latitude/
longitude, integer `radiusKm` 1–200 (default 10), category/status, limit 1–100 and a query/owner-bound
cursor. It combines the caller's eligible reports (including PRIVATE) with only approved public
summaries from other citizens, de-duplicating owned published reports. Unknown identity parameters
are rejected; no private reporter, description, evidence or incident fields are exposed.
`GET /api/citizen/issues/latest-location` returns only that caller's latest eligible saved point or
null. Both new gateway routes require JWT, bringing the cloud route contract to 133 operations.
The existing public nearby endpoint retains `radiusMeters` (now 50–200000); public DTOs/bounds
and publication approval remain unchanged. [Full contract](GEOGRAPHIC_DISCOVERY.md).

Phase13: unsafe ordinary `/api/` bodies are limited to64KiB by default before parsing;
the three evidence submission routes retain the separate3.25MiB cap. Invalid length400,
oversize413; allowed-origin CORS/error responses retain API no-store/security/request-ID
headers. Notification filters now include REPAIR_VERIFICATION_UPDATE and OFFICER_REPAIR_UPDATE.
The expanded131 cloud route methods/paths match real OpenAPI; this is not generated
frontend schema equivalence. [Contract/security results](PHASE13_READINESS_REPORT.md).

## Phase12 civic intelligence

All paths below have `/api` prefix, role authorization, active/verified checks and no-store responses.
Unsafe local requests require allowed Origin and rate limits. UUID paths, bounded paging (`after`
UUID, limit1–50), strict request fields and optimistic versions apply. API errors never echo photos,
passwords or private paths.28 new exact CDK JWT routes are separately catalogued.

- OFFICER GET/POST `/officer/incidents/{id}/repair-attempts`; ADMIN GET
  `/admin/incidents/{id}/repair-attempts`.
- Authenticated GET `/incidents/{id}/repair-attempts/{attempt}/evidence/{image}`: rechecked role,
  current assignment/membership and specific evidence approval; JPEG bytes, private/no-store.
- CITIZEN GET `/citizen/verification-requests`, `/{request}`, `/citizen/verification-history`;
  POST `/citizen/verification-requests/{request}/respond`.
- ADMIN GET `/admin/repairs/pending` (optional state filter), `/admin/repairs/{attempt}`;
  POST `/{attempt}/approve`, `/reject`, `/request-rework`, `/request-information`, `/approve-evidence`,
  `/reopen`. Reasons, explicit confirmation, expectedVersion and expectedIncidentVersion required.
  Evidence approval uses approvedEvidenceIds; does not resolve the incident.
- ADMIN GET `/admin/recurrences` (state/category/start/end/incident/after/limit), `/{recurrence}`;
  POST `/{recurrence}/confirm`, `/dismiss`, `/request-review`; POST
  `/admin/incidents/{id}/check-recurrence`. Decisions require reason/version/confirmation and
  confirmation additionally requires physicalIdentityConfirmed.
- ADMIN GET `/admin/analytics/fairness`, `/areas`, `/compare?first=grid:...&second=grid:...` with
  existing P11 filters; GET/POST `/admin/analytics/fairness/reviews`; PATCH `/reviews/{review}`.
  Review bodies carry operationId, expectedVersion, areaId, context, notes, state.
- Existing report catalog/preview/audited CSV routes add geographic-service-comparison, sla-disparity,
  unresolved-backlog-distribution, recurring-infrastructure-failures, repair-verification-outcomes.

Repair and response POSTs accept JSON (no photos) or multipart with exactly one JSON `payload` and
up to two `images`. Submission: operationId, expectedIncidentVersion, expectedAssignmentVersion,
description20–2000, notes≤2000, timezone-aware repairedAt. Response: operationId, expectedVersion,
result CONFIRMED_FIXED/STILL_BROKEN/UNSURE, feedback≤2000. One effective response, no silent edits.
409 means refresh/review; exact operation retries replay the committed result.503 denotes unavailable
storage or the intentionally unactivated cloud domain binding, never fabricated success.

## Phase11 analytics (current; earlier inventories below are historical)

Every route requires an active verified ADMIN, independently of frontend routing and gateway JWT.
GET `/api/admin/analytics/{view}` supports overview, complaint-trends, incidents, priorities,
departments, officers, sla, backlog, hotspots and response-times. The gateway allowlist has ten
exact paths; FastAPI validates the view literal. Typed envelope: calculatedAt, scope,
reportingTimezone, UTC window, normalized filters, dataFreshness and metric limitations.

Query fields: start/end inclusive reporting dates; category; department UUID; priority band or
UNAVAILABLE; status OPEN/RESOLVED; assignment; urgent boolean; named area; south/west/north/east;
grouping daily/weekly/monthly; grid0.001–0.1; availability; minWorkload/maxWorkload; limit1–50 and
scope/filter/source-revision-bound cursor. Unknown fields fail422. Range1–366days within1970–2100;
hotspots require a bounded non-wrapping viewport (<=2degrees/axis,10000 potential/2000 occupied cells).
Selected incident detail pages reset on filter/source changes. No partial source cohort is a total.

GET `/api/admin/analytics/reports` returns report types, limits and reporting/service-area/department
configuration. GET `/reports/{kind}` returns bounded preview with metadata/definitions/columns/rows;
POST `/reports/{kind}/csv` returns audited allowlisted CSV. Type is citywide/categories/priorities/
departments/officers/sla/backlog/hotspots. Maximum2000aggregate rows/1MiB; department/officer details
are explicit pages, not silent full exports. Local-cookie POST requires trusted Origin and10/min/user.
Responses are no-store, failures meaningful (400cursor,409revision,413source/output bound,
422invalid filters,503unavailable projection/storage). No arbitrary SQL/PII/image/location dump.
See [definitions](MUNICIPAL_ANALYTICS.md), [reporting](ADMIN_REPORTING.md) and
[data model](ANALYTICS_DATA_MODEL.md).13 new gateway routes,103 total exact HTTP routes.

## Phase10 additions (current; older sections below are historical)

All15 new routes require an active verified account, no-store responses and server authorization.
Notification ownership is the signed-in principal, including ADMIN; no recipient ID grants access.
Unsafe local-cookie actions require exact trusted Origin. Operational controls require ADMIN,
reason10–1000 characters, confirmed=true and operationId UUID; controls use durable replay receipts.

- GET /api/notifications — limit1–50, cursor, type, read=true/false; items/nextCursor.
- GET /api/notifications/unread-count — unreadCount.
- PATCH /api/notifications/{notificationId}/read; POST /api/notifications/mark-all-read.
- GET /api/admin/workflows — status, workflowType=IncidentTriageWorkflow, limit/cursor.
- GET /api/admin/workflows/summary — actual local state counts/duration; cloud sample explicitly labelled.
- GET /api/admin/workflows/{workflowId} — safe execution/stage history.
- GET /api/admin/workflows/dead-letters — paginated safe metadata, never an editable envelope.
- POST /api/admin/workflows/{workflowId}/retry.
- POST /api/admin/workflows/dead-letters/{messageId}/redrive or /acknowledge.
- GET /api/admin/sla/policies; PUT /api/admin/sla/policies/{policyId}.
- GET /api/admin/sla/escalations; POST /api/admin/sla/escalations/{escalationId}/acknowledge.

Policy PUT additionally takes expectedVersion, priorityBand, nullable category/departmentId, urgent,
responseHours and resolutionHours. Finite positive bounds, resolution>=response and100 policies max.
404 hides another recipient's notification.409 means stale/currently ineligible work or exhausted
redrive budget; reload and inspect rather than changing UUIDs blindly.422 invalid input/confirmation.
Private monitor routes never expose raw descriptions, evidence, credentials or citizen contact data.
See [events](EVENT_DRIVEN_ARCHITECTURE.md) and [recovery](FAILURE_RECOVERY.md).

## Municipal work APIs (Phase9)

All routes below require an active verified account, no-store responses and backend role checks.
ADMIN and OFFICER are distinct; administrator portal access is not implicit field-officer permission.
Unsafe local cookie requests require a trusted Origin and have a durable60/user/minute work limit.
Cloud routes require JWT/API scope and backend role/membership validation; no real cloud calls tested.

| Role | Method | Route under /api |
|---|---|---|
| ADMIN | GET | /admin/departments; /admin/departments/summary |
| ADMIN | POST | /admin/departments; /admin/departments/seed |
| ADMIN | GET, PATCH | /admin/departments/{departmentId} |
| ADMIN | GET, POST | /admin/departments/{departmentId}/officers |
| ADMIN | DELETE | /admin/departments/{departmentId}/officers/{officerId} |
| ADMIN | GET | /admin/departments/{departmentId}/incidents; /history |
| ADMIN | GET, POST | /admin/routing-rules |
| ADMIN | GET | /admin/officers?after=UUID&limit=50 |
| ADMIN | GET | /admin/assignments; /admin/assignments/unassigned |
| ADMIN | GET | /admin/incidents/{incidentId}/assignment; /assignment-history |
| ADMIN | POST | /admin/incidents/{incidentId}/assign-department; /recommend-officer; /assign-officer; /reassign; /unassign-officer |
| OFFICER | GET | /officer/incidents; /officer/incidents/{incidentId}; /officer/incidents/{incidentId}/history |
| OFFICER | POST | /officer/incidents/{incidentId}/start; /progress |
| OFFICER | GET | /officer/incidents/{incidentId}/complaints/{complaintId}/images/{imageId} |

29 new routes. UUID path validation and strict extra-field rejection. 401 unauthenticated,403 wrong
role/Origin,404 unknown/inaccessible work,409 stale/conflicting operations,422 invalid inputs,
503 storage failure. A recommendation POST is read-only and does not allocate/audit a fabricated action.

Every mutation supplies operationId UUID, reason10..1000 and confirmed=true. Create/edit departments
also supply expectedVersion (0 on create), code uppercase pattern, name3..100, description, active,
areas[]. Membership POST adds officerId, expectedVersion, active, availability, nullable capacity and
areas. Membership DELETE body uses expectedVersion and common action fields; it deactivates, not deletes.
Rule POST adds category,departmentId,expectedVersion,precedence0..1000,active. Seed accepts common fields.

Assignment actions require expectedIncidentVersion>=1 and expectedAssignmentVersion>=0. Department
assignment without departmentId invokes routing; with departmentId confirms manual responsibility.
Officer assignment requires officerId/current confirmed department. Reassign accepts departmentId and
officerId (null clears), review boolean and capacityOverride boolean. Unassign retains department.
Optional mode MANUAL_APPROVAL/default or CONSERVATIVE_AUTO_ASSIGN; auto mode additionally requires
environment opt-in and all safety checks. Current incident/assignment versions come from detail.

Progress adds note10..2000, percentage0..100 and requestReview. START only from OFFICER_ASSIGNED;
PROGRESS only from IN_PROGRESS. No RESOLVED/repair approval action exists. Same request ID replays exact
persisted output; reusing it with different inputs409. Refresh after a stale conflict; retain the same
ID/inputs after an ambiguous timeout. Histories and department work use opaque context-bound cursors.

Work queue filters: departmentId/officerId (ADMIN only), status (assignment state), band, category,
urgent, assignedAfter (timezone-aware UTC date), limit1..50 and cursor. Canonical lifecycle is OPEN
only; resolved/retired work is excluded. Officer-supplied officerId/departmentId filters are rejected;
identity comes from authentication. Fresh hazards first, pending-priority review work next, then Phase8
effective score/unresolved time/UUID. Queue changes/expiry409 restart the first page. Citizen/public
endpoints are unchanged and expose no assignment notes, private officer histories or unrelated reports.

## Priority APIs (Phase 8)

All ten endpoints require active verified ADMIN; anonymous401, CITIZEN/OFFICER403 before private
resource access. Responses no-store. Unsafe local cookie requests require trusted Origin; cloud uses
existing verified Cognito scopes/roles. No public priority mutation/read route was added.

| Method/path under /api | Behavior |
|---|---|
| GET /admin/incidents/priorities | Ranked fresh incidents, filters, stable-ID tie-break and expiring revision-bound cursor |
| GET /admin/incidents/priorities/summary | Real active/pending/scored/band/assessment/hazard/override totals locally; unavailable cloud aggregates explicitly null |
| GET /admin/incidents/{id}/priority | Canonical incident, controls/revisions, stored result, stale reasons and current evidence UUID options |
| GET /admin/incidents/{id}/priority/history | Original-ID immutable scoring/assessment/override history with before/after/factor snapshots |
| POST /admin/incidents/{id}/priority/recalculate | Confirmed versioned recalculation using current inputs |
| PATCH /admin/incidents/{id}/severity | ADMIN severity assessment with evidence/provenance |
| PATCH /admin/incidents/{id}/public-impact | ADMIN impact assessment, unknown distinct from zero |
| PATCH /admin/incidents/{id}/hazard-review | Set/clear verified urgent flag, independently audited |
| POST /admin/incidents/{id}/priority/override | Create effective-score override, preserve raw score |
| DELETE /admin/incidents/{id}/priority/override | Audited removal, latest formula/hazard restored |

All writes require `{operationId,expectedIncidentVersion,expectedPriorityRevision,reason,confirmed}`.
Assessment adds `{score,status,evidenceReferences}`; UNASSESSED requires null, PROVISIONAL<=6,
VERIFIED0–10 with at least one current member report/photo UUID. Hazard adds `{flag,evidenceReferences}`
(true requires evidence); override adds `{score}`0–100 and optional future timezone-aware `expiresAt`.
Extras/nonfinite/range/foreign evidence/control-character reasons rejected422. Conflict409; transaction
envelope413; missing404; temporarily unavailable503; durable mutation rate limits429 (local30/min/admin;
prepared cloud reuses separate conservative submission-limit buckets). Same-ID identical retries replay
the exact receipt; changed bodies/operation kinds conflict. After409, refresh and confirm a new request.

Both ranking modes keep verified urgent hazards first. Ranking filters:
q,band,category,status(OPEN/RESOLVED),urgent,assessmentStatus,overrideStatus,
min/maxSeverity, min/maxImpact, min/maxDays, sort(priority/oldest), limit<=50, cursor. Band refers to
effective operational priority. Revisions or aging/expiry invalidate cursors; restart page1. SQL pages
expire within60s or the earliest due score. Cloud GSI propagation remains eventual and filters may
produce empty pages with continuation. Stale/unscored records remain in master management, not current
rankings. History uses chronological keyset pages<=50 and stays accessible on retired original IDs.

Citizen `/complaints/{id}/incident` remains unchanged: own ID/category/status/processing only; no band,
private factor data, counts, notes or override rationale. See [scoring guide](PRIORITY_SCORING.md).

## Incident APIs (Phase 7)

Active verified ADMIN only, no-store, trusted Origin checked on local cookie POSTs:

| Method/path under /api | Behavior |
|---|---|
| GET /admin/incidents | q/category/status/sort/limit/cursor; bounded catalog |
| GET /admin/incidents/summary | Stored analytics; cloud pending-review count explicitly unavailable |
| GET /admin/incidents/{id} | Current canonical metadata, requested ID and alias chain |
| GET /admin/incidents/{id}/complaints | Bounded private members, eligibility/distance, protected image URLs |
| GET /admin/incidents/{id}/history | Original-ID immutable paginated before/after/change history |
| GET /admin/incidents/{id}/recommendations | Stored bounded suggestions/processing/mode, NOT actual membership |
| GET /admin/incidents/{id}/complaints/{complaintId}/images/{imageId} | Current membership + image ownership checked |
| POST /admin/incidents/merge | Whole source into target, atomic retirement/alias |
| POST /admin/incidents/{targetId}/link-complaint | Move one current source member to target |
| POST /admin/incidents/{sourceId}/split | New incident from selected proper subset |
| POST /admin/incidents/{sourceId}/unlink-complaint | Split exactly one report into singleton |
| POST /admin/incidents/{sourceId}/recheck | Audited, versioned fresh matching/clustering work |

POST bodies require `{operationId,sourceIncidentId,expectedSourceVersion,reason,confirmed}`.
Merge/link additionally `{targetIncidentId,expectedTargetVersion,physicalIssueConfirmed}`; link needs
`complaintId`, split/unlink `complaintIds`. Optional `matchingCandidateId` captures pair evidence but
does not authorize membership. UUID IDs, extra fields, reason length, confirmation, category/span,
subset/version checks enforced. Conflict409; invalid422; atomic envelope413; unavailable503.
Identical retry replays the durable result; do not generate a fresh operation ID merely after timeout.

GET `/api/complaints/{complaintId}/incident`: active verified CITIZEN owner-only;404 for another owner.
Only `{incidentId,category,status,processing}` or pending null ID. No counts, other members/identities,
private canonical narrative or alias chain. OFFICER/anonymous cannot read global incident data.
Existing publication-based public URLs are not replaced with private incident identifiers.
[Rules/commands](INCIDENT_CLUSTERING.md), [data model](INCIDENT_DATA_MODEL.md).

## Duplicate review APIs (Phase 6)

All new routes require active verified ADMIN: local session or existing Cognito role verification.
CITIZEN/OFFICER receive403; anonymous401, before resource lookup. Unsafe local POSTs require exact
trusted Origin. Responses/evidence are no-store. Existing citizen/public contracts are unchanged.

| Endpoint | Response/behavior |
|---|---|
| GET /api/admin/duplicate-candidates | `{items,nextCursor}` ranked persistent candidates |
| GET /api/admin/duplicate-candidates/{candidateId} | Candidate + two private comparisons/processing states |
| GET /api/admin/complaints/{complaintId}/duplicate-candidates | Same paginated list restricted to either pair side + processing |
| POST /api/admin/duplicate-candidates/{candidateId}/dismiss | DISMISSED, latest reviewer/time retained |
| POST /api/admin/duplicate-candidates/{candidateId}/reviewed | REVIEWED_POSSIBLE_DUPLICATE; never merges |
| POST /api/admin/complaints/{complaintId}/duplicate-check | Bounded source recheck; `{processing}` state/report |
| GET /api/admin/duplicate-candidates/{candidateId}/complaints/{complaintId}/images/{imageId} | JPEG only after pair membership/image validation |

List query: classification, reviewStatus, category, q (title substring max150), minScore/maxScore
(0–1, ordered), sort=score/date, limit=1–100 (default20), context-bound cursor. Changing filters,
sort or limit invalidates old cursors (400). Score sorting uses descending combined score, distance,
UUID (text-evidence strength breaks score ties before distance); date uses last-checked descending/UUID.
Offset pages can shift under concurrent writes.

Candidate fields: candidateId, canonical sourceComplaintId/possibleDuplicateId, distanceMeters,
geographicScore/textScore/imageScore (null if unavailable), combinedScore/effectiveWeights,
categoryCompatibility/classification/reviewStatus, method/modelVersion/configVersion,
explanation/indicators, createdAt/updatedAt/lastCheckedAt/reviewedAt. Detail complaint DTOs contain
ID/title/description/category/coordinates/status/time/incidentId and scoped image URLs, never
reporter identity/storageKey. An 86/100 similarity index is NOT an 86% probability.

Processing state is PENDING/RUNNING/RETRY/COMPLETE/INCOMPLETE, with attempts/error class, versions,
retrieved/compared/queryTruncated/timeBudgetExceeded/incomplete and stage timings in its report.
Old candidates remain after partial/failed work; inspect timestamps and recheck explicitly.
Unknown authorized resources404, invalid parameters422, unavailable storage503 and query quota429.
Empty/truncated responses do not establish non-duplication. No citizen-facing duplicate check exists.

Cloud listing uses bounded MatchingWork Query/strong reads, never Scan. Catalog overflow (default
2,000) returns503 rather than a misleading complete result. GSI propagation remains eventual.
See DUPLICATE_DETECTION.md for detailed safety/operational limitations.

Phase 5 adds full-history owner search/analytics and separate administrator-approved public discovery. Phase 6 adds private duplicate review above. Local operation uses SQLite/private storage; AWS adapters are mocked/offline only. Status transitions, incident priority scoring, clustering, department workflows and real notifications remain deferred.

## Publication and geographic APIs (Phase 5)

| Endpoint | Authorization | Operation |
|---|---|---|
| PATCH /api/complaints/{complaintId}/publication-request | Active verified CITIZEN owner | JSON requested=true/false; request review or immediately withdraw public consent |
| PATCH /api/admin/complaints/{complaintId}/publication | Active verified ADMIN | APPROVE, REJECT or UNPUBLISH; atomic audited change |
| GET /api/public/issues | Anonymous permitted | Required bounded minLatitude/maxLatitude/minLongitude/maxLongitude; optional category/status/limit/cursor |
| GET /api/public/issues/nearby | Anonymous permitted | Required latitude/longitude, radiusMeters 50–200000, optional category/status/limit/cursor |
| GET /api/public/issues/{publicIssueId} | Anonymous permitted | Current approved projection or indistinguishable unpublished/unknown 404 |

Local PATCH calls require the existing exact trusted Origin. Approval requires publicSummary (15–300), publicLatitude/publicLongitude and reviewedForPrivacy=true; it cannot approve a non-pending or withdrawn citizen request. Summary text is separately reviewed; coordinates round to three decimals. Public JSON contains only publicIssueId/category/status/summary/latitude/longitude/publishedAt and optional distanceMeters. It never includes the private complaint UUID, citizen identity, original notes or evidence.

Public pages have items and nextCursor when another page exists (the cursor may be omitted when finished). Limits are 1–100/default 50. Bounds span at most 0.25 degrees each side; date-line crossing is supported. Dense candidate sets or oversized regions return 422, not partial success. Default persistent public quota is 120/minute per connection identity; 429 includes Retry-After. All public responses are no-store. Full contracts: COMPLAINT_SEARCH.md, DASHBOARD_ANALYTICS.md, GEOGRAPHIC_DISCOVERY.md and PUBLICATION_AND_PRIVACY.md.

## Complaint endpoints (Phase 4)

Every endpoint below requires an active, verified **CITIZEN**, not merely any logged-in account. Local mode uses the existing HttpOnly session cookie. AWS mode requires the existing verified Cognito access token/API scope; backend role/ownership checks remain independent of API Gateway JWT authentication. Officers/admins have no complaint-wide or evidence access in this phase.

### POST /api/complaints

Use `multipart/form-data` with a required UUID `Idempotency-Key` header. Local state-changing calls also need an exact trusted Origin (`http://localhost:5173` by default). The browser generates the multipart boundary; do not set a bare Content-Type manually.

| Field | Validation |
|---|---|
| title | Trimmed 10–150 characters |
| description | Trimmed 20–2,000 characters; configurable maximum may be lower |
| category | POTHOLE, DAMAGED_ROAD, BROKEN_STREETLIGHT, GARBAGE, DRAINAGE, PUBLIC_PROPERTY_DAMAGE, OTHER |
| reportedSeverity | LOW, MEDIUM, HIGH; not a computed priority |
| latitude / longitude | Finite numbers within −90…90 / −180…180 |
| landmark / addressLabel | Optional, at most 200 characters each |
| images | Optional repeated binary field, at most 2 JPEG/PNG/WebP files, each nonempty and ≤1,572,864 bytes |

Unexpected/repeated fields, including citizenId, status and incidentId, are rejected. The actual streamed request is bounded at 3,407,872 bytes before multipart parsing. Images must decode correctly, match declared MIME, be single-frame, have ≤4,000,000 pixels and ≤4096px per dimension. Evidence is oriented, metadata-stripped, downscaled where necessary to ≤2048px and re-encoded as JPEG.

HTTP 201 is returned only after accepted evidence and metadata have been saved. A same-user/same-key/same-content replay returns that same persisted complaint with HTTP 201; changed content with the same key returns 409. Keep the same key and payload for a retry after a connection error. Idempotency does not detect independently submitted similar reports.

Example (identifiers/times here illustrate the schema, not real submitted reports):

```json
{
  "complaintId": "5832a51b-66c8-4a26-b2f2-d1f7fc63f162",
  "citizenId": "0b120964-2672-4901-9655-63f70991232a",
  "title": "Large pothole near the library",
  "description": "A large pothole creates a hazard for cyclists near the entrance.",
  "category": "POTHOLE",
  "reportedSeverity": "HIGH",
  "latitude": 12.9716,
  "longitude": 77.5946,
  "landmark": "Library gate",
  "addressLabel": "Library Road",
  "status": "SUBMITTED",
  "incidentId": null,
  "createdAt": "2026-10-19T12:00:00.000Z",
  "updatedAt": "2026-10-19T12:00:00.000Z",
  "images": []
}
```

Image entries contain `imageId`, `contentType`, `fileSize` (sanitized bytes), `createdAt` and a relative API path `url`, e.g. `/complaints/{id}/images/{imageId}`. Prepend the configured API base `/api`. Internal storage keys and filesystem paths are never returned.

### GET /api/complaints?limit=20&cursor=...

Returns `{"items": [/* complete private complaint records */], "nextCursor": null, "total": 0}`. Supports q, category, status, reportedSeverity, dateFrom/dateTo (inclusive UTC dates), sortBy=createdAt/category/status, sortOrder=asc/desc, limit=1–100 (default 20) and cursor. Text uses normalized AND token-prefix search across title/description/landmark/address. All predicates apply before counting/pagination. Default newest-first and all sorts include timestamp/UUID ties. Cursors bind owner/provider/filter/sort context; changed context or malformed tokens return 400. No citizenId override is accepted. The frontend uses real server filtering across complete owner history, not only loaded pages.

### GET /api/complaints/summary

Preserves total/counts/recent, adding byCategory, submissionTrend, trendDays and empty recentActivity. Optional days=7–90/default 30 selects UTC daily submission counts; total/status/category counts cover all owner records. Recent contains at most three real complaints. Empty accounts return zero totals and empty collections. No historic status transitions are invented.

### GET /api/complaints/{complaintId}

Returns the complete private persisted complaint, including owner-visible publication metadata. Nonexistent and foreign-owner UUIDs both return 404 `{"detail":"Complaint not found."}`. Malformed UUIDs return 422. Separate public UUIDs/details expose only reviewed fields; administrator publication review does not grant general private detail/photo access.

### GET /api/complaints/{complaintId}/images/{imageId}

Checks the citizen role, complaint ownership and image membership before reading bytes. Success is `image/jpeg`, `Cache-Control: private, no-store`, `X-Content-Type-Options: nosniff` and a generated safe inline filename. Cookie sessions or bearer credentials are required: the frontend fetches an authenticated Blob, displays a temporary object URL and revokes it on unmount. No public static directory or direct S3 URL is exposed. Missing stored bytes produce a safe 503/unavailable-image state, not a filesystem path.

### Errors, rate limits and diagnostics

Errors use `{"detail": "safe message"}` or a safe field-validation array. Status codes: 400 malformed multipart/cursor; 401 unauthenticated; 403 role/verification/Origin denied; 404 unavailable private resource; 409 request-key conflict; 413 request/image/pixel size; 415 media/format mismatch; 422 field/corrupt image validation; 429 quota exceeded (`Retry-After`); 503 database/storage unavailable or ambiguous cloud commit. Unexpected errors return a generic 500 without traceback pages.

Default submission quota is 10 per citizen per 900 seconds. SQLite enforces this transactionally in the shared database; the DynamoDB adapter uses atomic conditional counters, not process memory. Existing successful idempotent replays bypass the quota. See COMPLAINT_SYSTEM.md for accounting differences and crash recovery. Complaint responses include a generated `X-Request-ID`; safe logs contain operation/status/duration and complaint identifiers where available, never photos, tokens, descriptions, coordinates or private paths.

Base URL (local): `http://127.0.0.1:8000`

Interactive OpenAPI documentation:

- Swagger UI: `GET /docs`
- ReDoc: `GET /redoc`
- OpenAPI JSON: `GET /openapi.json`

## Health

`GET /api/health`

No authentication is required. A successful response is HTTP 200:

```json
{
  "status": "ok",
  "service": "civiclens-api",
  "environment": "local"
}
```

The environment comes from validated backend settings: `local` for native development, `test` for tests, and `aws` for the future Cognito-backed Lambda. CDK keeps demo/production in a separate DEPLOYMENT_STAGE setting; legacy demo/production APP_ENV aliases also require Cognito. The frontend uses this endpoint to report connectivity. The HTTP API defines the same public route through Mangum payload v2; it is not deployed.

## Authentication and profile routes

Local unsafe requests require `Origin: http://localhost:5173` (or another exact configured origin). Browsers send this automatically. Include cookies on local requests. AWS protected requests use `Authorization: Bearer <access-token>`; local-password routes are not registered in AWS mode.

| Method and path | Access | Request / result |
|---|---|---|
| POST /api/auth/register | Public, local only, trusted Origin | display_name, email, password, confirm_password → 201 safe CITIZEN profile |
| POST /api/auth/login | Public, local only, trusted Origin | email, password → 200 profile and HttpOnly cookie |
| POST /api/auth/logout | Local only, trusted Origin | No body → 204; session invalidated and cookie cleared |
| GET /api/auth/me | Authenticated | 200 safe current profile |
| PATCH /api/profile | Authenticated; trusted Origin for local | display_name only → 200 updated profile |
| POST /api/auth/forgot-password | Public, local only, trusted Origin | email → generic 202; private outbox if eligible, no email sent |
| POST /api/auth/reset-password | Public, local only, trusted Origin | token, password, confirm_password → 200; single-use token consumed and sessions revoked |
| GET /api/portal/citizen | CITIZEN or ADMIN | 200 safe portal confirmation |
| GET /api/portal/officer | OFFICER or ADMIN | 200 safe portal confirmation |
| GET /api/portal/admin | ADMIN | 200 safe portal confirmation |

Registration example (use your own password; no role field is accepted):

```json
{"display_name":"Example Citizen","email":"citizen@example.com","password":"<12–128 character password>","confirm_password":"<same password>"}
```

Safe profile response fields: id, email, display_name, role, provider, is_authenticated, is_active, is_verified. Password hashes, raw passwords, session IDs, and recovery tokens are never in these responses. Portal confirmation contains portal, message, and effective role; there is no complaint data.

Error status: 400 invalid/expired reset; 401 missing/invalid/expired authentication or generic invalid login; 403 CSRF origin rejection, insufficient role, or pending Cognito group provisioning; 404 local-password routes in AWS mode; 409 duplicate registration; 422 malformed/forbidden fields; 429 rate limit with Retry-After; 503 identity/profile service unavailable. Validation errors omit sensitive inputs.

Roles, IDs, is_active, is_verified, and other extra fields are forbidden in public registration/profile input. See [ROLES_AND_PERMISSIONS.md](ROLES_AND_PERMISSIONS.md). Complaint creation/retrieval is operational as documented above; incident management and status-changing workflows do not exist yet.

