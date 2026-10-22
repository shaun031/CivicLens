# Personal dashboard analytics — Phase 5

GET /api/complaints/summary requires the same active verified citizen and owner scope as complaint search. It preserves total, counts and recent. New fields are byCategory, submissionTrend, trendDays and recentActivity. Optional days is 7–90, default 30; the UI offers 7, 30 and 90 days.

- total counts every stored complaint owned by this citizen, independent of pagination and trend period.
- counts groups the existing lifecycle statuses. Missing statuses display zero. Publication status is not a complaint lifecycle status.
- byCategory contains actual nonempty category groups. The chart labels use the shared category vocabulary.
- recent contains at most three latest actual records with a deterministic timestamp/ID order.
- submissionTrend groups created_at by UTC date over the inclusive period ending today. Nonempty accounts receive zero-filled days, not inferred activity. It counts submissions, not historical status transitions.
- recentActivity stays empty because a general lifecycle history does not exist. Publication audit events are internal and are not misrepresented as complaint-status events.

An empty account receives total=0, empty counts/category/trend/recent/activity collections. The screen displays the no-complaints state and a working reporting link. Summary failures produce a retryable error, not fictional statistics.

SQLite uses indexed owner GROUP BY aggregates and a bounded recent query in one read transaction. Recent image/publication metadata is batch-hydrated, so there is no per-complaint aggregation query. The preparation-only DynamoDB adapter aggregates a capped ByCitizen catalog, with the eventual-consistency/read-budget limitations documented in COMPLAINT_SEARCH.md. Existing SUBMITTED creation counters remain for backward compatibility but are not falsely used as general lifecycle analytics.

The dashboard displays six cards: total, submitted, under review, assigned, in progress and resolved. Rejected reports remain included in total and the status chart. Category and status use bar charts; submission trend uses a line chart. Lazy-loaded Chart.js registers only the required controllers/elements/scales. Animation is disabled; charts resize and are destroyed on cleanup. Each chart has a textual description and an accessible data table. Empty charts show an explicit empty state. This follows [Chart.js integration guidance](https://www.chartjs.org/docs/latest/getting-started/integration.html).

Navigating back after a successful submission remounts/refetches summary data. Period changes and Refresh dashboard also fetch anew; no frontend restart is needed. Explicit sample mode is separately labeled and never replaces a failed API response.
