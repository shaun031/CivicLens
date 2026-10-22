# Known risks — Phase 13, 2026-10-21

| ID / severity | Risk | Mitigation / owner gate |
|---|---|---|
| B1 BLOCKER | Phase12 AWS domain binding and trusted source projections/bootstrap incomplete | Implement server-owned eligibility/plans and end-to-end cloud parity; preserve fail503 and no local fallback |
| B2 BLOCKER | Source-only Lambda asset; no pinned Linux-native dependency/package/import/size evidence | Reviewed Linux CI runtime lock, hashes, import/binary/Mangum tests and cold-start sizing before deploy |
| B3 BLOCKER | No frontend hosting or real HTTPS/OAuth/provisioning configuration | Choose/implement approved host, exact callbacks, trusted citizen/staff groups and staff MFA policy |
| B4 BLOCKER for real data | PITR/S3 versioning OFF, cloud restore policy/rehearsal absent | Approve retention/encryption/backups and new-target restore, not blanket retention-as-backup claims |
| W1 High operational risk if exposed | Prototype1RCU/1WCU per table/index, API has no dedicated concurrency cap/throttle; native matching may exceed15s/256MB | Live bounded sizing/cost controls and API abuse review; do not publicly deploy these defaults |
| W2 Medium | Review-only default needed: conservative clustering still8 false-positive pairs in46-report synthetic split; recurrence4 false suggestions in48 pairs | Keep human physical-identity review, no auto grouping different repair cycles, preserve reports/audit |
| W3 Medium | Synthetic/template labels, perfect small matching split and bootstrap interval are not field validation; image-only baseline poor | No probability/quality guarantees, separate real labelled retrieval/viewpoint/asset dataset and independent expert review |
| W4 Medium | Fairness is descriptive/unadjusted; sparse/missing records, different severity/capacity/reporting access | Show n/missing/sufficiency and mix; no low-reporting-is-well-served or causal/protected-class claims |
| W5 Medium | One account is not necessarily one person; noisy feedback and officer claims do not establish physical quality | Immutable responses, current eligibility, explicit accountable ADMIN review, no majority closure |
| W6 Medium | Windows filesystem ACLs/operator, private reset outbox and local backups require trusted-machine controls | Restricted account/NTFS ACL/disk encryption; no public static mount; separate encrypted config backup |
| W7 Medium | Backend coverage below universal90% target; frontend coverage provider not installed; limited accessibility/state combinations | Report actual statement/branch metrics; target uncovered high-risk branches, preserve meaningful browser and interaction checks |
| W8 Medium | No independent live AWS integration/IAM/GSI/cold-start/transport/billing validation | Explicit Phase14 bounded smoke, role/data/payload/recovery/cost gates, not synth-as-deployment proof |
| W9 Medium | 444 CloudFormation resources,56 remaining before500; exact resource/policy safety assertions must evolve with reviewed hosting changes | No blind extra services; review resource budget/diff and policy allowlist after additions |
| W10 Low/medium | Uncertain evidence commit can leave orphan files; backups intentionally copy only referenced files | Inspect read-only audit; preserve uncertain objects pending operator review, never auto-delete |
| W11 Low | Starlette/httpx and Mangum/asyncio deprecations,84 CDK feature-flag notice and NO_COLOR warnings remain visible | Compatibility tested current versions; planned reviewed upgrade, no warnings suppressed. Owned SQLite handle leak fixed and strict-tested |
| W12 Medium | No Git repository/history in supplied folder; Python bounded requirements not a reproducible hash lock | Preserve workspace, create source manifest; owner-managed Git/backup and pinned deployment lock before release |

No unresolved identified critical/high application exploit is being accepted for
public deployment. The operational/cloud blockers mean overall **BLOCKED** regardless
of passing local tests. Currency costs and500/1000-workflow capacity, exhaustive
screen-reader accessibility and independent field labels are NOT_VERIFIED, not zero.
