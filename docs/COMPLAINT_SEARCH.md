# Complaint search — Phase 5

GET /api/complaints remains an authenticated, active verified CITIZEN-only endpoint. Every SQL predicate or DynamoDB owner query is constrained by the verified principal, never a client-supplied citizen ID. Existing item fields, IDs, images and nextCursor are preserved; total is an additional exact local filtered count.

## Query contract

| Parameter | Meaning |
|---|---|
| q | Up to 160 input characters; title, description, landmark and address label |
| category | One canonical category |
| status | SUBMITTED, UNDER_REVIEW, ASSIGNED, IN_PROGRESS, RESOLVED, REJECTED |
| reportedSeverity | LOW, MEDIUM, HIGH |
| dateFrom / dateTo | Inclusive UTC submission dates, YYYY-MM-DD |
| sortBy | createdAt (default), category, status |
| sortOrder | desc (default) or asc |
| limit | 1–100, default 20 |
| cursor | Opaque next-page token, at most 2048 characters |

All filters combine with AND before counting or pagination. Empty search is unfiltered. Invalid enums, reversed date ranges, unsupported parameters, controls and overlong input return 422. No SQL identifier or direction comes directly from input: sort choices map to fixed allowlists and values are parameterized.

Search is accent-insensitive, Unicode-normalized, case-folded **AND token-prefix search**, not arbitrary substring, semantic matching, stemming or an FTS query language. For example `LIB road` matches library and road anywhere across supported fields. Punctuation is treated as a separator; quotes/operators never become executable FTS syntax. A punctuation-only query normalizes to empty. Combining marks are normalized for consistent local/cloud token comparison; this can reduce distinctions in some writing systems.

## SQLite indexing and fallback

Schema v3 adds owner/category/date/ID and owner/status/date/ID indexes alongside the existing owner/date/ID index. Severity is an additional predicate after owner/category/status narrowing; no speculative severity index was added. FTS5 indexes normalized supported fields by the complaint rowid. The additive migration backfills old records and installs insert/update/delete triggers in the same transaction. All application connections register deterministic search_normalize/search_matches functions. Trusted direct database writers must use AuthStore connections or register those functions; otherwise search-trigger writes fail rather than silently corrupt the index.

If SQLite lacks FTS5, migration still succeeds and parameterized owner-scoped SQL uses the registered search_matches function. Semantics remain the same, with slower per-owner text evaluation. Tests exercise this fallback explicitly. No hosted search engine is required. See the [official FTS5 documentation](https://www.sqlite.org/fts5.html).

## Ordering and cursors

Every sort includes createdAt and complaintId deterministic tie-breakers, in the selected direction. SQLite uses keyset tuple comparisons, not offset pagination. Count and page share a read snapshot. The cursor binds owner, provider, normalized filters, dates and ordering; reusing it after changing those values returns 400. Cursors are encoded context-bound pagination state, not signed access tokens: independently enforced ownership is the authorization boundary. Limit may change between pages. Concurrent edits/deletions are not a multi-request snapshot.

The frontend stores filters in URL query parameters, debounces search by 300ms, resets pagination on filter changes and ignores cancelled/stale loader results. Load more preserves the active context and deduplicates IDs. Empty filtered results are distinguished from an empty account. Real API failures never substitute samples. Cards can fetch private thumbnails through the existing authenticated image endpoint.

## AWS preparation and limits

DynamoDB has no native equivalent of FTS5 or arbitrary multi-field sorting. The demo adapter uses bounded ByCitizen Query/BatchGet pages, then performs the same normalized filters, exact owner counts and deterministic sorting before API pagination. It never scans the global table. Work is explicitly capped at 5,000 owner records (configurable 100–10,000); larger owner datasets return a clear 422 instead of silent truncation. This is a deliberately limited demo strategy, not a scalable production search engine. GSI enumeration is eventually consistent and can miss newly created records temporarily. The 15-second Lambda budget, read amplification and catalog/index redesign require Phase 14 validation before enabling AWS. Local search does not load the full database into Python.

## Measured local workload

Run from backend: `.\.venv\Scripts\python.exe -m app.scripts.benchmark_phase5`.

The executable creates and removes its own temporary database, containing 5,000 synthetic records, two citizens, 3,000 reports for the queried citizen and 500 synthetic approved projections. It never opens the configured developer database. Five warmed runs on this workstation measured:

| Operation | Median ms | Maximum ms | Returned |
|---|---:|---:|---:|
| Text search | 5.249 | 7.945 | 20 |
| Combined filters | 8.594 | 10.056 | 20 |
| Keyset page | 3.938 | 4.093 | 20 |
| Personal summary | 4.382 | 5.294 | 3,000 counted |
| Geographic bounds | 9.494 | 11.944 | 50 |
| Radius query | 11.801 | 14.211 | 50 |

EXPLAIN QUERY PLAN reports SEARCH USING COVERING INDEX for complaints_owner_category and publications_geo. FTS narrows matching rowids; counts still evaluate all matching owner records. Geographic distance work is bounded by candidate limits. These are local warmed microbenchmarks, not concurrent-load, disk-cold, production or AWS performance guarantees.
