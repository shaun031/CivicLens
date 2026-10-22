# Roles and permissions

## Current Nearby Issues boundary

Only an active verified CITIZEN can call `/api/citizen/issues/nearby` or
`/api/citizen/issues/latest-location`. The server derives the owner from authentication; extra
owner/citizen parameters are rejected by the nearby query; latest-location has no owner input.
The response includes the caller's eligible reports
and only approved public summaries of other citizens. ADMIN/OFFICER have no owner-overlay bypass.
Anonymous approved-public discovery stays separate; private photographs/details retain their
existing ownership rules. Publication approval remains independent from operational status.
See [geographic discovery](GEOGRAPHIC_DISCOVERY.md).

## Phase10 permissions

Any active verified authenticated principal may read/mark only their own notifications; ADMIN is not
an inbox ownership bypass. ADMIN alone monitors workflows/dead letters/SLA policies and requests
retry/redrive/acknowledgement. Citizen/OFFICER cannot read private workflow data. Unsafe local actions
require trusted Origin; controls have bounded input and durable rate limits. Event handlers are
internal server ports, not public payload-submission endpoints. No Cognito self-role assignment or
SNS subscription API is added. Existing officer evidence/assignment authorization is rechecked.
See [notification privacy](NOTIFICATION_SYSTEM.md), [safe replay](FAILURE_RECOVERY.md).

Phase9: ADMIN alone configures departments/rules/rectangles, trusted officer memberships, availability,
capacity and manual assignment/reassignment. OFFICER alone reads their current assigned operational
queue and starts/progresses eligible work; it is not a general department/private-complaint reader.
ADMIN role does not automatically create OFFICER membership. CITIZEN cannot access any work-management
route. Anonymous401, wrong-role403, unrelated/revoked officer assignment404. Unsafe local writes require
Origin, confirmation/reason/current versions; progress cannot mark RESOLVED. Public registration still
creates only CITIZEN; trusted local provisioning and existing Cognito subject roles remain authoritative.
Evidence is independently scoped to incident membership on every authenticated photo request.

Phase8 adds ADMIN-only ranking/detail/history and confirmed versioned assessment, hazard, override,
removal and recalculation controls. Evidence references must belong to current incident members.
CITIZEN/OFFICER cannot read private priority notes or mutate any factor. Local cookie mutations check
Origin; expensive writes are rate limited. Existing citizen/public DTOs/publication remain unchanged;
citizens receive explanatory prose only, not confidential priority/override data. [API matrix](API.md).

Phase7: ADMIN-only incident catalog/detail/private member photos/history/recommendations and
confirmed, reasoned, idempotent, version-guarded corrections. No global OFFICER access added. CITIZEN
reads only their own safe association via `/complaints/{id}/incident`, never cluster counts/other
members/private canonical text. Trusted Origin required for unsafe local cookie requests. Grouping
never publishes. [API matrix](API.md), [privacy rules](INCIDENT_CLUSTERING.md).

Phase6 explicit exception: active verified ADMIN may list/inspect private duplicate pairs, perform
bounded rechecks and dismiss/mark reviewed. Pair-scoped image routes validate candidate membership
and stored image ownership; no general private complaint/evidence read permission was added.
Citizen routes retain owner-only checks. OFFICER/CITIZEN/anonymous cannot inspect matching data;
public projections never include candidate records or private evidence. Latest review actor/time
is retained across reruns. POSTs require exact local Origin. No merge/priority permission exists.

Phase 5 additions: anonymous clients may read only bounded approved-public DTOs. Active verified CITIZEN may search/aggregate only their own reports and request/withdraw publication only for their own complaint. Active verified ADMIN alone may approve/reject/unpublish through the narrow review API; this does not grant general private complaint/evidence reads. OFFICER cannot review. Unsafe local calls retain Origin checks. Public DTOs contain no reporter/private complaint IDs, notes, photos or audit records. Review/audit commit atomically. See PUBLICATION_AND_PRIVACY.md; the Phase 4 policy below is superseded only for this explicit privilege.

Exactly three application roles exist: CITIZEN, OFFICER, ADMIN. Backend `app/core/permissions.py` is the policy source used by matrix tests; frontend guards mirror it for navigation only.

Phase 4 adds a deliberately narrower resource policy: complaint creation/list/summary/detail and image endpoints require an active, verified **CITIZEN** and always enforce that citizen's ownership. ADMIN may retain citizen-portal navigation from Phase 2, but does not gain complaint/evidence access. OFFICER/ADMIN complaint-wide management is deferred. Caller-supplied citizenId, status and incidentId are not accepted as create inputs. Unknown/other-owner UUIDs return the same 404. Frontend link visibility is never authorization.

| Capability | Public | CITIZEN | OFFICER | ADMIN |
|---|---|---|---|---|
| Read health/home/project status | Yes | Yes | Yes | Yes |
| Register a local citizen / request recovery | Local only | Local only | Local only | Local only |
| Read own authenticated profile | No | Yes | Yes | Yes |
| Update own display name | No | Yes | Yes | Yes |
| Citizen portal/dashboard | No | Yes | No | Yes |
| Officer portal/dashboard | No | No | Yes | Yes |
| Administrator portal/dashboard | No | No | No | Yes |
| Change role/activation/verification through profile/public APIs | No | No | No | No |
| Manage complaints, incidents, departments, analytics | Not implemented | Not implemented | Not implemented | Not implemented |

Anonymous/invalid credentials return 401; authenticated but insufficient role returns 403. Changing URLs, X-Role headers, JSON role fields, user IDs, or unsigned JWT payloads cannot elevate privileges. Public registration/profile schemas reject extra privileged fields. Roles come from the current local database record or signature-verified Cognito groups.

## Trusted provisioning

Only a trusted local project operator can create local OFFICER/ADMIN accounts using `scripts/create-local-user.ps1` or `python -m app.scripts.create_local_user`. Password entry uses getpass, never command-line arguments or echo. The tool checks APP_ENV=local, validates roles/input, hashes passwords, and rejects duplicate accounts. No administrator-registration HTTP route or default administrator password exists.

In Cognito, group definitions do not assign membership. After verified self-registration, a future trusted provisioning workflow must bind the confirmed Cognito subject and add only CITIZEN membership. It must not take a requested role from user attributes or request bodies. Until that workflow is operational, an approved operator may perform equivalent provisioning during Phase 14. OFFICER/ADMIN require a separately approved administrative action. No client can write group or role attributes.

If a verified token contains several recognized groups, ADMIN takes precedence over OFFICER, then CITIZEN. This hierarchy resolves trusted group membership only; no unverified claim is consulted. Cognito users without recognized groups receive 403 while provisioning is pending.

Future resource ownership and department rules are separate from these role checks and must be implemented before any complaint/incident endpoints. An ADMIN dashboard today is a protected foundation with planned feature cards, not an implemented administration console.
