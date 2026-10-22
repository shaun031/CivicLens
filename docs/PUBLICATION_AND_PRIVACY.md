# Publication and privacy — Phase 5

Current Nearby Issues adds a distinct authenticated owner-only overlay, not a relaxation of
publication. Eligible unpublished complaints are visible only to their verified citizen owner,
using minimal fields and their existing private detail route. Other citizens/anonymous readers
still receive only reviewed public summaries, approximate points and independent public IDs.
See [the current nearby contract](GEOGRAPHIC_DISCOVERY.md).

## Independent states

New complaints have citizenRequestedPublication=false and publicationStatus=PRIVATE, regardless of lifecycle status SUBMITTED. Existing records migrate with the same private default. Publication metadata is stored separately and does not replace category, severity, ownership or lifecycle fields.

The owner uses PATCH /api/complaints/{complaintId}/publication-request with exactly `{ "requested": true }` or false. Authentication must be active verified CITIZEN; another owner's/unknown complaint returns 404. True creates PENDING_REVIEW, never PUBLISHED. False withdraws consent and removes public discoverability atomically, including for an already published entry. No client-supplied owner, summary or publication status is accepted here.

ADMIN alone uses PATCH /api/admin/complaints/{complaintId}/publication with APPROVE, REJECT or UNPUBLISH. OFFICER has no review authority. Local unsafe requests retain exact-Origin CSRF checks; cloud routes retain JWT scope and independent backend RBAC.

APPROVE requires an active pending citizen request, explicit reviewedForPrivacy=true, a separate 15–300-character publicSummary, and reviewed publicLatitude/publicLongitude. Contact-like numbers, email/link markers, markup and controls are conservatively rejected. Administrators must still review for personal information: automated checks cannot establish anonymity or detect every name/address. Select a safe general location; coordinates round to three decimal places before indexing/serialization. Never simply copy private notes or a sensitive home location.

REJECT applies to an active pending/published request and removes its public representation. UNPUBLISH applies to a published record and clears active consent. Owners may withdraw and request review again; reapproval is mandatory. Public UUID remains independent from the complaint UUID. Public endpoints only return currently approved fields and never private photographs; private image access remains owner-only even when publication is approved.

## Minimal review interface

Owners can request/withdraw on their existing complaint-details screen. The administrator dashboard links to /admin/publication-review. This deliberately narrow form takes a complaint ID supplied through trusted coordination with the requesting citizen, a decision, reviewed summary and general coordinates. It is not a municipal moderation queue, broad complaint browser or Phase 11 dashboard. Approval eligibility and role are checked by the server, not the form. Operator coordination is still required to obtain/verify that source information; the form does not certify a report as a verified municipal incident.

## Atomicity, audit and failure

SQLite publication change and publication_audit event commit in one BEGIN IMMEDIATE transaction. Each event has event UUID, private complaint ID, actor, action, previous/new publication state and UTC timestamp; no raw private description or evidence is copied into it. Audit records have no public read endpoint. An audit write failure rolls back the publication change.

DynamoDB uses a revision-conditional transaction to update private metadata, replace sanitized/nonindexed public projection and append to the existing AuditEvents table. Missing audit configuration refuses mutation. Concurrent decisions return 409; network ambiguity returns 503 and may require checking persisted publication state before retry. There is no unaudited success fallback. Public reads use strong primary rechecks after GSI lookup to avoid returning stale withdrawn projections.

Public GET responses are no-store, bounded by geographic area/candidates/page size and rate-limited. No field whitelist is implemented by merely hiding private properties in React: dedicated backend DTOs enforce it. Public links refer only to public UUIDs and public details. Search/GPS query strings are removed from application HTTP access logging; deploy-time proxy and provider logs still need review. Public information may already have been seen/copied before withdrawal; no claim is made that withdrawing can erase third-party copies.

## Verification and deferred features

Tests cover private defaults, ownership, citizen/officer/anonymous review denial, consent requirements, safe summaries, approval/rejection/unpublish/withdrawal, audit rollback, public field whitelists, sparse index removal and persisted state after process restart. Synthetic benchmark data exists only in temporary databases. Optional sample maps are explicitly fictional and cannot publish themselves.

No duplicate matching, record merging, support/voting, image publication, automated moderation, incident cluster, dynamic scoring, department assignment or municipal repair workflow was introduced. AWS remains source-only and blocked until Phase 14.
