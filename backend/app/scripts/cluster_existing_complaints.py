"""Bounded local singleton backfill and fresh clustering. Default mode is REVIEW_ONLY."""

from dataclasses import replace

from app.scripts.incident_cli import arguments, local_service, output


def main():
    parser = arguments(__doc__)
    parser.add_argument(
        "--mode", choices=("REVIEW_ONLY", "CONSERVATIVE_AUTO_LINK"), default="REVIEW_ONLY"
    )
    args = parser.parse_args()
    service = local_service(parser, args)
    service.config = replace(service.config, mode=args.mode)
    ids = service.repository.source_ids(args.after, args.limit)
    if args.dry_run:
        output(
            {
                "dryRun": True,
                "mode": args.mode,
                "complaintIds": ids,
                "unassigned": sum(
                    service.require_member(identity).complaint.incidentId is None
                    for identity in ids
                ),
                "nextAfter": ids[-1] if ids else args.after,
            }
        )
        return
    for identity in ids:
        incident = service.ensure_singleton(identity)
        service.matching.repository.enqueue(identity)
        matching = service.matching.process_one(identity)
        service.repository.enqueue(identity)
        result = service.process_one(identity)
        output(
            {
                "complaintId": identity,
                "initialIncidentId": incident["incidentId"],
                "matching": matching,
                "clustering": result,
                "resumeAfter": identity,
            }
        )
    output({"processed": len(ids), "mode": args.mode, "nextAfter": ids[-1] if ids else args.after})


if __name__ == "__main__":
    main()
