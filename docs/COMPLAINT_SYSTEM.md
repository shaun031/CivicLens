# Complaint system — Phases 4–5

Phase 5 preserves the submission/evidence lifecycle below and extends full-history search, real category/status/trend analytics, explicit publication consent/admin review and approved-only public discovery. COMPLAINT_SEARCH.md, DASHBOARD_ANALYTICS.md, GEOGRAPHIC_DISCOVERY.md and PUBLICATION_AND_PRIVACY.md supersede the historical v2/loaded-page-only/cloud-summary limitations below. The current additive local schema is version 3; private complaint/evidence access remains owner-only.

## Implemented lifecycle

A verified, active CITIZEN submits a multipart form. The server derives `citizenId` from the Phase 2 principal, validates fields and image limits, sanitizes all accepted images, stores the private evidence, and commits the complaint/image/idempotency metadata. The response is the actual saved record with an opaque UUID, SUBMITTED status, null incidentId and fixed UTC millisecond timestamps ending in Z. There is no matching, clustering, priority score, department assignment, notification delivery, deletion or status-transition API.

Only the owner can list, read or fetch evidence. OFFICER and ADMIN do not gain complaint/evidence access merely because they retain broader portal navigation. Unknown and foreign-owner complaint IDs share the same 404. Creation never accepts a frontend citizenId/status/incidentId. UUIDs are identifiers, not access tokens. Phase 2 cookie CSRF, CORS, account verification/activity and Cognito validation are preserved.

## Contracts and validation

`models/complaint.py` centralizes ComplaintInput/Complaint/ComplaintImage/Page/Summary and canonical category/severity enums. Categories are POTHOLE, DAMAGED_ROAD, BROKEN_STREETLIGHT, GARBAGE, DRAINAGE, PUBLIC_PROPERTY_DAMAGE, OTHER. Phase 3 fixture-only STREETLIGHT/PUBLIC_PROPERTY keys were aligned; no old persisted complaint migration was needed. Required title is trimmed 10–150 characters and description 20–2,000 (a configuration can tighten the maximum). Coordinates must be finite and bounded; neither location nor optional 200-character address/landmark is inferred from a person's device or EXIF GPS. User-reported LOW/MEDIUM/HIGH is not a computed priority.

The API uses manual bounded multipart parsing after authentication, with an OpenAPI-described multipart schema and required UUID Idempotency-Key header. Unknown/repeated fields, over two files, corrupt/unsupported/animated/oversized evidence and spoofed file paths are rejected. Windows-style filename traversal is checked in the original part header too, because multipart parsers may normalize those names before exposing UploadFile.filename.

## Persistence and concurrency

The existing AuthStore connection/transaction helper is reused. Schema version 2 adds complaints, complaint_images, complaint_requests and indexes without dropping/replacing users, sessions or other auth data. SQLite FK checks are enabled per connection. Creation, image metadata, idempotency mapping and quota accounting commit together under BEGIN IMMEDIATE; readers never see a partially completed complaint. `(created_at DESC, complaint_id DESC)` gives deterministic ordering, including timestamp ties. Query parameters cannot override ownership. Pagination is bounded, owner/provider-bound and validated; its base64 encoding is not a security signature or a replacement for authorization.

The dashboard has a separate owner-only summary endpoint: indexed aggregate counts and at most three recent records. It does not label a partial fetched page as a total. List search/filter/sort is explicitly limited to loaded results and offers Load more and Refresh. No server-wide search/discovery was added.

## Idempotency and failure recovery

The browser generates a UUID request key in its in-memory draft, disables the form immediately with a synchronous in-flight guard, and sends the key as Idempotency-Key. It keeps the key and fields after failure. Editing fields/files/coordinates denotes a new intent and rotates the key; success clears the draft and shows the real ID/details link. Draft/key state is not durable across reload/logout: if an attempt was interrupted and the draft is lost, inspect My Complaints before submitting a new report.

The repository scopes the key to the authenticated citizen and stores a SHA-256 fingerprint of normalized input plus source image hashes/MIME. Exact replays return the original committed record, even after a restart. Same key with different content yields 409. Concurrent requests have unique staging paths; the losing attempt removes only its own staged objects, never the winner's evidence. This is request idempotency, not the future intelligent duplicate detector.

All photos are validated before any storage write. Definite failed writes/rolled-back persistence remove staged objects best-effort and return an honest error, never 201. Key collisions never overwrite/delete existing evidence. A hard process stop before metadata commit can leave private unreferenced objects, but no public complaint. A stop after commit can leave a client unsure: retrying the same payload/key retrieves the saved record. Ambiguous DynamoDB transaction outcomes are checked with a strongly consistent idempotency read; if still unknown, objects are preserved and a retryable 503 is returned. There is no background reconciler pretending to have fixed that state. See EVIDENCE_STORAGE.md for a read-only local audit and trusted manual recovery.

## Quotas and diagnostics

Default quota is 10 submissions/citizen/900 seconds. SQLite counts committed new complaints in a rolling fixed-expiry bucket, inside the creation transaction. DynamoDB uses one conditional fixed-epoch-window counter item per citizen and counts eligible creation attempts, including attempts whose later transaction fails; concurrent losing attempts may consume quota. Already committed replays bypass counting. These are small-demo application quotas, not comprehensive internet/DDoS protection; upstream/global abuse controls remain a Phase 13/14 review.

Safe logs contain generated request IDs, operation, result/error category, duration and safe complaint IDs. No credentials, cookies, input text, coordinates, filenames, photos or private storage paths are logged by the complaint service. Traceback responses are disabled even in local debug configuration.

## Providers and future AWS mode

`ComplaintRepository` and `EvidenceStorage` are narrow contracts. Local/test explicitly select SQLite and filesystem using the shared database. AWS/demo/production require DynamoDB/S3 and their table/bucket references; missing or mismatched selection fails clearly, never falls back. SDK clients are lazy and are not constructed at module import/startup. Local mode does not use DynamoDB/S3.

DynamoDB stores complaint plus image metadata in one small item and conditionally transacts its idempotency record and owner summary in the existing Complaints table. Request/rate/summary sentinel records lack citizenId/createdAt GSI keys and never appear in owner lists. The ByCitizen KEYS_ONLY GSI is queried, then full records are BatchGet with bounded unprocessed-key retries. No Scan, extra table or index was added. ExclusiveStartKey is carried in the cursor; GSI results are eventually consistent and pages are not snapshots under concurrent writes. SQLite has deterministic global timestamp/ID tie ordering; DynamoDB sorts each returned page by those values but cannot promise a global UUID tie order across equal GSI sort keys without a future index redesign. A future reviewed writer/index contract is needed if that cloud guarantee becomes mandatory.

Cloud summary counters currently represent immutable SUBMITTED complaints only. Any future status/delete workflow must update counters atomically or replace this strategy; no general analytics correctness is claimed. The IAM role permits only necessary operations on the Complaints table, ByCitizen index, private evidence prefix and its logs. Gateway routes require JWT/API scope, while the backend still checks citizen role/ownership. Native Linux packaging, real IAM/runtime/GSI behavior, service quotas, costs and Cognito provisioning await Phase 14. No AWS service was contacted by this implementation or its tests.
