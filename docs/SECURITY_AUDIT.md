# CivicLens Phase 13 security audit

Assessment date: **2026-10-21 (Asia/Kolkata)**. Scope: source, disposable local
fixtures, real local HTTP/browser flows, SDK stubs and offline synthesized policy.
No intrusive external scanning, AWS API, paid service, deployment or real photo changes.

## Threat model and boundaries

Protect citizen identities, private reports/GPS, original and repair/feedback
photographs, sessions, assignments, administrative decisions and durable events.
Adversaries include unauthenticated clients, another citizen, an unassigned officer,
replayed requests/events and malicious input. The local machine operator is trusted:
SQLite, environment files and the reset outbox are not safe against a compromised OS.
Grid indicators and reviewed public projections must not reveal private source evidence.

## Findings and remediation

| Finding | Severity | Disposition / regression evidence |
|---|---|---|
| Ordinary JSON/control requests unbounded before parsing | Medium, resource-exhaustion exposure | Fixed: streamed 64KiB default on unsafe `/api/` requests, configured 16KiB–1MiB; upload routes retain separate 3.25MiB bound. Actual bytes checked even without Content-Length; malformed/duplicate lengths rejected. `test_release_security.py` |
| Limit/configuration responses could miss security/cross-origin response handling | Medium, defense/operability gap | Fixed: outer CORS wrapper and API-wide no-store, no-referrer, nosniff, frame DENY and generated request IDs. Production HTTPS HSTS. No reflection of supplied request IDs. Same regression group |
| Evidence orphan audit omitted repair/feedback evidence | Medium, operator data-preservation risk | Fixed: union all three private evidence kinds via truly read-only DB connection. No deletion/quarantine is automatic. `test_evidence_audit_does_not_misclassify_repair_objects` |
| Repair notification filter/type contract omitted new notification kinds | Low, broken filter/UX | Fixed backend Literal and frontend labels; cross-language key contract and real journey filter tested |
| Coverage/debug files could enter CDK source assets | Low, unnecessary developer artifact exposure | Fixed asset exclusion of `.coverage*`, coverage and htmlcov, in addition to data/.env/tests/.venv; staged-tree CDK assertion |
| Browser fixture environment overrides could select existing/developer files before later fixture checks | Medium, test data-preservation risk | Fixed config preflight UUID/root/new-file validation before servers start; valid worker reload remains supported. Developer DB override and traversal run ID probes both fail before startup; default13-test discovery succeeds |
| Host-installed logging handlers caused LOG_LEVEL to be ignored | Low, excessive logs | Fixed root level application. Existing query-string privacy filtering remains |
| Incomplete cloud domain bindings / source-only Lambda / hosting | Deployment blocker | Not hidden behind local fallback. AWS repair HTTP returns503; no production-readiness assertion. See AWS readiness report |

No unresolved **identified** critical/high application exploit was demonstrated in
the exercised local scope. This is not a penetration-test certification or proof of
absence of defects. Deployment remains blocked independently of the local findings.

## Authentication and authorization

Local: Argon2id maintained defaults; 12–128 character passwords; generic failed
login; persistent per-IP/account throttles; case-insensitive unique email; hashed
random server-side sessions; login rotation; HttpOnly, SameSite=Lax cookies and
Secure on HTTPS; exact Origin for unsafe requests; reset token single use, expiry,
private outbox and session invalidation. Public registration rejects role extras.
Staff creation is trusted local provisioning, not an unauthenticated API.

`test_auth.py`, `test_cognito.py`, `test_release_security.py` exercise forgery,
expiry/reset, CSRF/CORS and role denials. The generated-route test checks every
private GET without identity and all staff GETs as a citizen, including malformed
IDs, pagination/filter endpoints. Object tests cover foreign complaint/photo IDs,
current membership after merge, officer assignment revocation, unrelated repair
requests and notification ownership. UI hiding is not an authorization mechanism.

Cognito uses lazy cached JWKS (300s), RS256 signature/issuer/expiry/iat/client_id/
token_use/access-scope checks and subject-bound verified userInfo. Signed group
claims determine roles; user-selected role headers are ignored. Local tests use
generated RSA keys and mocked profiles, never Cognito. Account provisioning,
revocation behavior and real hosted OAuth remain live prerequisites. MFA is OFF
in the prototype definition; staff MFA needs a documented pre-public-demo decision.

## Input, output and evidence

Parameterized SQL and fixed allowlisted ordering/filter expressions remain in use;
bounded search/cursors, finite coordinates, timezone-aware dates, enum/schema
validation and CSV formula defenses are tested. React renders untrusted text, not
unsanitized HTML; the new notification XSS test asserts literal img/script strings
and absence of DOM img/script elements. This is not an exhaustive XSS proof.

Evidence: at most two files, 1.5MiB each; actual JPEG/PNG/WebP decode, pixel/dimension
bounds, EXIF orientation and fresh RGB/JPEG re-encoding strip GPS/metadata. Generated
UUID keys only; no raw filename path construction, static uploads mount or public
S3 URLs. Local exclusive writes, symlink/junction refusal, no-overwrite collisions,
safe rollback cleanup, private get and member/assignment checks are regression-tested.
Repair photos require specific ADMIN approval to share with eligible reporters;
feedback photos stay owner/private staff evidence. A repair approval is not blanket
photo-publication approval. Windows POSIX mode bits do not prove restrictive NTFS
ACLs: protect the developer account, directory ACL and disk encryption manually.

Unexpected API errors return generic500 and safe category logging, never tracebacks.
Private paths/query values/photo bytes/reset tokens must not enter operational logs.
Uncertain commits may leave orphan objects intentionally; inspect before any removal.

## Dependency and infrastructure review

`pip check`: PASS. Frontend/infrastructure `npm audit --json`: zero published
advisories returned for 313 /117 dependencies. The opt-in PyPI release JSON check
completed for59 third-party installed packages: zero non-withdrawn advisories
reported. Date/source/versions are in `build/phase13-python-advisories.json`.
This is a registry snapshot, not a guarantee against future advisories or malware;
recheck before deployment. No dependency reinstall, blanket upgrade or lock deletion.
PyPI methodology: [official JSON API](https://docs.pypi.org/api/json/).

IAM/template review: five scoped execution roles/policies; no AdministratorAccess,
normal DynamoDB Scan/DeleteItem, unrestricted object/list grant, public bucket or
browser IAM credentials. Justified wildcards are dynamic log streams, the generated
`complaints/*` object namespace, and the Step worker's version/alias invoke ARN.
127 of131 HTTP routes require JWT plus API scope; health and three reviewed public
discovery GETs are public. Bucket public blocks, TLS-only policy, SSE-S3, retained
tables/bucket and bounded queues/workflows are asserted offline. Live IAM is unverified.

## Regression commands / residual risks

`python -m pytest -m security`, `python -m pytest -m concurrency`, full verify and
Playwright run against isolated fixtures. Marker selection is documented in
`backend/tests/conftest.py`; do not equate a test count with comprehensive coverage.
See [known risks](KNOWN_RISKS.md), [integration](INTEGRATION_TEST_REPORT.md) and
[coverage/final results](PHASE13_READINESS_REPORT.md). No scan of a service outside
the project's authorized local/test scope was performed.
