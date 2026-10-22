# Phase11 integration plan

1. Reuse schema8 complaints/users, canonical incidents and membership audit, Phase8 priority sidecars
   and configuration, Phase9 assignment/membership/work history, and Phase10 SLA/outbox infrastructure.
2. Add analytics-owned revision/checkpoint/export-audit state and indexes only. Current local views
   read one consistent, bounded SQLite snapshot; never increment operational totals on delivery.
3. Validate municipality-zone date boundaries, combined operational filters, configured rectangular
   service areas and bounded grid queries independently of HTTP. Separate complaint/incident cohorts.
4. Pure calculators produce distributions, valid timing samples, current SLA outcomes, global officer
   workload and spatial cells. Missing/stale inputs remain explicit. Historic current-state reconstructions
   and progress-as-resolution are prohibited.
5. Reuse Phase10 successful-delivery observation for idempotent freshness checkpoints, with independent
   error isolation. Rebuild/reconcile only analytics-owned snapshots; source revisions fence replacement.
6. Add protected APIs, allowlisted bounded CSV exports with formula protection/audit, and React command
   center, department/officer, geographic, SLA/backlog and reporting screens with shared URL filters.
7. Prepare bounded versioned DynamoDB projection manifests in the existing operations table, conditional
   publication/invalidation and explicit unavailable states; no Scan or separate event infrastructure.
8. Verify synthetic correctness/security/concurrency/API/component/browser/integration scenarios, run
   disposable1000-report/500-incident benchmark and prior regressions, then update the A–Z handoff.
   No AWS service calls/deployment, normal-data reset, paid services or Phase12 implementation.
