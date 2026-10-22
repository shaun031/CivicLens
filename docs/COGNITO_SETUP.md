# Cognito preparation — not deployed

Phase 2 defines Cognito locally in CDK. No live pool/client/domain/groups/users were created. No Cognito request occurs in local mode or local tests. Deployment stays blocked until Phase 14.

## Defined resources

- One retained User Pool: case-insensitive email sign-in, verified-email recovery, email auto-verification, self-registration, required email/name, twelve-character password minimum. Email is immutable after registration; name is mutable.
- Explicit Lite tier and classic hosted UI. SMS, MFA, premium managed-login branding, advanced threat protection, and paid optional security features are not enabled by default. Review privileged-account MFA requirements before exposing an actual deployment.
- A browser App Client without a secret; authorization-code grant only, no implicit/client-credentials/password grants. Access/ID tokens last fifteen minutes, refresh token one day; revocation and user-existence protection are enabled.
- Read attributes are email, email_verified, name; writable attributes are email (initial registration) and name. There are no writable role/group/verification attributes.
- A resource server `civiclens` and API scope `civiclens/access`. Additional scopes openid/email/profile support the safe profile; aws.cognito.signin.user.admin supports self-service profile updates and does not grant the application ADMIN role.
- Exactly CITIZEN, OFFICER, ADMIN groups. No users, group assignments, or new Lambda triggers are created.
- A Cognito domain prefix derived from project/stage/account/region, using CloudFormation tokens during offline synthesis.

## URLs and public configuration

CDK context supports `callbackUrls` and `logoutUrls` JSON arrays. Demo defaults are `http://localhost:5173/auth/callback` and `http://localhost:5173/`. Production defaults use `https://frontend.example.invalid` solely to keep credential-free synthesis possible. Wildcards/fragments/credentials are rejected; production requires HTTPS. The hard deployment rule and readiness failure prevent these placeholders being deployed accidentally. Phase 14 must replace placeholders, validate exact frontend origins and callbacks, and confirm domain availability.

Outputs include CognitoUserPoolId, CognitoClientId, CognitoIssuer, CognitoDomainUrl, FrontendCallbackUrls, and FrontendLogoutUrls, in addition to Phase 1 outputs. They are public configuration references, not usable live IDs before deployment. Populate frontend VITE_AUTH_MODE=aws plus VITE_COGNITO_ISSUER, CLIENT_ID, DOMAIN, REDIRECT_URI, and LOGOUT_URI from reviewed outputs. Never put a client secret or AWS credentials in Vite variables.

The backend uses APP_ENV=aws, AUTH_PROVIDER=cognito, DEBUG=false, COGNITO_ISSUER, COGNITO_CLIENT_ID, COGNITO_DOMAIN, COGNITO_API_SCOPE, resource references, and restricted CORS origins. CDK injects them through actual resource references. The local SQLite provider is absent in AWS mode.

## Code flow and authorization

The maintained OIDC client generates state and PKCE verifier/challenge, redirects to the configured Cognito authorize endpoint, verifies the callback, and exchanges the code using PKCE. API requests carry the access token, never the ID token. [AWS supports S256 PKCE for this flow](https://docs.aws.amazon.com/cognito/latest/developerguide/authorization-endpoint.html).

HTTP API uses a JWT authorizer with the User Pool issuer and App Client audience. GET /api/health remains public. GET /api/auth/me, PATCH /api/profile, and the three GET portal routes require JWT plus civiclens/access. Requiring a custom access-token scope rejects ordinary ID tokens at the gateway. There is no catch-all route or local-password route in the cloud API.

Backend verification remains mandatory even behind the gateway: verify signature/issuer/time/client/token_use/scope and use verified groups for RBAC. API Gateway does not enforce application ADMIN/OFFICER membership by itself. The Lambda role still has only scoped logging permissions; Cognito self-service calls use the verified access token, not broad IAM grants.

## Citizen assignment and deployment prerequisites

Self-registration does not automatically join CITIZEN. Before deployment, implement or approve a trusted provisioning process: accept a confirmed subject from a trusted control-plane event/operator, verify email/account state and idempotency, add only CITIZEN membership, and audit the decision. Privileged groups require separate reviewed approval. A future post-confirmation trigger needs its own narrow AdminAddUserToGroup permission and tests; Phase 2 deliberately adds none. Pending group assignment results in 403, not privileged or implicit access.

Phase 14 must verify real code/PKCE redirects, callback/logout origins, email verification/recovery delivery and quotas, group assignment, JWT/JWKS rotation, revocation/refresh behavior, self-service profile updates, audience/scope enforcement, CORS, browser refresh/SSO behavior, and account/region costs. Linux packaging remains incomplete: add Argon2/cryptography/PyJWT/email-validation runtime dependencies to the future pinned package, exclude local databases/outboxes, and run Linux import/runtime verification. Synthesis and mocked tests do not prove cloud operation.
