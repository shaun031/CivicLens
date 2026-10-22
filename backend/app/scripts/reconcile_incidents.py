"""Read-only by default; --repair performs bounded audited non-destructive corrections."""

from app.scripts.incident_cli import arguments, local_service, output
from app.services.incident_reconciliation import reconcile


def main():
    parser = arguments(__doc__)
    parser.add_argument("--repair", action="store_true")
    parser.add_argument("--incident-after", default="")
    parser.add_argument("--candidate-after", default="")
    parser.add_argument("--event-after", default="")
    args = parser.parse_args()
    if args.repair and args.dry_run:
        parser.error("Choose dry-run OR explicit repair, not both")
    if not args.repair:
        args.dry_run = True
    service = local_service(parser, args)
    output(
        reconcile(
            service,
            args.limit,
            args.after,
            args.repair,
            args.incident_after,
            args.candidate_after,
            args.event_after,
        )
    )


if __name__ == "__main__":
    main()
