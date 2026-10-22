# AWS cost scenarios and guardrails — no resources created

Phase13 uses local CPU/storage and offline synthesis. It makes **no zero-bill or
Free Tier/credit entitlement guarantee**. Region/account/pricing plan are not chosen
here, so currency totals are NOT_VERIFIED. Confirm current service unit rates and
regional entitlements in Phase14 before permission to deploy. The estimates below
are workload units and formulas, not fabricated prices or measured cloud traffic.

## Scenario worksheet

Let H=hours retained, R/W=region-specific RCU/WCU-hour rates, L=request+GB-second
Lambda costs, T=Standard transition rate, E/Q=bus/queue request rates, S=storage,
A=API requests, C=Cognito active users, N=SNS messages, G=logs/transfer/HTTPS hosting.
All totals add durable Dynamo/S3/log storage and internet egress, including idle days.

| Scenario / assumptions | Estimate to price before deployment |
|---|---|
| Idle,720h, no user reports; scheduler remains OFF | Provisioned capacity base **13×720×(R+W)** plus existing table/object/log storage, any empty queue polling and configured host/certificate/DNS charges. Zero reports is not zero cost |
| Small demo:100 reports/month,20 active users,100 triage runs,200 sanitized photos at200KB/photo,200 authorized photo views; illustrative20 downstream events/report | About40MB new complaint evidence before repair/feedback/retention;100 triage×assumed12 transitions=1200T plus retry/review paths;2000E and queue delivery/receive/delete/poll requests; API assume2000A. Add actual transactional item/index reads/writes (not one write/report), C=20 and measured Lambda duration/memory L |
| Moderate test:1000 reports/month,100 active users,20000 API calls,2000photos,4000 photo views,20000 downstream events | About400MB complaint evidence plus repair/feedback; illustrative12000 transitions plus retries,20000E and corresponding Q,20000A, C=100, measured L, storage/index/log and transfer.1WCU may throttle far below this burst; do not treat this as capacity validation |
| Unexpected loop:10000 extra workflows/day | At illustrative12 transitions,120000T/day plus consumer/step L, bus/queue requests and logs. Attempts, target retries/native redelivery and manual redrives multiply work. Boundaries help recovery, not a hard dollar cap. Halt source/schedule/consumers under operator control and investigate, preserving queued work |

SNS N=0 unless an operator enables approved subscriptions; external email/SMS was
not activated. Cognito email delivery, frontend S3/CloudFront or other HTTPS hosting,
requests/cache misses, DNS/certificates where applicable and transfer must be priced
separately: hosting is not implemented and must not be omitted from the worksheet.
PITR/versioning/backup choices can add charges; RETAIN means stack deletion does not
stop storage/capacity billing. API15s/256MB, workers512MB are unprofiled, not measured rates.

## Required manual safeguards before Phase14

1. Select account/region and bill owner; inspect existing commitments/credits without
   assuming entitlements. Price every row in AWS Pricing Calculator/current pages.
2. Create a small approved monthly AWS Budget and actual/forecast alerts (for example
   50/80/100% of an owner-chosen amount); verify recipient subscription delivery.
   Budgets alerts are delayed and do **not** cap spend. No Budget was created here.
3. Tag resources `Project=CivicLens`, environment, owner and expiry; review retained
   resources after demo. Keep credentials outside code/Vite/logs.
4. Maintain worker concurrency4/2/1, choose an API limit and API Gateway throttles
   explicitly; review account-wide Lambda concurrency interactions. No provisioned
   concurrency, NAT, EC2, RDS or paid analytics/ML service is introduced.
5. Keep seven-day log retention and safe payload-free logging. Metrics descriptors
   alone create no active alarm: choose failure/backlog/throttle/billing monitoring
   and owner escalation before exposure.
6. Hourly source rule is DISABLED. Approve actual outbox dispatcher/SLA schedule
   frequencies and bounded batch sizes; do not turn schedules on to bypass missing bindings.
7. Keep SNS OFF/unsubscribed until opt-in and spend review. No uncontrolled citizen SMS.
8. Do not run stress benchmarks in AWS. Use a bounded smoke-test script/count and
   inspect invocation/state-transition/queue/backlog/bytes after each small batch.
9. Record before/after inventory and daily billing during demo; stop new ingress or
   disable triggering rules/mappings if anomalous, preserving data and pending events.
10. Cleanup is an explicitly approved Phase14 procedure: inspect backups and retained
    resources first. Deleting a stack is not the same as deleting or preserving all data.

Official sources: [Budgets behavior](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html),
[Lambda pricing](https://aws.amazon.com/lambda/pricing/), [DynamoDB](https://aws.amazon.com/dynamodb/pricing/),
[S3](https://aws.amazon.com/s3/pricing/), [API Gateway](https://aws.amazon.com/api-gateway/pricing/),
[Cognito](https://aws.amazon.com/cognito/pricing/), [EventBridge](https://aws.amazon.com/eventbridge/pricing/),
[SQS](https://aws.amazon.com/sqs/pricing/), [Step Functions](https://aws.amazon.com/step-functions/pricing/),
[SNS](https://aws.amazon.com/sns/pricing/), [CloudWatch](https://aws.amazon.com/cloudwatch/pricing/),
[CloudFront](https://aws.amazon.com/cloudfront/pricing/). Rates/region/account checks
remain Phase14 tasks; no billing API was contacted.
