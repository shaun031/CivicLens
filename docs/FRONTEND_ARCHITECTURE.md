# Citizen frontend and private administration — Phases 3–11

## Current Phase11 analytics

Protected `/admin/command-center`, `/admin/analytics/{view}`, `/admin/hotspots` and `/admin/reports`
reuse existing Chart.js, React-Leaflet, authRequest and loading/error/card primitives. Shared URL
filters and typed services keep report/incident measures distinct. Data freshness includes explicit
zone/UTC window/revision; requests reload on principal changes and do not retain another user's data.
Accessible table alternatives, keyboard-scrollable regions and bounded grid layers accompany charts.
Leaflet loads no external basemap by default. Authenticated POST CSV uses the same local/Cognito
credential handling; no AWS credentials are embedded. Existing management and citizen routes remain.

## Phase10 current frontend

NotificationsPage uses authenticated notificationService APIs in normal mode; explicit CitizenContext
samples remain isolated. NotificationBell refreshes conservatively on navigation and read actions.
All roles can navigate /notifications; citizen workspace also retains /citizen/notifications.
WorkflowsPage (/admin/workflows and /admin/workflows/:workflowId) combines stored summaries,
execution/stage detail, status filtering/pagination, safe DLQ inspection, confirmation-gated retry,
SLA escalation acknowledgement and versioned policy editing. Replay retains its operation UUID on
transport retry; there is no arbitrary payload editor. Existing ProtectedRoute and backend ADMIN
checks both apply. Loading/empty/error/unknown-cloud-count states are explicit. No WebSocket or timer.
See [notifications](NOTIFICATION_SYSTEM.md), [orchestration](WORKFLOW_ORCHESTRATION.md).

Phase9 WorkPages/workService add ADMIN departments/details/routing/membership/workload/rebalancing,
assignment queues/details/recommendations/reassignment/history, and OFFICER dashboard/details/progress.
Existing AuthProvider/ProtectedRoute/authRequest, Card/Select/Modal, useResource and evidence gallery
are reused. Server queues/filter/cursors replace citywide React loading. Typed recommendation and
confirmed assignment DTOs are separate. Mutation dialogs validate reason/confirmation and freeze exact
request IDs/inputs on retry;409 requires refresh. Invalid queue payloads become an error state, not a
render crash or fabricated empty data. Private officer photos use authenticated blob loading.
Mobile375/desktop1440 browser checks include axe/overflow; existing citizen routes are unchanged.

Phase8 adds typed priorityService, ADMIN PrioritiesPage and PriorityPanel/PriorityEditor/accessible
contribution bars in existing incident details. Server-side filters/ranking/cursors; no frontend
citywide sorting or fabricated operational success. Dialogs require current versions/reason/evidence/
confirmation and preserve exact failed request IDs for retry. Stale scores are labelled, unknown
inputs distinct from zero, hazard/override separate from raw formula. Citizen summary adds explanation
only. Real browser flow tests375/1440px, keyboard/modal/accessibility, persistence and private-note denial.

Phase7 adds typed incidentService, ADMIN IncidentsPage/IncidentDetailsPage and incident correction/map/
candidate/citizen-summary components. Route-keyed details reset selection/history state on navigation.
Dialogs retain exact failed operation requests for durable retry, invalidate edited target snapshots,
and require reasons/confirmation plus physical-issue confirmation for merge/link. Private image loading
reuses authenticated galleries; Leaflet is lazy and loads no external tiles. Owner summary fetches only
the narrow safe endpoint. [Incident UI guide](INCIDENT_CLUSTERING.md).

## Current Phase 6 administrator matching review

duplicateService uses the existing authenticated cookie/bearer transport. Protected ADMIN routes
/admin/duplicate-candidates and /admin/duplicate-candidates/:candidateId provide filters/search,
score/date sorting, pagination, bounded source recheck, side-by-side private text/coordinates/scoped
photos, numeric components/effective weights, missing-image and incomplete-work warnings, method/
model/config versions, review metadata and dismiss/review/rerun/back actions. No merge/priority UI.
Stale async responses are ignored; comparison actions require the currently displayed candidate ID.
Existing authenticated blob gallery handles photo cleanup/unavailable states. No dependency changes.

The earlier viewport popup fix retained approved markers during auto-pan refresh. The current
radius-based citizen page supersedes that workaround: zoom/pan does not issue discovery requests,
while changed radius/center/filters clear stale markers until fresh authorized results arrive.
The useResource helper's optional retain mode remains available to other consumers. Popup/card
focus uses stable marker keys; cluster popup actions cannot bubble into a center-selection click.

## Current Phase 5 integration

MyComplaints reads URL filters, debounces q by 300ms, requests full-history server filtering/sorting and resets cursor context on changes. Stale loader results are ignored; pagination retains context and deduplicates records. Cards show severity and authorized thumbnails. Dashboard adds Assigned, actual category/status/trend charts, period selection and refresh. Chart.js is lazy-loaded with accessible descriptions/tables and non-canvas/failure fallbacks.

discoveryService centralizes validated public queries plus the separately authenticated citizen
nearby/latest-location contract. NearbyIssues uses a 1–200km radius (default 10km, slider debounce
350ms), explicit center, category/status and bounded pages. Map and cards share approved public
summaries plus only that citizen's eligible owner-private reports, with correct visibility labels.
No full complaint/evidence is serialized into discovery DTOs. Seven category SVG icons, a hollow
teal center, circle, collapsible legend and bounded grid clustering are shared presentation code.
Selection/circle are projection-limited with a polar warning, while the backend search retains
actual coordinates. Geolocation is opt-in; report/nearby OSM tiles load by default with disclosure
and hide/retry/manual/list fallbacks. PublicIssuePage still reads only safe public details.
PublicationControls and the narrow ADMIN reviewed-publication workflow remain unchanged.
See [the full nearby contract](GEOGRAPHIC_DISCOVERY.md).

AuthProvider, cookie/bearer transport, CSRF, private blobs, URL cleanup, UI, drafts and optional samples remain. No sample fallback occurs after API failure. Historical notes below are superseded for search, analytics and discovery.

## Phase 4 integration (supersedes the fixture-only historical boundaries below)

Normal Report/My Complaints/Details/Dashboard screens now use the real authenticated complaint API. `complaintService` adapts backend camelCase/flat coordinates into existing presentation types, validates basic response shape, supports cursor pages, exact detail, multipart create and aggregate summary. Sample mode stays opt-in and never receives writes or substitutes for a failed API. Creation has a per-draft request UUID, a synchronous in-flight lock, disabled controls, failure-state retention and success ID/details navigation. Editing creates a new request intent; retry without editing reuses its key.

List filters/sorting explicitly affect loaded pages only; Load more uses a validated opaque backend cursor and Refresh restarts the listing. Dashboard counts use `/complaints/summary`, never a partial list length. New real timelines contain only Submitted and pending future stages. Private evidence is fetched as an authenticated Blob through the existing cookie/bearer client; object URLs are revoked. Sources and paths are not exposed publicly. Native dialogs, accessible feedback, mobile navigation and the Phase 2 AuthProvider remain shared. Complaint requests avoid redundant StrictMode startup effects by checking activity before dispatch.

Canonical categories are BROKEN_STREETLIGHT/PUBLIC_PROPERTY_DAMAGE rather than the Phase 3 fixture shorthand. Form limits are 10–150-character titles, 20–2,000-character descriptions, optional 200-character address/landmark and two 1.5-MiB photos; server validation remains authoritative. Details are in COMPLAINT_SYSTEM.md, EVIDENCE_STORAGE.md and API.md.

The remainder documents the original Phase 3 component organization/history; fixture-only service/form statements describe that earlier checkpoint, not the current operational API.

## Structure and ownership

`frontend/src/App.tsx` owns React Router routes. A single existing AuthProvider restores Phase 2 sessions. Public routes use AppLayout; citizen routes use ProtectedRoute with the existing CITIZEN/ADMIN matrix and DashboardLayout. The layout calls the real `/api/portal/citizen` endpoint before rendering page content, handles loading/errors/retry, and never replaces backend authorization. Officer/admin dashboards and `/profile` are preserved. `/citizen` redirects to `/citizen/dashboard`; unknown routes still use the public 404.

DashboardLayout contains the desktop Sidebar, native-dialog mobile navigation, role/name top bar, account menu and real logout. Citizen workspace state is keyed by authenticated user ID. Switching identities, logout, leaving this layout, or reload discards drafts, selected Files, sample mode, notification read state, and selected map coordinates. No duplicate authentication context, credentials, browser complaint storage, database writes, or new backend endpoints were added.

## Components

- `components/common`: existing Button, Field, PasswordField, FormMessage, LoadingState and ErrorState; new Card, Badge, Alert, Select, Textarea, InlineError, Skeleton, EmptyState, PageHeader and Breadcrumbs in UI.tsx; native Modal/ConfirmDialog with focus containment, Escape dismissal and focus restoration; ErrorBoundary for unexpected render/map errors.
- `components/complaints`: typed ComplaintCard, StatusBadge, ComplaintFilters, ComplaintCategorySelector, ComplaintTimeline, ComplaintImageGallery, ImageUpload, and lazy ComplaintMap.
- `components/dashboard`: StatCard, QuickActionCard and RecentActivity.
- `components/notifications`: NotificationItem with explicit simulated read actions.
- `pages`: public HomePage, CitizenDashboard, ReportIssuePage, MyComplaintsPage, ComplaintDetailsPage, NearbyIssuesPage, NotificationsPage; existing profile/auth/status/role pages remain operational.
- `hooks`: useResource tracks loader identity to prevent stale fixture exposure when mode changes and ignores late results after navigation; useGeolocation runs only on explicit action and handles unsupported/denied/unavailable/timeout states.
- `utils`: centralized date formatting, validation and complaint filtering/sorting.

## Data boundaries

Complaint/IssueLocation/ProgressEvent/ComplaintDraft types use Phase 1 `complaintId`, `citizenId`, optional `incidentId`, UTC ISO timestamps, `imageKeys`, and coordinates. Uppercase status values SUBMITTED, UNDER_REVIEW, ASSIGNED, IN_PROGRESS, RESOLVED and REJECTED are centralized presentation contracts; Phase 1 did not impose a conflicting status enum. Notification types cover received/status/assignment/resolution/information/announcement.

`services/complaintService.ts` defines list/detail/nearby/create boundaries. Normal personal views return empty data because no complaint API exists. Explicit sample mode returns independent copies of typed fixtures with `isSimulated: true`, `sample-*` identifiers and `fictional-demo-citizen`, never the real user's ID. Unknown IDs return null, never an arbitrary example. `create()` always rejects as unavailable; the preview form does not call it. `notificationService.ts` similarly returns only explicit fixture copies or empty account data. These are local asynchronous data interfaces, not fake HTTP responses or simulated network success.

For Phase 4, add an authenticated HTTP implementation behind the same interfaces, validate server response schemas, enforce server ownership/role checks and retain fixture selection separately. Do not silently switch to fixtures on network failure. Shared request logic remains `auth/authClient.ts` for identity/profile/protected APIs and `services/api.ts` for health. Vite proxies `/api`; no production host or AWS credential is embedded.

## Form and evidence preview

The form supports category, 5–120-character title, 20–2,000-character description, 3–200-character landmark, finite latitude/longitude in geographic bounds and user-reported severity. Validation uses trimmed minimum lengths, inline errors, described inputs and focus on the first invalid field. Latitude/longitude fields are the keyboard alternative to map clicking. Selected photos are optional: maximum three non-empty JPEG/PNG/WebP files, each at most 5 MiB. MIME/size checks are client convenience checks only, not a future upload security boundary. Object URLs are revoked on replacement/removal/unmount, including StrictMode cleanup. No S3/upload request, complaint ID or false success is generated. Draft fields and File references remain in workspace memory across citizen routes. Local preview and destructive clear use real dialogs.

## Maps and privacy

React Leaflet is dynamically imported only for report/nearby screens. Presentation receives markers, selection and callbacks through props; no fixtures are embedded in the map. Basic filtering is not geospatial querying or clustering. Default coordinates illustrate Bengaluru, not the citizen's current position. Geolocation is requested only by clicking Use My Location, never stored, and not needed for manual/map selection.

External tiles are off until Load OpenStreetMap basemap is clicked. The explanatory notice discloses IP/viewed-area sharing. The exact HTTPS standard tile URL, visible copyright attribution and default browser Referer/caching are retained. No proxy, restrictive page Referrer-Policy, offline download, cache bypass, prefetch or automated tile scraping is implemented. Automated browser tests intercept/abort all OSM requests. On failure the coordinate grid, markers, manual fields and issue list remain usable. Consult the [OSM tile policy](https://operations.osmfoundation.org/policies/tiles/) before any public usage; no availability guarantee is made. Map source URL/attribution are isolated in ComplaintMap for a future reviewed provider change.

## Testing

Vitest/Testing Library cover deterministic fixtures, form/files, search/filter/sort, empty/errors/retry, notifications, geolocation, profiles and authorization/session regression. Heavy map behavior is mocked in citizen component tests. Playwright exercises the real Leaflet DOM, marker/filter/popups, blocked-tile fallback, geolocation denial, native-dialog focus/Escape, automated WCAG checks and overflow at 375/768/1024/1440px. A separate browser scenario uses a real isolated FastAPI/SQLite service for registration, protected-return login, refresh, profile persistence, forbidden admin access and cookie logout. No AWS account or Docker is needed.
