# Repair verification (Phase12)

Phase13 adds full HTTP/browser lifecycle, synchronized feedback/approval and progress/
reassignment races, all-kind photo backup/audit, error/body protection and notification
filter contracts. Domain approval/rework rules below are unchanged. [Evidence](INTEGRATION_TEST_REPORT.md),
[security](SECURITY_AUDIT.md). Cloud domain binding still fails closed503.

Officer work percentage, repair submission, citizen feedback and official resolution are different facts.
Only a currently eligible assigned OFFICER, with IN_PROGRESS work and current incident/assignment
versions, can submit a repair. Description and timezone-aware repair timestamp are required; private
notes and up to two photos are optional. The timestamp cannot precede the incident or be in the future.

Each incident has sequential attempts. One pending attempt is enforced by a partial unique index.
Rejection/rework retains the old attempt, evidence and votes; subsequent work creates a NEW attempt.
Requests are persisted for distinct active, verified CITIZEN accounts with non-rejected reports in the
canonical incident. Accounts are not asserted to represent independently verified humans.

Membership is always `complaints.incident_id`. Every response and evidence retrieval rechecks it.
Merge/split corrections revoke stale access; approvals cannot use an obsolete incident version.
Citizens may submit CONFIRMED_FIXED, STILL_BROKEN or UNSURE, with optional text/photos. One immutable
effective response per account/attempt is enforced by a unique request/response constraint. Repeating
the same operation ID replays the receipt; changing that input conflicts. Corrections require recorded
administrative review rather than silently editing a citizen response.

## Decision policy

No vote closes or reopens an incident. Any eligible STILL_BROKEN response produces
DISPUTE_REQUIRES_REVIEW, even against several confirmations. Confirmations produce CONFIRMATION_SUPPORT;
zero/only-unsure responses produce INSUFFICIENT_RESPONSES. All are recommendations only. The admin
review includes current hazard/priority, private evidence, eligible and historical feedback, missing
responses and audit history. No-response cases are never automatically accepted or rejected.

ADMIN decisions require a reason, explicit confirmation, current attempt and incident versions:
approve; reject; request-rework; request-information; approve-evidence; reopen. Approval without a
photograph requires at least 40 characters describing independent verification. This is accountability,
not proof of an actual site visit; administrators must follow municipal verification policy. Serious
hazards/disagreements are never majority-voted away. Assignment/progress changes after submission
prevent stale approval; rework/new submission is required.

Approval atomically records the attempt, verifier, decision timestamp/reason, canonical OPEN→RESOLVED
transition, linked non-rejected complaint statuses, canonical audit, operation receipt and outbox events.
Private decision receipts/audits include explicit supporting evidence IDs and citizen-sharing approval
IDs; no photo bytes or private object keys enter domain events. Citizen response/dispute events notify
staff, not every reporter. Terminal decisions can notify the original eligible submitting officer with
a generic dashboard link, without restoring historical evidence access after assignment ends.
Unsubmitted/legacy resolved incidents are not retroactively given repair cycles. Reopening requires the
current verified attempt and matching resolution timestamp; the original incident becomes OPEN, its
resolved reports return to UNDER_REVIEW, history survives, and P9 suspends the officer for assignment
review while retaining department context. Priority invalidation/recalculation and existing SLA-cycle
triggers run; resolved intervals are excluded by P8's existing cumulative aging rules.

## Evidence

The P4 EvidenceService decodes actual JPEG/PNG/WebP, rejects unsafe names, animation, corrupt/oversized
images and excessive pixels, and re-encodes fresh JPEG pixels with EXIF/GPS stripped. Input is bounded
before multipart spooling. Photos use the existing private EvidenceStorage port and generated UUID
keys in the established `complaints/{uuid}/{uuid}.jpg` namespace (including S3 IAM). This is a shared
object-key namespace, not a second complaint-membership model.

ADMIN and current eligible assigned officers can access authorized incident photos. Citizens see only
their own feedback photos and specifically ADMIN-approved repair photos while current membership is
valid. No evidence is automatically published. Original before photos remain in the citizen's own
complaint view; cross-citizen original photos are not copied into verification. Failed known-rollback
staging is removed; key collisions never delete the existing object. An uncertain I/O commit may leave
an orphan rather than risk deleting committed evidence; controlled orphan reconciliation is needed
before cloud activation. No public object paths or image bytes appear in events/exports.

Run `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_civic_intelligence.py
backend/tests/test_intelligence_security.py` from the project root. Tests use temporary databases/photos.
