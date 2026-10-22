# Project-status removal and interactive location fixes

Date: 2026-10-21 (Asia/Calcutta). Scope: existing Phase 14 frontend, not deployment.

## Removed development UI

- Deleted `frontend/src/pages/ProjectStatusPage.tsx` and its import and `/status` route.
- Removed desktop/mobile public navigation, public-footer and workspace-footer status links.
- Changed sample announcement targets from `/status` to Home.
- Removed the public footer's development/deployment banner. Kept the independent-platform disclaimer.
- Old `/status` URLs now use the existing accessible not-found page and Return home link.
- Backend `/api/health`, the internal frontend health client, diagnostics, documentation,
  `PHASE_PROGRESS.md`, AWS configuration and unrelated tests are preserved.

## Root cause and investigation

The primary cause was explicit application state, not missing Leaflet CSS or broken Vite assets:
`ComplaintMap` initialized `tiles` to **false**, so React never rendered a `TileLayer` until the
user found and clicked “Load OpenStreetMap basemap.” Leaflet still rendered zoom controls and its
own attribution over an empty gray container. The configured canonical HTTPS tile URL was valid.
The pre-existing icon system already used local HTML `divIcon`s, not default PNG marker URLs.

Two layout weaknesses compounded this: the report fieldset placed a short issue-information card
beside a much taller location card, leaving empty space below the first card; Leaflet had no
container resize observer for sidebar, card or grid width changes. Existing CSS imports and map
height utilities were present. Real-browser checks subsequently confirmed CSS positioning,
successful HTTP 200 tile requests, decoded 256px tiles, functional controls and no map JavaScript
exceptions. There was no evidence of a CSP, asset-loading, z-index or StrictMode initialization defect.

## Implemented map and location behavior

- Report/nearby basemaps load by default, with privacy disclosure and a Hide external basemap action.
- Shared `OpenStreetMapTiles` uses the canonical HTTPS OSM endpoint and visible copyright link.
  Browser cache behavior is preserved; only viewport tiles and a small normal buffer are loaded.
  `updateWhenIdle` avoids re-requesting tiles continuously during panning. No proxy, bulk download,
  prefetch, paid service, fake tiles or geolocation-at-page-load behavior was added.
- Tile requests use an origin-only cross-origin referrer policy, not private route/query strings.
- Loading, tile-error and 12-second stalled-initial-load feedback provide a visible manual-coordinate
  fallback and explicit Retry map tiles control. Selection is retained through errors/retries.
- Shared `MapResize` watches the actual container using `ResizeObserver`, schedules one animation
  frame and calls `invalidateSize({pan:false, debounceMoveend:true})`. Cleanup disconnects the
  observer and cancels pending frames. Window resize remains a fallback.
- One teal, keyboard-focusable, locally rendered selection marker supports click and drag selection,
  with auto-pan while dragging. Longitude wraps are normalized before validation. No external marker
  image or shadow URL is required in either development or production.
- “Use my current location” remains an explicit browser permission request. Permission denial,
  unavailable/unsupported location, timeout, invalid coordinates and inaccurate fixes have clear
  messages. Duplicate pending requests and callbacks after unmount are guarded. Submission waits for
  a pending geolocation request to finish so it cannot silently change a newly cleared draft.
- The selected-location summary and actual coordinate inputs use six decimal places for selected
  points. Blank or invalid coordinates produce no marker and no invented default selection.
- Bengaluru remains the documented initial map viewport, not a complaint location. Selection occurs
  only through user action. Manual valid coordinates, including zero, remain supported.

## Search adapter and limitations

Explicit coordinate search works offline: enter `latitude, longitude`, search, then choose the
result to set the marker. Place-name search has **no default provider**. An optional operator-managed
same-origin adapter can be enabled with `VITE_LOCATION_SEARCH_URL` and must return:

```json
{"results":[{"label":"Place name","latitude":12.97,"longitude":77.59}]}
```

No geocoding endpoint or paid account was invented. Missing/unavailable configuration explains the
fallback. This adapter validates results, caps them at five, times out after eight seconds, caches
up to 30 searches in memory for five minutes and limits uncached browser requests to one per second.
Queries are sent only on explicit submission, never autocomplete or page load. Enabling a real
provider requires an operator-supplied backend with **application-wide** limits, identification,
cache and licence attribution; per-browser limits alone do not meet a public provider's global limit.
The public Nominatim service is not called or configured by this implementation.

## Complaint integration and privacy

Map clicks, drags, confirmed search results and geolocation call the report page's validated
`selectLocation`, updating the existing `CitizenContext` draft's `latitude`, `longitude` and request
key. Manual edits use the same draft. Existing validation rejects non-finite latitude/longitude
outside [-90,90]/[-180,180] or missing values. Draft state survives client-side workspace navigation
and preview; it is intentionally not persistent across reload/sign-out.

The unchanged `complaintService.create` sends the actual draft coordinates under the existing
multipart `latitude`/`longitude` fields with the existing idempotency header. FastAPI, the SQLite
schema, duplicate detection, publication rules and authorization are unchanged. The detail page
continues displaying persisted coordinates. Browser verification submitted a real isolated complaint,
queried SQLite read-only and checked the returned and persisted coordinates were exactly
`12.975432, 77.612345`, then checked detail coordinates again after reload. This is a test-selected
coordinate pair, not a claimed user location. Nearby public discovery did not publish that private report.

Private administrative maps keep their existing opt-in external basemap behavior. Hotspot/fairness
maps reuse the canonical tile component and resize handling and now disclose tile errors; incident
maps reuse resize handling but still load **no external basemap**. Existing filters, approved public
markers, private incident members and accessible tables are preserved.

## Layout

The report now stacks full-width issue-information, location, evidence and review sections using
the existing shell and cards. Map height is 450px on tablet/desktop and 330px below 768px. Controls
have 44px touch targets. All sections use shrinkable grid columns; no independent scrolling region
was introduced. Existing card/panel entrance animations and reduced-motion overrides are retained;
no animation was added to the dragged marker that could fight Leaflet positioning.

## Files changed

Production frontend:

- `frontend/src/App.tsx`
- `frontend/src/components/layout/{Navbar,Footer,AppShell}.tsx`
- `frontend/src/data/demoNotifications.ts`
- `frontend/src/pages/{ReportIssuePage,NotFoundPage}.tsx`
- `frontend/src/pages/ProjectStatusPage.tsx` — deleted
- `frontend/src/components/complaints/{ComplaintMap,LocationSearch}.tsx`
- `frontend/src/components/maps/{MapSupport.tsx,mapConfig.ts}`
- `frontend/src/components/analytics/{HotspotMap,FairnessMap}.tsx`
- `frontend/src/components/incidents/IncidentMap.tsx`
- `frontend/src/hooks/useGeolocation.ts`
- `frontend/src/services/locationSearch.ts`
- `frontend/src/styles/index.css`
- `frontend/src/vite-env.d.ts`, `frontend/.env.example`

Tests and documentation:

- `frontend/src/test/{App,ComplaintIntegration,Geolocation,LocationSearch}.test.tsx`
- `frontend/e2e/location.spec.ts` and shared `frontend/e2e/fixtures.ts`
- Existing citizen, assignment, discovery, incident, duplicate, priority and redesign browser suites
  import the shared network fixture. Default regression runs abort external tile requests instead of
  repeatedly consuming OSM capacity; the separately opted-in live test requests one real viewport.
- `PHASE_PROGRESS.md`, `docs/FRONTEND_LOCATION_FIXES.md`

No backend/infrastructure source, package manifest, package lock or database schema was changed.

## Verification

Focused browser run: **3 passed**, including responsive real-API/SQLite submission and a live OSM
viewport. The live check was strengthened and rerun: **1 passed**, waiting until **all requested tile
images** were decoded at 256px before capturing the map and selection marker. Visual inspection
confirmed a complete real basemap and teal marker, not just an attribution/control rectangle.
Evidence: `build/map-fix/live-verified/` and `build/map-fix/browser/`.

Focused updated unit checks: **22 passed** (navigation removal, geolocation and optional search).
The full frontend unit suite separately passed **211 tests in 17 files** and the production build
passed. A browser probe against the actual compiled Vite preview also passed: the local teal
selection marker rendered after a map click, both real form fields updated, zero default marker
image/shadow requests occurred, no JavaScript page errors occurred and `/status` displayed not-found.
This build-only probe used an explicitly synthetic authenticated identity and blocked external tiles;
the real API/SQLite journey and real OSM viewport above were tested separately. Its screenshot is
`build/map-fix/production-selection.png`. The preview server was stopped after the check.

The first broader run found a test-only auth-restoration timing assumption; it was corrected by
awaiting the existing session restoration. The first new browser journey also used an overlarge
public bounding-box query; it was corrected to the existing bounded nearby API. No API validation
or authorization rule was weakened.

Full default verification **passed all 28 stages**, with no skip switches:
`build/verification/20261021-205811-d538b9b4/summary.json`.

| Executed check | Final result |
| --- | --- |
| Backend unit/security/concurrency/integrity tests | 651 passed |
| Real integration/process-restart tests | 6 passed |
| Frontend tests | 211 passed in 17 files |
| Infrastructure assertions | 59 passed in 16 files |
| Default browser/accessibility journeys | 17 passed; 1 deliberately opt-in live test skipped |
| Separate real OSM browser test | 1 passed; complete requested tile grid decoded and visually checked |
| TypeScript app and browser checks, ESLint, Ruff and formatting | PASS |
| Production build and separate compiled-marker browser probe | PASS |
| Research evaluations and disposable performance checks | PASS |
| Offline CDK synthesis/template/local-safety checks | PASS; no deployment |
| OpenAPI / synthesized API contract | PASS; 131 operations match 131 routes |

These are **945 distinct automated tests** across the complete default run and separate live test;
targeted reruns are not added again. The compiled-build probe is additional and not included in that
test count. Browser checks include all four widths, actual marker dragging, permission handling,
selected-coordinate submission/read-only SQLite verification, private publication rules, existing
incident/priority/workflow journeys, reduced motion, keyboard focus and axe accessibility checks.

Executed commands included `scripts/verify.ps1`, frontend `npm run typecheck`,
`npm run typecheck:browser`, `npm run lint`, `npm test`, `npm run build`, targeted unit tests and
`npm run test:browser -- e2e/location.spec.ts --project regression`. The live-network case was
explicitly enabled with `CIVICLENS_LIVE_MAP_CHECK=1` and run with `-g 'one opt-in'`, storing results
under `build/map-fix/live-verified/`. Normal regression runs deliberately block external tiles.

The complete run's source manifest contains 463 source/configuration/documentation files. A
post-report-finalization manifest is saved separately as `build/map-fix/final-source-manifest.json`.

Normal developer SQLite SHA-256 before **and after** all changes/tests:
`175A8828EAF1A8E67D614599F2DD4695E8052507BB3F51B2384D4BCAC0606334`.
Browser writes use the existing new-UUID-only disposable database safeguards. No data reset, AWS
API call/deployment or cloud resource change was performed. Existing cloud-readiness blockers remain.
All owned test/preview listeners on ports 8002/8003/5180/5181/5190 were stopped. A hash comparison
against the prior Phase 14 release confirmed all 241 backend/infrastructure/package files unchanged.

## Remaining limitations

- Basemap imagery requires access to OSM. Future network/provider restrictions cannot be eliminated
  by frontend code; the visible error/retry and manual-coordinate fallback remain available.
- Place-name search is deliberately not configured. Offline coordinate search and the optional
  same-origin adapter are implemented; a real provider needs an operator decision and backend limits.
- Browser geolocation requires support, permission and a secure context (localhost is suitable for
  local development). Browser tests use explicitly emulated GPS fixes, not a field accuracy study.
- Numeric frontend coverage remains unverified; backend coverage and pre-existing cloud readiness
  blockers are unchanged. Visible existing dependency/CDK warnings were not suppressed or worked
  around. No AWS readiness or absolute absence-of-bugs guarantee is inferred from local passing tests.

## Start locally

Run each command in a separate PowerShell terminal from `D:\CivicLens`:

```powershell
.\scripts\run-backend.ps1
```

```powershell
.\scripts\run-frontend.ps1
```

Frontend: `http://localhost:5173`; API health: `http://127.0.0.1:8000/api/health`.
Installed dependencies are reused; no paid map key is required.

## Upstream references

- [OSM tile usage policy](https://operations.osmfoundation.org/policies/tiles/): canonical URL,
  visible attribution, browser referrer/cache behavior, no bulk requests and best-effort availability.
- [Leaflet 1.9.4 reference](https://leafletjs.com/reference.html#map-invalidatesize): container
  invalidation and marker dragging.
- [Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/): relevant only
  if an operator deliberately selects that service later; no such integration is enabled here.
