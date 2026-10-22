# Non-secret environment and release configuration guide

All `VITE_*` values are public build inputs: never put passwords, session/JWT tokens,
AWS keys, client secrets or database credentials in them. `.env*` (except examples),
DB/data/evidence and build artifacts are ignored/excluded from Lambda source staging.
The source release manifest lists hashes and installed versions, not environment values.

| Scope | Required reviewed values |
|---|---|
| Local backend | APP_ENV=local, AUTH_PROVIDER=local; loopback HOST, PORT8000; exact CORS origins; LOCAL_DB_PATH and separate private LOCAL_EVIDENCE_ROOT. COOKIE_SECURE=true when serving HTTPS. Local defaults require no AWS credentials |
| Tests | APP_ENV=test, isolated DB/evidence paths, generated accounts; worker invoked explicitly. Never point fixtures at development data |
| Cloud backend | APP_ENV=aws or production, AUTH_PROVIDER=cognito, COMPLAINT_PROVIDER=dynamodb, EVIDENCE_PROVIDER=s3, DEBUG=false; COGNITO_ISSUER, COGNITO_CLIENT_ID, COGNITO_DOMAIN, COGNITO_API_SCOPE=civiclens/access; exact HTTPS CORS_ORIGINS for production |
| Cloud references | COMPLAINTS_TABLE_NAME, INCIDENTS_TABLE_NAME, AUDIT_EVENTS_TABLE_NAME, EVIDENCE_BUCKET_NAME, WORKFLOW_TABLE_NAME, EVENT_BUS_NAME, TRIAGE_STATE_MACHINE_ARN; optional operational topic ARN only after explicit opt-in |
| Frontend local | VITE_AUTH_MODE=local, VITE_API_BASE_URL=/api; Vite proxy to local8000 |
| Frontend cloud | VITE_AUTH_MODE=aws, HTTPS API base; VITE_COGNITO_ISSUER/CLIENT_ID/DOMAIN/REDIRECT_URI/LOGOUT_URI matching reviewed Cognito/client/host. No browser AWS SDK administrative identity |
| CDK | stage, reviewed account/region, frontendOrigins JSON, callbackUrls and logoutUrls JSON. production placeholders are NOT real destinations. Local stage constructs zero AWS stacks |

MAX_API_REQUEST_BYTES defaults65536, bound16384–1048576. Image request/output caps
remain independently bounded. Matching/clustering/priority/assignment/analytics/
recurrence/fairness configuration is in backend examples and the release evaluation
manifest. Defaults remain review-only/manual allocation; no algorithm weights were
silently retuned in Phase13. ANALYTICS_TIMEZONE requires a real IANA zone (tzdata
installed on Windows); configured service rectangles are not verified municipal wards.

Cloud mode forbids local auth/storage fallback. Missing complaint table/bucket
causes clear factory startup failure; absent workflow configuration rejects relevant
business writes503. Some lazy cloud services fail only when invoked; this is a known
readiness issue, not complete eager production validation. Phase12 cloud binding is
absent even with every variable set. Supplying values does not make it deployable.

The Windows development install uses bounded pyproject dependencies, not a hash-pinned
Python lock; installed exact versions are captured in the ignored release manifest.
Node lockfiles are preserved; use `npm ci` only in a fresh/stopped workspace. Never
reinstall while Vite/watchers lock native Lightning CSS binaries or stop unrelated
Node/Codex processes. A separate Linux runtime lock/artifact is mandatory before cloud use.
