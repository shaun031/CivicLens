# Local backup, migration and rollback guide

Phase13 never reset/migrated/restored over the developer DB. New diagnostics are
aggregate/read-only; backup tests write only disposable fixtures. Schema remains8
with additive Phase8–12 extensions. No Phase13 table/index rebuild or domain data
migration is needed; HTTP limits/headers/labels apply on normal process restart.

## Before an operator-run local migration or backup

1. Announce maintenance; stop this project's backend/worker/scheduled tasks and
   frontend submissions. Do not kill unrelated processes. Explicit `--quiesced`
   acknowledges this; the tool cannot prove no other writer exists.
2. Identify actual DB and private evidence roots from your reviewed local config
   without printing secrets. Do not assume the examples below match custom paths.
3. Choose a **new**, access-restricted backup directory outside evidence and the
   live data directory. The helper refuses overwriting an existing destination.
4. From `D:\CivicLens\backend`, examples (adapt paths, do not run blindly):

```powershell
.\.venv\Scripts\python.exe -m app.scripts.audit_local_data --database 'D:\CivicLens\backend\data\civiclens_local.db'
.\.venv\Scripts\python.exe -m app.scripts.backup_local create --database 'D:\CivicLens\backend\data\civiclens_local.db' --evidence-root 'D:\CivicLens\backend\data\evidence' --destination 'D:\CivicLens-Backups\approved-new-timestamp' --quiesced
.\.venv\Scripts\python.exe -m app.scripts.backup_local verify 'D:\CivicLens-Backups\approved-new-timestamp'
```

The helper uses SQLite's online backup API, then copies only referenced complaint/
repair/feedback objects, records SHA256 per object/DB, checks integrity/FKs and
verifies the manifest. On failure an incomplete directory may remain deliberately;
absence of a valid manifest/verification is failure, never successful backup.
No data deletion or auto-quarantine occurs. Orphans need separate preservation/
review; private reset outbox and environment secrets are deliberately not copied.

The DB contains password/session hashes and private text. Protect backups with
reviewed NTFS ACLs/encryption and access retention, not just Unix mode bits. Securely
store an encrypted copy of required environment configuration separately; never
paste its values into reports or source. Preserve the source release manifest and
app/runtime versions alongside backups. Do not overwrite older backups.

## Restore rehearsal / recovery

Restore only into a **new** directory: verify hashes, point an isolated test app at
`database.sqlite3` and the backup `evidence` folder, check reports/ownership/history/
repair responses/foreign keys and authenticated photo access. The unit restoration
test covers all three photo kinds and rejects corruption. A real user-data restore
was not performed. Do not expose a restored copy of real citizen data publicly.

For actual recovery, stop writers; retain the damaged originals; validate a restored
copy and backup; then make an explicitly reviewed config-path switch. The helper
does not implement destructive in-place restore. Rollback app code only to a version
compatible with schema8 additive extensions and v1 events; never downgrade by
dropping tables/columns or truncating receipts/audits. Pending outbox/queue leases
can be recovered with the existing bounded worker/redrive workflow.

Cloud backup/retention/rollback is separately gated in [deployment runbook](AWS_DEPLOYMENT_RUNBOOK.md).
RETAIN is not a backup; current PITR and bucket versioning are OFF and must be an
explicit owner decision before live data. No cloud backup was created in this phase.
