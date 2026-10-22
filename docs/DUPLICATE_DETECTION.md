# Phase 6 — explainable duplicate complaint detection

Current Phase13: unchanged engine/configuration, centrally reproduced five-baseline
evaluation with image-availability strata, threshold curves and family bootstrap.
Perfect tiny synthetic scores do not establish field accuracy; Recall@K needs a
separate labelled retrieval corpus. [Measured results/limits](RESEARCH_EVALUATION_REPORT.md).

Phase7 initializes separate singletons and adds explicit audited ADMIN corrections and optional
guarded auto-linking. Pair scores/dismissal/review remain distinct from membership; Phase6 alone
still never merges. [Current incident rules](INCIDENT_CLUSTERING.md) supersede historical no-incidents
implementation statements below. Public discovery remains publication-based.

Implemented locally, CPU-only. A candidate is a review suggestion about the same physical problem,
not a merge, incident, priority change, department assignment or calibrated probability.
Phases 0–5 APIs and privacy defaults are preserved. No AWS resources were deployed.

## Architecture and execution

`app/algorithms/duplicate_detection` separates typed inputs/results, configuration, category rules,
candidate selection, geographic similarity, text, images, fusion and deterministic explanations.
Algorithms have no database sessions, SDK clients or FastAPI request inputs. The existing shared
Haversine function supplies metre distances; there is no alternative distance formula.

Submission commits the complaint, photos' metadata, request idempotency and a durable matching job
in the same transaction. SQLite's additive AFTER INSERT outbox trigger is intentionally cheap.
The local lifespan worker sees only committed jobs and performs one bounded comparison run at a time
in a worker thread. Matching failure cannot roll back the already successful HTTP 201 or delete photos.
`APP_ENV=test` disables automatic processing for deterministic fixtures; normal `APP_ENV=local`
enables it unless `MATCHING_WORKER_ENABLED=false`. No daemon runs inside Lambda.

Jobs transition PENDING → RUNNING → COMPLETE or INCOMPLETE. Exceptions set RETRY with an error class
only and a 60-second delay. A random lease token and 120-second expiry recover interrupted workers;
token-checked commits prevent a superseded worker from committing. Review decisions survive reruns.
SQLite commits every run's pair upserts and job result atomically. AWS uses one transaction with
at most 90 pairs plus job completion. A durable outbox exists there too, but automatic cloud queue
consumption is deferred: administrators can explicitly recheck one complaint. No SQS/EventBridge
workflow was implemented. Processing interface/storage are replaceable in a future phase.

## Candidate selection, privacy and bounds

The INTERNAL SQLite latitude/longitude/category/status/ID covering index includes eligible PRIVATE
complaints. It is separate from public publication approval/indexes. A latitude-range indexed
bounding-box query, longitude/antimeridian check, compatible categories and active status filters
run before loading text/images. Source IDs are excluded. At most `matching_candidate_limit + 1`
rows are fetched; the extra row signals truncation. Exact Haversine distance then filters and ranks
the retained subset. A cap is not a nearest-neighbor guarantee in dense data.

Default active statuses: SUBMITTED, UNDER_REVIEW, ASSIGNED, IN_PROGRESS. RESOLVED/REJECTED are not
eligible. Historical matching is deliberately disabled, not silently mixed into current results.
Recheck CLI can visit historical *source records*, but an inactive source produces no active matches.

Default category radii are experimental: streetlight 30m, pothole 50m, damaged road/drainage 75m,
others 50m. Related-category comparisons use the SMALLER of the two radii, ensuring symmetry.
The explicit compatibility matrix permits same categories and optionally POTHOLE↔DAMAGED_ROAD.
OTHER↔OTHER is conservative; all other cross-category combinations are rejected. All 49 ordered
category combinations are tested. Garbage/drainage is not an automatic exception.

SQLite supports polar bounding envelopes and antimeridian wrapping. AWS queries neighboring shared
0.05-degree cells using its separate InternalGeography sparse GSI, strongly reloading primary items
and revalidating exact category/status/distance. Queries wider than 16 cells fail retriably rather
than scanning, including some polar locations. GSI propagation remains eventually consistent; a
complete run is not a strongly consistent global snapshot. Future deployment must recheck after
propagation and maintain these internal attributes when coordinates/lifecycle change.

The default CPU-loop budget is 8 seconds with 100 local candidates (maximum 500); cloud uses 90.
This is a cooperative deadline between comparisons, not a hard preemption of a model load or storage
operation already in flight. Storage adapters also have bounded size/time/retry settings. Runs record
queryTruncated/timeBudgetExceeded/incomplete, compared count, timings and versions. INCOMPLETE requires
an explicit recheck/configuration adjustment; it is never presented as proof there are no duplicates.

## Text

Unicode NFKC/casefold, whitespace/punctuation normalization and restrained repeated-character cleanup
preserve negation, numeric asset identifiers and location qualifiers. Documented synonym rules include
big→large, gate→entrance, college/university→campus, lamp post→streetlight and rubbish/trash→garbage.
These can lose nuance; they are not a semantic language model. Title and description are the ONLY
textual inputs; reporter identity, contact information, landmark/address and arbitrary profile fields
are not ingested. Descriptions can themselves contain personal text, so vectors/caches remain internal.

Scikit-learn TF-IDF is fitted once lazily on the bundled, fixed 14-document infrastructure vocabulary,
independent of citizen data and evaluation pairs. Word 1–2 grams contribute 70% and char-within-word
3–5 grams 30% of cosine similarity. Both representations are L2-normalized. Vocabulary feature limits
are 8,000/12,000; bounded caches retain at most 2,048 vector pairs and 4,096 clipped preprocessed texts.
No pair-specific refit, download, embedding model, hosted API or GPU is needed. Version includes corpus,
preprocessing rules and installed sklearn version. English is the supported baseline; Unicode-safe
handling does not imply multilingual understanding or robust semantic paraphrase recognition.

## Images

Evidence is loaded only by generated, validated internal keys through the existing EvidenceStorage
interface. Clients never provide a matching filesystem path. Pillow reads already-sanitized JPEG bytes
with size/pixel checks. A 9×8 grayscale resize creates a 64-bit difference hash (`dhash64-v1`).
Normalized score is `I = 1 − Hamming(hashA, hashB)/64`. Successful fingerprints are cached by immutable
image UUID and algorithm version. Missing/read-failed/corrupt/low-contrast images are UNAVAILABLE,
not numerical zero. Failed reads are retried on a later recheck rather than cached permanently.

At most two images per complaint and four pairs are compared. The maximum informative pair score
provides supporting evidence, without counting photographs as extra independent support. Almost equal
hashes explicitly warn about reused photographs. Hashing is vulnerable to collisions/stock images and
may fail for different viewpoints, lighting, seasons or repair states. It does not recognize arbitrary
same-object photographs. Low-information flat images do not contribute.

## Fusion and safety

`L = max(0, 1 − distance/categoryRadius)`

`M = 0.40L + 0.40T + 0.20I`

Without a usable image, renormalize to `M = 0.50L + 0.50T`; effective image weight is zero and the image
score is null. Available actual image score zero is DIFFERENT from unavailable image evidence.
UI shows `100M / 100` as a **similarity index, not probability**.

Initial score bands: ≥0.80 STRONG_CANDIDATE; ≥0.60 REVIEW_REQUIRED; lower WEAK_MATCH. Safety gates can
override bands with CATEGORY_MISMATCH, OUTSIDE_SEARCH_RADIUS or INSUFFICIENT_EVIDENCE. At least four
distinct meaningful text tokens including an infrastructure asset term, and text similarity ≥0.35,
are required. Strong candidates additionally
need text ≥0.75, same known category and separation ≤10m. Other/related categories and distinct nearby
assets require review. Opposite direction/inside-outside/first-second qualifiers, differing numeric
asset identifiers, working/not-working conflicts and explicit separate/different-object mentions
require manual review. These heuristic gates are conservative, not proof of identity or completeness.

Ranking is combined score descending, text evidence descending, distance ascending, stable candidate UUID.
Saved results contain numeric components, effective weights, category relation, method/model/config
versions, explanation, missing/unreliable evidence warnings, review state and timestamps. Canonical
sorted complaint UUIDs generate a UUIDv5 candidate ID: A↔B and B↔A update the same record. Candidate
records are retained rather than unexpectedly deleted. Inspect lastCheckedAt/current processing state;
old candidates are historical comparisons, not a continuously refreshed materialized view.

## Administrator review and operations

`/admin/duplicate-candidates` supports search, category/classification/review/score filters, score/date
sorting, pagination, loading/errors/empty states and explicit ID recheck. Detail pages compare original
private text/categories/coordinates and authorized photos, components/weights/versions/explanations,
processing incompleteness and review dates. Dismiss, mark reviewed possible duplicate, rerun and back
are available. No merge or priority controls exist. Review metadata records the latest actor/time/state;
it is not an append-only review-history audit log.

Every route requires active verified ADMIN on the backend. Existing CITIZEN owner-only private routes
are unchanged; OFFICER/anonymous/unrelated citizens cannot retrieve matching records or pair evidence.
Admin evidence access is restricted to images belonging to the selected pair, not general arbitrary
private complaint access. Reporter identity and storage keys are excluded from comparison DTOs.
Unsafe local calls require exact trusted Origin. Matching routes use no-store/nosniff headers and
existing persistent admin query quotas. Private descriptions/bytes/paths never enter diagnostic logs.

See API.md, DATABASE_DESIGN.md and MATCHING_EVALUATION.md. Historical recheck is local-only, bounded,
resumable by printed UUID and supports --dry-run / --only-outdated config and text-model checks.
It does not delete candidates, assign incidents or update complaint severity/priority.
