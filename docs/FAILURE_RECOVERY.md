# Failure recovery and safe replay

Local outbox and queue claims use BEGIN IMMEDIATE, ownership tokens and120-second leases. Cloud
conditional revisions fence claims and use600-second execution leases. A killed process leaves durable
RUNNING state, not lost work; a later worker claims expired work. Completed steps/receipts remain.
Matching and clustering have their own durable leases and may defer workflow recovery until they expire.

Transient failures retry with exponential delays (2,4,8,16 seconds in the initial policy; maximum300).
Five message attempts maximum. Validation, unsupported version and invalid domain transitions are
permanent. Store only safe categories, never raw exception text, descriptions, tokens or private images.
Failure of a notification step cannot undo a stored complaint or completed matching/clustering.
Do not retry whole domain transactions by splitting membership operations into smaller partial commits.

After permanent failure/exhaustion, mark the message DEAD, record failed execution/stage and emit a
deduplicated administrator review event. Unrelated messages continue. ADMIN monitoring displays
safe IDs/category/count/timestamps, not raw editable envelopes. Redrive/acknowledge requires a reason,
confirmation and durable operation UUID. Same request retry does not consume another redrive.
Maximum three redrives; permanent invalid events and dispatch-schema failures require source repair
and cannot be blindly replayed. Acknowledgement preserves the failure record, it does not delete it.

Safe procedure: inspect the workflow and category; correct configuration/eligibility through authorized
domain controls; refresh current versions; request one eligible retry; inspect resulting stage history.
Do not fabricate a valid event around arbitrary private payload or clear idempotency tables.
Native AWS SQS DLQs catch malformed SQS bodies and unhandled invocation failures; operations-table
dead letters capture known application failures. EventBridge target-exhaustion also uses the matching
queue's14-day DLQ. Native DLQ operational redrive remains an explicitly reviewed AWS action in Phase14,
not a hidden cloud call from this local dashboard.

Reliability is effectively-once business effects under at-least-once delivery, not exactly-once transport.
Existing domain version guards, deterministic singleton/candidate/workflow IDs, operation receipts,
notification unique keys and escalation receipts are reused. No global process mutex or in-memory set
is the durability mechanism. Cloud receipt+ack and escalation+event use bounded transactions.

Offline tests cover rollback, enqueue/dispatch acceptance, concurrent claim, stale lease recovery,
interrupted triage, retry exhaustion/redrive, notification ownership/dedup, SLA rerun/reopen/exclusions,
SDK partial failures and stage fixtures. Integration kills a real foreground worker, expires only its
test leases, restarts it and proves one report/incident/received notification with six completed stages.
The lease-clock advancement is an explicit test simulation, not a claim of waiting120seconds.
See PHASE_PROGRESS for actual final command results and limitations; live AWS failure semantics have
not been tested or deployed.
