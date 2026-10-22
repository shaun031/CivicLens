# Phase 14 manual deployment runbook — DO NOT EXECUTE IN PHASE 13

**Current entry condition: BLOCKED.** No command in this document was executed
against AWS. Phase14 requires the human owner's explicit deployment authorization.
The following ordered procedure is a preparation artifact, not a runnable approval
or a workaround for the intentional CloudFormation deployment blocker.

## 0. Release hold / missing source prerequisites

Stop until all source blockers in [readiness](AWS_DEPLOYMENT_READINESS.md) are closed:
cloud domain/eligibility bindings and projection bootstrap; pinned/tested Linux
artifact integrated in CDK; real HTTPS frontend hosting; exact OAuth URLs and trusted
group provisioning; approved budget/data retention/recovery/monitoring. Re-run
`scripts/verify.ps1` after those changes. Do not merely delete the blocking assertion.
Record reviewer, source/dependency/artifact hashes and expected resource diff.

## Ordered manual procedure after approval

1. **Account:** owner controls the demonstration account; protect root with MFA,
   no root access keys. Record account ID, bill owner, shared workloads/limits and
   teardown date. Verify account access through approved short-lived CLI identity.
2. **Region:** choose a supported region deliberately (no region is assumed here),
   considering users, quotas, Cognito, runtime availability, privacy and prices.
3. **Permissions:** use reviewed deployment/bootstrap roles with just the required
   CloudFormation/CDK/IAM/service actions. Do not put deployer privileges in Lambda
   or the browser. Initial admin creation is a distinct trusted operator action.
4. **CLI validation:** only now run `aws --version`, approved SSO/login and
   `aws sts get-caller-identity --profile <approved-profile>`. Confirm expected
   account/role before any mutation. These live calls were not made in Phase13.
5. **CDK environment:** explicitly set reviewed account, region, stage,
   frontendOrigins, callbackUrls and logoutUrls; verify no example.invalid/loopback
   production callbacks or wildcard origins. Never print credentials to logs.
6. **Budget/alerts:** manually create owner-approved actual+forecast budgets and
   billing notifications; accept/verify recipient subscriptions. Alerts can lag;
   see [cost worksheet](AWS_COST_GUARDRAILS.md). No hard cap is implied.
7. **Resource/cost review:** approve exact synthesized resources, provisioned
  13RCU/13WCU baseline or deliberate alternative, requests/transitions/storage/
   transfer/hosting, retention, API throttles/concurrency and log settings.
8. **Bootstrap decision:** inspect whether the account/region already has the
   correct trusted bootstrap stack. Review roles/trust/KMS/S3 retention and costs;
   bootstrap is a live resource-creation action requiring separate approval.
   Do not blindly run `cdk bootstrap` against an unknown account.
9. **Synthesis/diff:** rerun offline tests first, inspect Linux asset hash/size and
   production template; after approval, review a live diff/change set for replacements,
   deletions, public policies or new billable services. Stop on unexpected changes.
10. **Deploy:** only a reviewed deployable artifact/template may use the owner's
    approved `cdk deploy`/CloudFormation change-set procedure, with rollback enabled
    and explicit account/region/profile. Current source has an unsatisfiable rule
    and cannot be deployed. Never use a broad unattended destroy/redeploy shortcut.
11. **DynamoDB:** record four tables/nine indexes or reviewed new inventory. Check
    encryption, capacity, deletion protection, RETAIN/PITR decision. Seed trusted
    departments/officers and build scoped source projections via approved bounded
    server tools. Verify strong canonical reads, transactions and GSI propagation.
12. **S3:** verify private/TLS/SSE/owner enforcement, no public GET or static website,
    generated namespace and scoped IAM. Decide versioning/backups/retention. Test
    bounded sanitized uploads, private retrieval, collision/uncertain cleanup.
13. **Cognito:** configure exact HTTPS OAuth URLs, code+PKCE public client/API scope,
    email verification, trusted CITIZEN assignment and separate OFFICER/ADMIN
    provisioning. Decide/enforce staff MFA. No self-selected privileged groups.
14. **API/Lambda:** inject non-secret resource references, validate production env,
    DEBUG=false/no local fallback, correct handler/runtime/architecture. Test JWT
    rejection/expiry/groups, JSON errors, multipart/base64 transport, CORS/HTTPS,
    memory/duration and safe correlation logging. Apply reviewed API abuse limits.
15. **Events:** verify dispatcher→EventBridge→SQS→consumer→SFN and durable
    receipts/outbox. Keep scheduler OFF until handler bindings/costs are validated;
    then enable only the approved bounded schedule. Confirm queue visibility,
    partial failures, DLQ, retries, lease recovery and no feedback loops.
16. **Frontend:** deploy the separately approved static hosting design, private
    origin/OAC if chosen, HTTPS and SPA fallback. Do not reuse the evidence bucket.
    Configure public VITE values only and test deep-link navigation on refresh.
17. **HTTPS/CORS/headers:** exact host origins at Gateway/backend/Cognito; no mixed
    content, arbitrary redirects or wildcard credentials. Verify HSTS/CSP/frame/
    referrer/cache policy at the actual frontend/edge, not just Vite development.
18. **Initial ADMIN:** trusted operator grants the verified named staff account
    approved ADMIN group. Document who approved it and verify public registration
    remains citizen-only. Officer role additionally needs active membership/coverage.
19. **Bounded smoke:** first health and one generated account per role. Stop on
   503/500 or any false empty-success projection; inspect safe logs and rollback
    rather than silently falling back to SQLite.
20. **Role tests:** anonymous/citizen/officer/admin allow/deny matrix; foreign
    complaint/photo/notification IDs, pagination/export, reassigned officer and
    verification eligibility. Use generated demo data, never real citizen samples.
21. **Full journey:** one photo complaint→durable event→candidate/canonical→
    priority→routing/assignment→start/progress→repair photo→citizen feedback→
    accountable ADMIN decision. Confirm membership/history/outbox/notifications,
    later recurrence remains a separate incident, reopen/rework preserves history.
22. **Notifications:** confirm in-app recipient privacy/dedup and mark-read.
    SNS remains OFF unless explicit approved subscriptions/eligibility/consent;
    external delivery is not implied by an in-app notification.
23. **Monitoring:** inspect Lambda errors/duration/throttles, table/GSI throttles,
    outbox age, queue backlog/DLQ, failed executions, projection freshness and
    retention. The prototype creates metric descriptors but no active alarms.
24. **Cost check:** inspect actual usage/billing after the bounded batch and daily
    during demonstration. Billing delays require headroom. No AWS load/stress test.
25. **Backup/rollback:** perform a small approved backup/restore rehearsal in an
    isolated cloud target before live citizen data. Record previous Lambda/frontend
    artifacts and compatible schema/event versions. Follow recovery below on failure.
26. **Demo completion:** stop new reports/dispatch/schedules under an approved
    maintenance window, drain/inspect work, export/backup data and obtain explicit
    retention/deletion decision. Review a proposed stack deletion/resource list,
    then run only owner-approved targeted cleanup. Confirm retained tables/bucket/
    logs/backups and provisioned capacity can still bill. Never automatically purge them.

## Rollback and recovery decisions

- Lambda/frontend regression: pause ingress/trigger changes if needed; redeploy the
  last signed/recorded compatible artifact. No alias-based rollback is currently
  provisioned; that mechanism must be designed/tested, not assumed present.
- Infrastructure failure: inspect CloudFormation events/change set and retained
  resources. Do not force-delete stateful resources to clear an error. Source-only
  offline synth does not prove stack update/rollback compatibility.
- Data corruption: quiesce writes, preserve affected tables/objects and event
  receipts; restore approved DynamoDB backup/PITR into NEW table names, repoint
  reviewed config after validation, and restore photo versions from the agreed
  backup. PITR and S3 versioning are currently OFF, so this plan is a blocker until
  a real protection policy/restore rehearsal exists.
- Partial event failure: inspect native DLQ and application workflow/audit, fix the
  root condition, then bounded explicitly approved redrive. Never empty queues or
  delete receipts/idempotency keys to hide failures. Old event-version compatibility
  must survive application rollback.
- Before any destructive cleanup, confirm exact account/region/resource IDs,
  backup/retention/owner authorization and affected data. Prepared command shape
  is `cdk destroy <reviewed-stack-id> --profile <approved-profile>` only after
  reviewing a current resource inventory; it was not executed and is NOT an
  instruction to delete retained data. Final evidence/data deletion requires a
  separate approved, auditable retention procedure and cost review.

Record actual smoke/role/lifecycle/restore outcomes and cost observations in Phase14;
do not populate the runbook with invented successful deployment results.
