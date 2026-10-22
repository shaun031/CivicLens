# Authentication — Phase 2

Local authentication is functional without AWS. Cognito infrastructure and browser/backend adapters are implemented for later cloud verification. No Cognito service, user, email, or deployment was created during Phase 2.

## Modes and common identity

`APP_ENV=local` selects `AUTH_PROVIDER=local`. Tests may use the isolated `test` environment. `APP_ENV=aws` requires Cognito configuration and `AUTH_PROVIDER=cognito`; legacy `demo`/`production` environment names also require Cognito. CDK sets `APP_ENV=aws` and a separate `DEPLOYMENT_STAGE`. Missing cloud configuration, a local provider in a cloud environment, bad tokens, or unavailable identity services never falls back to local credentials.

Both providers produce a typed Principal containing user ID, normalized email, display name, effective role, provider, authentication status, and account status. One backend permission matrix governs both providers. Headers/body fields supplied by the browser never establish identity or role. The UI gets its role from `/api/auth/me` or the authenticated login response.

## Local accounts and passwords

SQLite resides at `backend/data/civiclens_local.db` by default. The entire data directory, including reset outbox files, is ignored by Git and excluded from Lambda assets. Users use UUID IDs, normalized case-insensitive unique email, UTC timestamps, active/verified flags, and a constrained role enum. Public registration always assigns CITIZEN and rejects extra privilege fields. Local registration marks email verified for development only; it sends no email and does not claim ownership verification. Cognito requires actual email verification.

Passwords use Argon2id via `argon2-cffi`, independent random salts, and maintained defaults. Login rehashes when parameters change. Policy accepts Unicode and passphrases of 12–128 characters, rejects nulls, repeated-character/predictable values, and requires four distinct characters. It does not invent a numeric strength score or force arbitrary character classes. Passwords are never normalized silently, logged, stored in plaintext, or returned. Validation responses strip input values, including password/reset-token fields.

The database initialization command creates schema version 1 idempotently, preserves accounts, and rejects unknown future versions. Startup also initializes local tables safely. Later schema changes must add explicit migrations; initialization is not a destructive reset.

## Sessions, CORS, and CSRF

Login verifies password and active/verified state. Unknown users and incorrect/inactive/unverified accounts return the same generic 401 message; a dummy Argon2 verification reduces account-existence timing differences. Successful login generates a fresh 256-bit random token, invalidates the presented old session, and stores only its SHA-256 digest. SHA-256 is used only for high-entropy tokens, not passwords.

The `civiclens_session` cookie is HttpOnly, SameSite=Lax, scoped to `/api`, expires after eight hours by default, and is Secure when HTTPS or `COOKIE_SECURE=true` is used. Plain HTTP authentication accepts loopback hosts only. Logout deletes the server session and cookie; reset revokes all of the account's sessions. Each protected request checks expiry and current account flags/role from SQLite.

Every state-changing local request, including register/login/recovery/logout, requires an exact configured `Origin`. Missing, null, wildcard, and untrusted origins fail. This strict Origin strategy plus SameSite cookies and restricted credentialed CORS prevents browser CSRF; scripts must explicitly supply a trusted Origin. Swagger can display all schemas, but authentication writes from the backend origin are intentionally rejected unless that origin is explicitly trusted. Use the frontend for normal flows.

SQLite fixed-window rate limits persist across local server restarts: login allows five attempts per email/IP and twenty per IP within fifteen minutes; successful login clears the email/IP bucket. Registration allows eight requests per IP per window. Recovery/reset allow five each per IP. 429 includes Retry-After. The application does not trust a body-supplied IP. These controls target local development; distributed cloud abuse controls require Phase 14 review.

## Recovery

`POST /api/auth/forgot-password` returns the same 202 response for eligible and unknown accounts. A known active account gets a random, fifteen-minute reset token; only its digest is in the reset table. A private development outbox file contains a link with the token in a URL fragment. There is no HTTP endpoint for retrieving the outbox and no real email is sent.

The trusted local project operator retrieves the link from the terminal:

```powershell
Set-Location D:\CivicLens\backend
.venv\Scripts\python.exe -m app.scripts.local_auth outbox
```

Treat outbox files/links as secrets. Do not publish, screenshot, commit, or copy them into ordinary logs. Restrict the data folder to trusted Windows users using normal account/folder permissions. The browser removes the fragment from its address bar after capturing it. Reset is transactional, short-lived, single-use, invalidates sibling reset tokens and all sessions, and requires a new login. Stale outbox messages do not make consumed/expired tokens valid.

## Cognito mode

`oidc-client-ts` drives authorization-code flow with S256 PKCE and OAuth state validation. No client secret is embedded. Access/ID/refresh tokens remain in memory; sessionStorage stores only transient OAuth state/PKCE information. Local credentials and sessions are never put in localStorage. A hard AWS-mode page reload clears in-memory tokens and requires returning through Cognito sign-in/SSO; that flow needs real browser verification in Phase 14. Local cookie sessions restore automatically on refresh.

Only access tokens are sent to APIs. PyJWT verifies RS256 signatures against a lazy five-minute JWKS cache, handles key rotation, and verifies issuer, exp, iat, optional nbf, token_use=access, client_id, subject, and the custom API scope. Cognito access tokens need not contain `aud`, so client validation uses `client_id`. Groups are read only after cryptographic verification. Unknown/missing groups fail closed with 403 until trusted provisioning completes.

The verified token calls Cognito userInfo for email/name; its subject must match the verified access-token subject and its email must be verified. This avoids assuming access tokens contain email/name. Profile PATCH changes only `name` through Cognito's self-service UpdateUserAttributes API using that user's access token; no IAM credentials or arbitrary target user ID are accepted. The reserved `aws.cognito.signin.user.admin` scope enables that self-service action, not application ADMIN membership. [AWS scopes documentation](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-define-resource-servers.html)

AWS registration and password recovery use Cognito's hosted UI, not local-password API routes. Logout revokes tokens when reachable, clears in-memory state, and visits Cognito logout. Offline JWT verification cannot detect every revocation instantly; already-issued access tokens can remain usable until expiry. Fifteen-minute access-token lifetime bounds that exposure. Validate actual revocation/session behavior before deployment.

All identity API/profile/portal responses use `Cache-Control: no-store`. API responses set no-referrer/nosniff headers. No complaint, incident, or authentication-bypass API exists.
