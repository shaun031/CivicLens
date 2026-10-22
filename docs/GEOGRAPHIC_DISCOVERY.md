# Geographic discovery — citizen overlay and public boundary

## Why recently submitted complaints were missing

Nearby Issues previously consumed only the approved-public projection. New complaints correctly
start PRIVATE, so even the reporter could not discover them there. The page also defaulted to an
invented Bengaluru search point, mixed viewport/radius modes, and capped nearby searches at 5km.
This follow-up adds a separate authenticated owner overlay; it does not relax public publication.

## APIs and visibility

`GET /api/citizen/issues/nearby` requires an authenticated, active, verified CITIZEN. Required finite
coordinates are `latitude` (-90..90) and `longitude` (-180..180). `radiusKm` is an integer 1..200,
default 10. Optional `category`, operational `status`, `limit` (1..100, default 50) and `cursor`
(maximum 2048 characters) remain server-side filters. Unknown parameters, including owner IDs,
are rejected. The server derives ownership from the authenticated principal, never query input.

The result is `{items, nextCursor, countPolicy}`. Each minimal item contains `issueId`, `title`,
`category`, `status`, `latitude`, `longitude`, `distanceMeters`, `createdAt`, `dateLabel`, `isOwn`,
`isPublic`, and `detailsUrl`:

- Own eligible reports use the original title, actual saved point, submission date (`Reported`),
  private complaint UUID and `/citizen/complaints/:id`. Publication approval is not required.
- Other citizens contribute only approved public summaries, reviewed approximate points, publication
  date (`Published`), independent public UUID and `/issues/:publicId`. Original complaint IDs,
  descriptions, photographs, reporter identity, incident IDs and storage keys are never returned.
- Own published reports use the owner branch only, not a second public marker. If the actual owner
  point is outside the radius but its approximate public point is inside, it remains outside for
  that owner. This makes ownership, distance and de-duplication deterministic.
- REJECTED operational reports and reports whose citizen account is no longer active/verified/
  CITIZEN are ineligible. Publication rejection is separate: an otherwise eligible owner can still
  see their own report when its publication request was rejected or withdrawn.

`GET /api/citizen/issues/latest-location` has the same authorization and returns
`{location: {latitude, longitude}}` or `{location: null}`. Only that principal's latest eligible
report is considered. No report means no invented location.

The anonymous public APIs remain public-only: `GET /api/public/issues`, `/api/public/issues/nearby`
and `/api/public/issues/:publicId`. Their existing DTO whitelist is unchanged. The legacy nearby
parameter remains `radiusMeters` (50..200000, default 1000), not kilometres. Both radius APIs obey
`NEARBY_MAX_RADIUS_METERS` (default 200000). Public bounds remain capped at 0.25 degrees per side;
large radius searches do not reuse that intentionally small viewport validation.

## Exact radius and indexed queries

Both providers reuse the single Phase 5 `haversine` implementation, mean Earth radius
6,371,008.8 metres. A spherical bounding envelope is calculated first, splitting date-line
crossings into longitude ranges. Envelopes reaching a pole cover all longitudes. Exact distance
is then checked against `radiusKm * 1000` (or legacy metres), with a 1e-7m numerical tolerance.
Returned distances are unrounded metres; kilometres are presentation only. Distances are straight
line, not driving/walking distances. Public distances refer to reviewed approximate locations.

SQLite has additive indexes:

- `complaints_owner_radius(citizen_id,latitude,longitude,complaint_id)` for the authenticated owner.
- `publications_radius(publication_status,public_latitude,public_longitude,public_issue_id)` for
  approved public candidates.

The query explicitly uses these indexes, applies ownership/publication/eligibility and bounding-box
predicates in SQL, unions the non-overlapping sources, calls the same deterministic Haversine SQL
function, and sorts by `(unrounded distanceMeters, issueId)`. A context-bound keyset cursor and
`LIMIT pageSize+1` hydrate at most 101 rows into Python, including a continuation sentinel. Large
eligible populations are not loaded into Python. SQLite still computes/sorts qualifying indexed
bounding-box candidates; this is not a constant-time spatial tree. No old 2000-candidate truncation
is imposed on this SQL radius path. The small viewport/fine-cell endpoint retains its honest
2000-candidate refusal. Index creation is idempotent, additive, preserves schema version 8 and
does not rebuild/reset complaints, accounts or evidence.

## Client and markers

The real-data page starts without a selected point. Bengaluru is explicitly a default map view,
not detected current location. Map click/drag, manual coordinates, explicit browser geolocation,
or “Search near my latest complaint” choose the center. Center/radius survive citizen route
navigation in memory and are reset across accounts; GPS is never requested on mount. Successful
submission preserves the saved coordinates and offers “View on Nearby Issues”; returning to
Nearby performs a fresh query. My Complaints likewise reloads from the backend on mount.

The 1..200km slider defaults to 10km; presets are 1, 5, 10, 25, 50, 100 and 200km. Slider requests
are debounced 350ms. A real Leaflet circle uses metres (200km = 200000m), fits the selected area,
and remains independent of viewport panning/zooming. No search uses viewport bounds instead of
radius. Web Mercator cannot faithfully show the poles; views at |latitude| >=85 are clamped for
display, but server queries and returned coordinates remain valid and unchanged.
An explicit polar-projection warning replaces the unrepresentable radius circle in that view.

Both map and cards consume the same authorized page. Changing center/radius/category/status
clears stale items while loading; stale first-page and pagination responses cannot attach to a
different search. Clear Filters preserves radius/center. API failures, no selected center, empty
results, failed tiles and more-results states are distinct. More pages are explicitly loaded;
after 500 displayed reports, users must refine the query. Loaded counts never claim to be totals.

`categoryConfig.ts` centrally maps the seven existing enums to local SVG divIcons: orange pothole,
red road construction, yellow bulb, green trash, blue water/drainage, purple building, grey other.
Unknown marker categories use Other. No external image URLs or user content enters marker HTML.
The teal crosshair identifies the search center. Popups/cards show authorized title, category,
status, distance, correct date label, owner/private badge and the existing authorized detail link.
Marker selection highlights its card; “Show on map” focuses/opens its marker. The native details
legend collapses on mobile or desktop. No heavyweight map dependency was added.

Shared resize invalidation preserves the geographic center (`pan:true`, no animation) so existing
marker pixels remain inside a narrower map. Nearby popups have bounded width/height, scroll dense
content and reserve room beside zoom controls. Browser checks verify actual marker/popup
rectangles inside the map, not merely DOM presence, at all four acceptance widths.

Clustering is a lightweight 64-pixel projected grid over only the loaded page (maximum 500 items).
Clusters show individual-report counts and zoom on click. Selecting a co-located report opens
that exact point; no artificial coordinate jitter is introduced. Multiple reports belonging to
one master incident remain individual reports, clearly labeled **not unique incidents**. This
visual grouping neither merges complaints nor changes master incidents or backend counts.

Real OSM tiles load by default, with attribution, privacy disclosure, hide/retry controls and
manual/list fallbacks. Loading shares IP and viewed area with OSM. No prefetch, bulk download,
fake tiles or cache bypass. Regression tests block external tiles; the existing opt-in live test
is separate. See the [OSM policy](https://operations.osmfoundation.org/policies/tiles/).

## Future DynamoDB mode — source preparation, not deployment

The regional adapter reuses existing KEYS_ONLY `InternalGeography` and `PublicGeography` GSIs.
Five-degree parent partitions (`r5:rr:cc`) avoid enumerating thousands of fine cells at 200km;
their bounded envelope covers at most 144 partitions near a pole. Owner partition keys are
`citizenId#r5:rr:cc`, never another caller-supplied owner or a global owner catalog scan.
Minimal `owner-region#complaintId` projections are created in the complaint transaction.
Minimal `public-region#publicId` projections are written/tombstoned in the publication transaction.
They do not add `citizenId`/`createdAt` attributes to the ByCitizen index or add new GSIs/tables.

Query pages have at most 100 evaluated items, with SDK continuations and a bounded candidate
budget (2000 default across the whole search). Strong BatchGet reads in batches <=100 revalidate
regional projections and current source ownership/publication/eligibility before serialization.
Retries are bounded; dense regions return an actionable 422 rather than incomplete success.
Stale withdrawn/rejected source records cannot become public through stale index entries. Public
queries only use PublicGeography. No Scan is used. SDK behavior is verified offline with mocks.

`CLOUD_DISCOVERY_REGIONS_READY=false` deliberately gates the new cloud citizen and expanded-radius
path until a separately reviewed, complete projection bootstrap/backfill is verified. Existing
cloud data must not silently disappear because legacy rows lack parent projections. No migration/
backfill was run, no completeness verifier/provisioning is claimed, and no cloud execution was
tested. A future deployment must supply a verified export/backfill procedure, enable the flag in
the reviewed deployment environment, and assess GSI eventual indexing delay, read budgets/hot
partitions and production performance. Legacy public nearby searches <=5km outside polar regions
retain the fine-cell path. Strong revalidation prevents disclosure, not GSI indexing delay for
new reports. Source-only cloud readiness remains blocked by the previously documented bindings,
packaging and hosting gaps. Both new cloud HTTP routes require JWT; no anonymous boundary weakened.

Upstream contracts: [Leaflet 1.9.4 Circle](https://leafletjs.com/reference.html#circle) and
[DynamoDB GSI projection and synchronization](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GSI.html).

Verification evidence and the changed-file inventory: [Nearby Issues implementation report](NEARBY_ISSUES_FIXES.md).
