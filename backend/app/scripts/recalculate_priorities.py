"""Bounded local priority backfill/refresh. --dry-run opens existing SQLite read-only."""

import argparse
from uuid import UUID

from app.core.config import Settings
from app.scripts.incident_cli import arguments, local_service, output
from app.services.priority_service import build_priority_service


def main():
    parser = arguments(__doc__)
    parser.add_argument("--batch-size", dest="limit", type=int, default=argparse.SUPPRESS)
    parser.add_argument("--incident-id", type=UUID)
    parser.add_argument("--stale-only", action="store_true")
    args = parser.parse_args()
    incidents = local_service(parser, args)
    service = build_priority_service(Settings(), incidents)
    ids = (
        [str(args.incident_id)]
        if args.incident_id
        else service.repository.batch(args.after, args.limit)
    )
    completed, skipped, failed = 0, 0, []
    output(
        {"configVersion": service.config.version, "dryRun": args.dry_run, "batchSize": args.limit}
    )
    for identity in ids:
        try:
            identity = service.canonical(identity)
            snapshot = service.repository.snapshot(identity)
            if args.stale_only and not service.stale_reasons(snapshot):
                skipped += 1
                continue
            result = service.calculate_snapshot(snapshot, dry_run=args.dry_run)
            completed += 1
            output({"incidentId": identity, "result": result, "resumeAfter": identity})
        except Exception as error:
            failed.append({"incidentId": identity, "errorCategory": type(error).__name__})
            output(
                {"incidentId": identity, "state": "FAILED", "errorCategory": type(error).__name__}
            )
    output(
        {
            "processed": completed,
            "skipped": skipped,
            "failures": failed,
            "nextAfter": ids[-1] if ids else args.after,
            "note": "Retry failed IDs or restart a stale-only sweep; no records deleted",
        }
    )
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
