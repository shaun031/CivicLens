# Real in-app notifications

Normal authenticated pages use real private backend records. Explicit sample preview remains separate;
sample reads are temporary and never create real notifications. All roles can use /notifications;
citizens retain /citizen/notifications. Unread navigation refreshes on navigation and explicit actions,
not an aggressive timer. Lists fetch on load/filter/page and support Refresh, mark-read and mark-all-read.

Types: COMPLAINT_RECEIVED, COMPLAINT_UNDER_REVIEW, INCIDENT_STATUS_CHANGED, INCIDENT_ASSIGNED, OFFICER_ASSIGNED,
WORK_STARTED, WORK_PROGRESS_UPDATED, INCIDENT_OVERDUE, URGENT_HAZARD_REVIEW,
ADMIN_ACTION_REQUIRED. Titles/messages are fixed safe templates, never raw complaint or officer notes.
A received notification means the report is stored; triage and municipal assessment may still be
pending. It does not mean that a municipal repair is approved.
Operational progress does not silently change the original complaint's lifecycle or verify final resolution.

Recipients come from current report membership/ownership, valid officer assignment and a trusted admin
directory. Current officer authorization is checked again for an assignment event. Stale assignment
messages cannot grant evidence access. A recipient/event/type unique key prevents repeated delivery
from creating another in-app notification; several reports from one citizen do not cause a storm.
Accounts must remain active/verified locally. Cognito directory/lifecycle synchronization is a cloud
deployment prerequisite, not a public self-provisioning API.

GET /api/notifications accepts limit1–50, ownership/filter-scoped cursor, type and read=true/false.
GET /api/notifications/unread-count returns stored unread count.
PATCH /api/notifications/{UUID}/read and POST /api/notifications/mark-all-read persist read state.
No recipient parameter conveys authority; even ADMIN sees only their own inbox. Another user's ID
returns404. Unsafe local-cookie actions require trusted Origin; private responses are no-store.
Chronological ordering is timestamp plus notification UUID, not an unstable offset.

SQLite stores delivery_status=IN_APP. This is not an email/SMS/push success claim.
The SNSPublisher adapter requires an enabled channel, eligible operational event and explicit opt-in;
it publishes only a small UUID/type envelope to a configured topic. SDK MessageId means SNS accepted
publication, not that an email arrived. Returned outcome is PUBLISHED or SKIPPED; errors propagate for
durable caller retry, rather than fabricating delivery success. Automatic SNS publication is not wired
into normal user notification delivery in Phase10. No personal subscriptions or email addresses are
created, and no real message has been sent. Future email topic subscriptions require the recipient's
confirmation and an explicit Phase14 channel/retention/cost review.

Cloud inbox querying is bounded and eventually consistent; count beyond100 retained notifications
fails explicitly pending retention reconciliation. No count is invented from a truncated page.
