"""Explicit local worker; never spawns a detached process or contacts AWS."""

import argparse
import json
import time

from app.core.config import get_settings
from app.main import create_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--continuous", action="store_true")
    parser.add_argument(
        "--batch-size", type=int, default=20, choices=range(1, 101), metavar="1..100"
    )
    parser.add_argument(
        "--max-batches", type=int, default=20, choices=range(1, 101), metavar="1..100"
    )
    args = parser.parse_args()
    settings = get_settings()
    if settings.complaint_provider != "sqlite":
        parser.error("This command is local-only; no AWS transport is allowed")
    app = create_app(settings)
    app.state.auth_service.store.initialize()
    try:
        batches = 0
        while True:
            result = app.state.workflow_service.batch(args.batch_size)
            result["legacyJobsProcessed"] = sum(
                bool(service.process_one())
                for service in (
                    app.state.duplicate_detection_service,
                    app.state.incident_service,
                    app.state.priority_service,
                    app.state.work_service,
                )
            )
            print(json.dumps(result))
            batches += 1
            if args.once or (
                not args.continuous and (not any(result.values()) or batches >= args.max_batches)
            ):
                break
            if args.continuous and not any(result.values()):
                time.sleep(2)
    except KeyboardInterrupt:
        print("Worker stopped; unacknowledged leases recover on a subsequent run.")


if __name__ == "__main__":
    main()
