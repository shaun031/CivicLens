# Phase 13 integration and data-preservation report

Date:2026-10-21. Windows11, Python3.13.2, SQLite3.45.3, Node22.20.0;
FastAPI/React/Vite, no containers. All write tests use generated users and disposable
databases/evidence. The developer DB is accessed only by explicit read-only diagnostics.

## Evidence layers (do not conflate them)

| Layer | Evidence | Scope |
|---|---|---|
| Unit/repository | `backend/tests`, including security and thread races | Real SQLite constraints/transactions plus explicitly mocked SDK contracts |
| Local HTTP / restart | six `tests/integration` tests | Existing tests spawn/stop real local processes; new full lifecycle reconstructs app and runs real ASGI HTTP contracts and durable worker, not TCP or mocks |
| Browser |13 Playwright tests | Real isolated Vite/FastAPI servers on5180/8002 and5181/8003, generated staff/users, real persisted changes; no reused developer server |
| AWS | SDK Stubber / mocked JWT profiles / CDK | Offline source/contracts only, not an end-to-end cloud deployment |

Final executed counts and timings are consolidated in [readiness](PHASE13_READINESS_REPORT.md).
Playwright configuration rejects a development-DB path override and traversal run
ID before startup (negative `--list` probes), and validates new UUID fixture paths
before launching owned servers. Worker reloads may reopen their current fixture;
no arbitrary developer path is accepted.
The baseline process test initially failed409 during concurrent worker routing;
the test now explicitly refreshes/retries only a definitive rejected409. Other errors
still fail and version/permission assertions were retained. No test was removed.

## Citizen journey

Existing browser flows verify registration/login, refreshed authenticated state,
profile edit/logout, real report with private photo, dashboard/search/filter/details,
unauthorized foreign ownership, reviewed publication/withdrawal and nearby discovery.
The integrated lifecycle persists a photo complaint before closing the first app;
a fresh app's worker processes the durable outbox through matching, canonical
creation, priority and department routing. Received notifications are persisted.
The eligible citizen records feedback but the incident stays OPEN until ADMIN approval.
Repair notification filtering is now a verified backend/frontend contract.
The final expanded rerun persists two photo reports and inspects/reviews the actual
duplicate candidate through ADMIN APIs before physical-identity-confirmed merge.
It asserts two reports but one unique reporter, then explicitly reviews the intended
post-correction REVIEW_LOCK using the server's suggested department before assignment.
An initial test assumption of department carryover was corrected to this safe policy;
no routing/authorization guard was removed. Expanded journey:1 passed in25.65s.

Negative cases include bad coordinates/files/headers, unauthorized IDs, stale cursors,
ineligible verification feedback, repeated votes, extra role fields, expired session
and reset replay. Preview data never submits real repair responses.

## Officer and administrator journeys

Trusted staff provisioning is fixture setup, not a public promotion API. Seeded
department rules, active officer membership/capacity, manual assignment, officer
queue/start/progress and reassignment revocation are exercised through actual APIs
and browser pages. The officer submits repair evidence without closing the incident;
ineligible/other officers and ADMIN endpoints are denied. Rework preserves the prior
attempt and enables a new attempt, with history retained (repository regressions).

ADMIN views include real command-center counts, candidate review, canonical merge/
split, priority factors/hazard/override, allocation history, workflow/SLA monitoring,
private reports/CSV and Phase12 repair/recurrence/fairness pages. The full HTTP test
approves a current repair exactly once, drains notifications, submits a genuinely
later report and verifies a distinct canonical incident plus recurrence suggestion.
It never auto-merges different repair cycles. Existing tests cover reopen/reject/
request-information/evidence approval, disputes and audited review state.

## Persistence, concurrency and failure recovery

SQLite integrity/FK diagnostics pass; additive initialization is rerun twice on
populated fixtures without losing rows. New backup creation includes complaint,
repair and feedback photo references, checks hashes/FKs, refuses existing destinations,
and detects corrupted fixture evidence. Restoring the snapshot into fresh fixture
paths preserves reports/repair/votes. Nothing restores over the development database.

Actual thread races test competing complaint idempotency, singleton/candidate creation,
incident mutations, priority controls, assignment/capacity, queue claims, repair
submission/approval and eight concurrent notification attempts. New synchronized
races cover citizen dispute vs approval, officer progress vs unassignment, analytics
snapshot vs merge and split vs priority calculation. Either a valid fenced winner
or a consistent snapshot is required; a stale score must be labelled stale.
Cloud enqueue/completion race tests are stubs, not real DynamoDB concurrency.

The twelve requested race scenarios are covered as follows (real local threads,
unless explicitly labelled as a mocked cloud race elsewhere):

| Scenario | Executed evidence |
|---|---|
|Two citizens, same problem|New `test_two_citizens_reporting_same_problem_concurrently_preserve_both_reports` |
|Concurrent canonical creation|Existing four-thread singleton creation in `test_incidents.py` |
|Concurrent duplicate processing|Existing pair-processing/candidate uniqueness in `test_duplicate_workflow.py` |
|Merge plus new report|New `test_merge_racing_new_complaint_does_not_drop_original_or_new_membership` |
|Split plus priority calculation|New split/priority race, stale/version fence assertions |
|Two administrators assigning|Existing two-thread assignment winner/history and global capacity tests in `test_work_allocation.py` |
|Officer progress plus reassignment|New progress/unassignment race, current permission/version assertions |
|Two repair approvals|Existing two-thread ADMIN decision winner in `test_civic_intelligence.py` |
|Feedback during review|New dispute/approval race preserves accepted feedback or returns explicit rejection |
|Replay during priority work|New membership-event/priority race, receipt and no-repeat-history assertions |
|Concurrent notifications|Eight attempts/four threads, one deduplicated inbox record |
|Analytics refresh plus merge|New consistent snapshot/membership-epoch race |

The dedicated marker group ran19 cases successfully in38.57s (including separately
labelled cloud race fixtures); this is not a claim that all19 are live cloud tests.
The final three explicit local scenarios were added after the648-case full collection
started; all seven Phase13 race tests were rerun together,7 passed in16.70s.

Recovery tests cover controlled DB locks/audit rollback, worker process interruption,
lease expiry simulation, temporary/permanent failure, bounded retry/DLQ/redrive,
notification deduplication and failed image cleanup/collision safety. Original reports,
private images and accepted feedback are preserved. Delivery is at-least-once;
idempotency fences business effects, not an exactly-once transport guarantee.

## Read-only development database audit

At assessment start: schema8,770048bytes, SHA256
`F254663D7A0F6608CC0C96D34C6530E0A1C2AD57E296B85B963415C9A0980710`.
Integrity `ok`, zero foreign-key violations and12 aggregate consistency checks passed.
Checks include owner/canonical references and counts, retired aliases/memberships,
assignments, pending-repair uniqueness, response/recurrence/notification/queue dedup.
No migration, reconciliation repair, photo deletion or user-data backup was run.
These are structural checks, not proof of physical repairs or a complete priority audit.

## UI/accessibility coverage limitations

Real Chromium/Chrome flows use keyboard/focus, dialogs, loading/error/empty states,
safe preview, map/table alternatives and Axe assertions at375/768/1024/1440px for
selected screens. ADMIN analytics, reports, repair navigation and fairness at375/1440
are exercised. This is not manual screen-reader certification or an Axe sweep of
every possible dialog/state. Frontend tests mock fetch responses and do not by
themselves prove the end-to-end journey; the browser and HTTP suites provide that evidence.
