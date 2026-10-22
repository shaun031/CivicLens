# Cost and Cloud Safety

The project targets a minimal or zero-cost learning/development footprint, but no AWS service is promised to remain free. Free-tier eligibility varies by account age, region, service, usage, and current AWS terms. Promotional credits are a finite account balance; they are not an ongoing free allowance.

## Guardrails

- Phases 0–13 use local development and tests only.
- Phase 14 is the first deployment phase and requires explicit, manual user initiation.
- Project scripts never run `aws configure`, `cdk bootstrap`, `cdk deploy`, or resource-creating SDK/API calls.
- Before deployment, verify current prices and free-tier eligibility in the selected account and region.
- Review the synthesized template and estimated resource behavior before approval.
- Apply least privilege, encryption, retention limits, log controls, budgets, and billing alarms as appropriate.
- Avoid unbounded concurrency, storage, logs, workflow transitions, NAT gateways, and high-volume notification paths.

## Planned cleanup

Phase 1 defines 7 RCU/7 WCU across three tables and four indexes per stage; all tables, the evidence bucket, and logs use RETAIN. No cleanup is automatic. An explicit CloudFormation rule and a failing deployment-readiness check block use of the incomplete Lambda asset. See [AWS_COST_ESTIMATE.md](AWS_COST_ESTIMATE.md) for the service inventory, capacity math, and pricing review, and [INFRASTRUCTURE.md](INFRASTRUCTURE.md) for deployment blockers.

Document every deployed stack and non-stack retained resource. Test deletion in a non-production environment, empty/versioned storage where required, run `cdk destroy` only after explicit approval, and verify through billing/resource inventory that resources and recurring charges are gone. Retained evidence or backups require a named owner and expiry policy.

