# Workflow states — through Phase13

Phase13 changes no domain transition policy. Added synchronized race, replay/recovery
and real HTTP/browser lifecycle verification, not automatic repair closure or grouping.
[Executed integration evidence](INTEGRATION_TEST_REPORT.md).

Repair sidecar: IN_PROGRESS work → PENDING_VERIFICATION → ADMIN VERIFIED_RESOLVED;
or ADMIN REJECTED / REWORK_REQUIRED / INFORMATION_REQUIRED. A later allowed submission creates a
new numbered attempt, never overwrites the prior attempt. Approved evidence and citizen responses
do not change canonical state. Reopening the current verified resolution marks its attempt REOPENED,
sets the SAME canonical incident OPEN, resets linked resolved complaint statuses to UNDER_REVIEW,
invalidates priority, resumes the SLA cycle and suspends officer allocation for review. Department
context is retained by P9. All mutations are transactional, versioned, idempotent and audited.
See [repair verification](REPAIR_VERIFICATION.md) for evidence, consent and disagreement policy.

## Historical Phase9 allocation policy (still applicable)

Canonical Phase7 lifecycle remains OPEN, RESOLVED, MERGED or SUPERSEDED. This is not duplicated by
department assignment and is not changed by officer progress. Phase8 unresolved-time aging continues
while OPEN, including blocked/in-progress/100%-reported work. Observed RESOLVED freezes aging and
reopening resumes it under the existing policy. Phase9 exposes no final repair/RESOLVED endpoint.

| Assignment state | Meaning / allowed operation |
|---|---|
| UNASSIGNED | No responsible department/officer; clear routing or ADMIN confirmation needed |
| DEPARTMENT_ASSIGNED | Responsible department confirmed, no officer; recommend and approve allocation |
| OFFICER_ASSIGNED | Eligible officer allocated; that officer may start work |
| IN_PROGRESS | Assigned officer started work; may append private progress and nondecreasing % |
| NEEDS_REVIEW | Ambiguity, blocked work or invalidated allocation; ADMIN must correct/reassign |

Only the currently assigned active eligible OFFICER can start/progress. START requires OFFICER_ASSIGNED;
PROGRESS requires IN_PROGRESS. Note, reason, confirmation, current canonical/assignment versions and
operation UUID are required. Progress0..100 cannot decrease;100 is self-reported work, not verified
resolution. requestReview transitions to NEEDS_REVIEW; no further officer progress until ADMIN correction.
Administrators correct workflow through audited reassign/unassign operations, preserving prior notes.

Changing department removes/replaces an officer atomically. Removing an officer retains the department
queue or returns work to unassigned/review. Availability/membership/deactivation changes with active
work require prior reassignment. Account eligibility changes revoke local allocation automatically.
Merge/split clears conflicting active allocations, preserves history and requires review. Retired and
resolved incidents never appear in active officer/department queues. An alias does not grant an old
officer access to the surviving incident. Citizens cannot update any municipal work state.

Forbidden: officer self-assignment, self-membership/capacity changes, other-officer updates, arbitrary
department access, premature resolution, automatic report-wide status propagation, automatic publishing,
automatic repair approval or notifications. These are not mocked successes in the UI.

Next: Phase10 — Automated Event-Driven AWS Workflows, Notifications, and Escalation. NOT STARTED.
