# Nearby Issues and category markers — implementation report

Implemented 2026-10-21; final validation 2026-10-22 (Asia/Calcutta).
Existing project: `D:\CivicLens`. No AWS deployment.

## Outcome and root cause

Nearby Issues previously used approved-public discovery only. A newly submitted PRIVATE report
therefore stayed invisible even to its reporter. A preset search location and the old 5km radius
cap further obscured location/radius mismatches. The fix adds a separately authorized citizen
overlay while preserving the anonymous approved-public-only endpoints and private evidence access.

Owners see eligible unpublished reports labeled **My Report · Not Publicly Visible**. Other
citizens see only reviewed approved summaries and approximate public coordinates. An owned
published report appears once, using its actual saved owner coordinates. Public metadata never
substitutes for private complaint access, and caller-supplied owner IDs are rejected.

## Backend changes

Source/configuration files:

- `backend/app/api/routes/discovery.py`: authenticated nearby and latest-location endpoints.
- `backend/app/models/discovery.py`: citizen query/DTO, 200km limits, separate internal envelope.
- `backend/app/utils/geography.py`: shared Haversine retained; pole/date-line envelope and parent cells.
- `backend/app/core/config.py`, `backend/.env.example`: 200000m maximum and guarded future cloud mode.
- `backend/app/repositories/auth_store.py`: shared Haversine SQLite function and two additive indexes.
- `backend/app/integrations/database/sqlite_nearby.py` (new): indexed owner/public union, exact SQL
  distance, context-bound keyset pagination and minimal response hydration.
- `backend/app/integrations/database/sqlite_discovery.py`: radius delegation and owner latest location.
- `backend/app/integrations/database/dynamodb_nearby.py` (new): bounded parent GSI lookup and strong
  projection/source revalidation, owner scoping, safe payloads, no Scan and complete-bootstrap guard.
- `backend/app/integrations/database/dynamodb_complaints.py`: atomic minimal owner-region projection.
- `backend/app/integrations/database/dynamodb_discovery.py`: publication-region projection/tombstone,
  new radius delegation and bounded owner latest-location lookup.
- `backend/app/scripts/benchmark_phase5.py`: disposable 200km owner-overlay timing and both radius
  index query plans in the existing full-verification benchmark stage.
- `infrastructure/lib/constructs/api-gateway.ts`, `infrastructure/lib/safety.ts`: two JWT GET routes,
  no new anonymous route, table, GSI, permission expansion or deployment operation.
- `infrastructure/lib/constructs/backend-lambda.ts`: matching 200000m environment maximum and an
  explicitly disabled regional-bootstrap flag, checked in `infrastructure/test/lambda.test.ts`.

Updated documentation: this report, `GEOGRAPHIC_DISCOVERY.md`, `API.md`,
`PUBLICATION_AND_PRIVACY.md`, `DEVELOPMENT.md`, `FRONTEND_ARCHITECTURE.md`,
`ROLES_AND_PERMISSIONS.md`, `UI_DESIGN.md`, root `README.md` and `PHASE_PROGRESS.md`.

Backend tests: new `test_nearby_visibility.py` and `test_nearby_cloud.py`; updated
`test_discovery.py`, `test_discovery_cloud.py`, `test_complaint_adapters.py`. Infrastructure
`test/api.test.ts` and `test/discovery.test.ts` check 133 routes and JWT protection.

## Frontend changes

- `frontend/src/pages/NearbyIssuesPage.tsx`: 1..200km slider (10km default), seven presets, explicit
  center/GPS/latest location, synchronized real map/cards, category/status filters, clear/refresh,
  stale-result protection, pagination, owner labels and specific empty/error states.
- `frontend/src/services/discoveryService.ts`, `frontend/src/types/nearby.ts` (new): central API
  contract/validation and authorized detail routes.
- `frontend/src/auth/CitizenContext.ts`, `frontend/src/components/layout/DashboardLayout.tsx`:
  account-scoped in-memory search center/radius.
- `frontend/src/pages/ReportIssuePage.tsx`: successful saved coordinates retained for nearby search
  and “View on Nearby Issues” action; original multipart submission contract unchanged.
- `frontend/src/components/complaints/ComplaintMap.tsx`: shared category markers, teal crosshair,
  search circle, legend and existing OSM/resize/error fallback integration.
- New `frontend/src/components/maps/categoryConfig.ts`, `markerIcons.ts`, `CategoryLegend.tsx`,
  `clustering.ts`, `NearbyLayer.tsx`: seven local SVG category symbols/colors, fallback, authorized
  popups, 64-pixel visualization-only clusters and card/marker focus.
- `frontend/src/components/maps/MapSupport.tsx`: center-preserving Leaflet resize invalidation so
  markers do not remain outside a narrower mobile map's clipping area.
- `frontend/src/styles/index.css`: responsive legend, marker/cluster/radius/card styling.

Frontend tests: updated `src/test/Discovery.test.tsx`; new `src/test/NearbyMarkers.test.tsx`;
updated `e2e/discovery.spec.ts`, `e2e/location.spec.ts`, `e2e/citizen.spec.ts`; new
`e2e/production-markers.spec.ts` exercises compiled assets with explicit synthetic UI fixtures.
The real backend submission/privacy journeys remain separate real-API/SQLite browser checks.
The existing guarded `tests/integration/provision_browser_admin.py` additionally supports an
optional trusted fixture session for the extra independent viewer context. It refuses normal
database paths; no HTTP backdoor, increased production quota or rate-counter reset was added.
Dedicated real HTTP registration/login/rate-limit tests remain intact. This avoids unrelated
browser journeys sharing the extra viewer's 15-minute public authentication quota.

## Radius, query and count policy

The citizen API accepts `radiusKm=1..200`, converting exactly once to metres. SQLite uses indexed
bounding-box candidate selection followed by the single existing Haversine calculation in SQL,
not global Python filtering. Date-line/pole envelopes are supported; exact distance determines
inclusion. Page size <=100, stable distance/ID order, context-scoped cursor and <=101 hydrated SQL
rows. Tests include 2201 isolated reports and prove both radius indexes are used. The interface
loads pages explicitly, caps rendered reports at 500 and asks users to refine if more remain.

Markers retain each report's authorized coordinates. A cluster counts **individual visible
reports, not unique incidents**, and never merges records or modifies master incidents. Category
symbols/colors are orange pothole, red construction, yellow bulb, green trash, blue drainage,
purple building and grey other. Search center is a separate teal crosshair. Cluster click zooms;
coincident reports can be selected individually without falsifying their coordinates.

## API additions

```text
GET /api/citizen/issues/nearby?latitude=12.97&longitude=77.59&radiusKm=200&limit=50
GET /api/citizen/issues/latest-location
```

Both require active verified CITIZEN authorization. Existing public radius discovery retains its
`radiusMeters` parameter (now up to 200000); public viewport limits and safe DTO fields are
unchanged. See [the full contract and privacy rules](GEOGRAPHIC_DISCOVERY.md).

## Verification

The clean full verification rerun passed **28/28 stages, exit 0**, with no skipped coverage or
browser category: `build/verification/20261021-235312-c46b2092/summary.json`.

| Test group | Actual result |
|---|---|
| Backend unit/security/migration/concurrency | 690 passed |
| Process-restart integrations | 6 passed |
| Frontend units/interactions | 226 passed |
| Offline infrastructure assertions | 59 passed |
| Default real browser journeys | 18 passed; 1 explicitly opt-in network case skipped |
| Separate opt-in live OSM case | 1 passed |
| Types, lint, build, evaluations, benchmarks, API contract and source manifest | PASS |

This is **1000 distinct tests**, not a sum of repeated targeted runs. The API contract matches
133 operations/routes; the full source manifest contains 476 source/config/documentation files.

Post-run visual review caught a mobile resize issue that DOM visibility alone did not detect.
The final frontend-only refinement changes shared resize invalidation to preserve center, bounds
popup dimensions/scrolling and reserves space beside zoom controls. Browser assertions now check
the marker and popup rectangles inside the visible map and verify no overlap with zoom controls
at 375/768/1024/1440px. Targeted checks and the complete frontend-only rerun passed under
`build/nearby-fix/final-frontend/`: lint, app/browser TypeScript, all 226 units/interactions,
production build and all 18 browser journeys (the opt-in live case is intentionally skipped in
standard runs). The final bounded-popup production build/probe and actual screenshot review
also passed. Backend/infrastructure code is unchanged since the full 28-stage run.

The final source inventory is `build/nearby-fix/final-source-manifest.json`. Standard browser
screenshots are under `frontend/test-results/`, with the strengthened real submission/private
nearby evidence in `location-real-map-selectio-0bc51-izing-and-SQLite-submission-regression/`
and compiled-asset evidence in `production-markers-compile-6760d-us-circle-and-mobile-legend-regression/`.
Grey basemaps in regression screenshots are expected: external tiles are deliberately blocked.
The separate live OSM screenshots show actual decoded imagery. Final 375px views were visually
inspected to confirm the issue icon and readable popup stay inside the map, clear of zoom buttons.

Final read-only inspection of the normal developer database found its two complaints and schema
version 8 intact. The new indexes are additive; no database hash-equality claim is made because
index initialization changes database metadata. All owned fixture/preview listeners are closed.

The earlier run at `build/verification/20261021-232525-d7358d71/` stopped at the infrastructure
resource-count gate after passing its earlier stages: adding two routes required exact expected
route/integration counts of 133 and Lambda permissions of 134, not 131/132. Those counts were
corrected without removing JWT, unexpected-resource or deployment-block checks. Failure evidence
is retained; a passing stage is not inferred from the earlier failure.

The 5000-record disposable benchmark (3000 owner records, 500 approved projections) measured
**14.92ms median / 16.84ms maximum** across five warmed 200km owner-overlay queries returning
50 reports. EXPLAIN uses `complaints_owner_radius` and `publications_radius`. Backend coverage is
**76.43% statements / 63.98% branches**, not a claim of complete coverage. Numeric frontend
coverage remains unverified.

Focused checks already completed:

- 69 focused SQLite/discovery/cloud adapter tests passed, including real HTTP submission.
- 5 new offline regional DynamoDB tests passed; SDK transport is mocked, not deployed.
- Updated initial frontend suite: 211 passed before the final additional cases.
- Additional discovery/marker unit run: 42 passed.
- Real approval/public/owner/de-duplication/cluster/withdrawal browser journey passed.
- Real map/drag/GPS/submission/read-only SQLite/owner-private nearby browser journey passed at
  375/768/1024/1440px, including 200km, filtering and safe polar projection handling.
- Frontend app/browser TypeScript checks, ESLint, Ruff and production build passed in focused runs.
- Compiled-production marker probe passed all seven colors/icons, popups/links, circle/crosshair,
  collapsible legend, all four widths, accessibility and no overflow. Explicit synthetic UI fixture;
  not substituted for the real backend privacy/submission browser journeys.
- One opt-in live OSM browser case passed (actual decoded 256px tiles and complete requested grid),
  saved under `build/nearby-fix/live-osm/`. Standard regression runs block external tiles.
- Corrected infrastructure rerun: all 59 tests, offline synthesis, exact template/JWT/IAM safety
  and zero-cloud local-stage checks passed. No AWS transport or deployment was used.

Real browser checks found and fixed map lifecycle issues before acceptance: detached-circle
`getBounds()` use and an orphan popup caused by moving focused markers between nested React child
arrays. Circle bounds now use the attached rendered layer; stable keyed marker siblings preserve
the active popup. Cluster popup actions stop clicks during capture, so unmounting a popup cannot
accidentally choose a different nearby-search center. The center remains unchanged when selecting
an individual co-located report. Failing browser runs were rerun, not suppressed.

The first complete browser preflight passed 17 journeys but exhausted the unchanged real public
registration quota in the priority journey after adding an extra citizen. The additional viewer
now uses the existing strictly guarded fixture service and a separate browser context/session,
without logging the owner out. This restores independent test setup without weakening production
limits, deleting counters or removing real registration/login coverage. The subsequent clean run
passed that priority journey and all nearby/privacy/compiled-marker checks, as recorded above.

## Remaining limitations and safety

- OSM tiles depend on network/provider availability. Existing loading/error/retry, manual coordinate
  and list fallbacks remain. GPS is explicitly requested, permission-dependent and not a field
  accuracy guarantee. Place-name geocoding remains unconfigured.
- Public coordinates are intentionally approximate; no original reporter coordinates are revealed
  to other citizens. Foreign dates are publication dates, not falsely labeled submission dates.
- Web Mercator cannot faithfully display poles. At |latitude|>=85 the viewport is clamped, not
  the stored coordinates or backend search; a warning replaces the unrepresentable circle.
  The server handles polar/date-line radii.
- Search center/radius are memory-only, not a persistent location history. A full reload asks for
  a center again; latest-complaint centering is available. Category filtering remains single-select
  to preserve the existing API's enum contract.
- SQLite radius work scales with indexed bounding-box candidates; 5000-row warmed timings are
  demonstration measurements, not production/cloud load guarantees.
- DynamoDB regional discovery deliberately requires `CLOUD_DISCOVERY_REGIONS_READY=true` only after
  a separately verified complete projection bootstrap/backfill. No bootstrap was run or certified.
  New GSI entries can be delayed; dense searches can hit the bounded candidate budget and return
  422. Strong reads prevent stale private disclosure, not indexing delay. Cloud bindings/Linux
  packaging/hosting readiness remain blocked, and real AWS behavior is not claimed tested.
- Numeric frontend coverage remains unverified. Passing local tests cannot guarantee no future bug.
- Existing dependency/tool warnings remain visible: Starlette's HTTPX test-client deprecation,
  CDK's 450/500 resource-headroom notice and unconfigured feature-flag notice. They were not
  suppressed or presented as evidence of cloud deployment readiness.
- No complaints, accounts, photographs or normal database were deleted/reset. Tests use disposable
  databases and isolated browser ports. Index changes are additive metadata, not a data migration
  that replaces reports. No dependency/lockfile changes or new paid map service.

## Run locally

From `D:\CivicLens`, in separate PowerShell terminals:

```powershell
.\scripts\run-backend.ps1
```

```powershell
.\scripts\run-frontend.ps1
```

Frontend: `http://localhost:5173`. API health: `http://127.0.0.1:8000/api/health`. Restart the API if
an existing non-reloading process is still serving the old routes/settings. Additive indexes
initialize automatically; no database reset is needed. Full checks: `.\scripts\verify.ps1`.
