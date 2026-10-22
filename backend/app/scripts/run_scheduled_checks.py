import argparse
import json

from app.core.config import get_settings
from app.main import create_app
from app.services.sla_service import scheduled_checks


def main():
    parser = argparse.ArgumentParser(
        description="Bounded local priority and demonstration SLA checks"
    )
    parser.add_argument("--once", action="store_true", help="One bounded sweep (default)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--batch-size", type=int, default=20, choices=range(1, 101), metavar="1..100"
    )
    args = parser.parse_args()
    settings = get_settings()
    if settings.complaint_provider != "sqlite":
        parser.error("Local-only command; no AWS transport is allowed")
    if args.dry_run:
        # Do not initialize/migrate or create a DB for a read-only preview.
        from app.repositories.event_repository import SQLiteEvents
        from app.scripts.incident_cli import ReadOnlyStore
        from app.services.sla_service import SQLiteSLA

        if not settings.local_db_path.is_file():
            parser.error("Initialize/migrate the local backend first; dry-run created no database")
        with ReadOnlyStore(settings.local_db_path).connection() as db:
            if db.execute("PRAGMA user_version").fetchone()[0] != 8:
                parser.error("Initialize/migrate to schema8 first; dry-run made no changes")
        app = create_app(settings)
        events = SQLiteEvents(ReadOnlyStore(settings.local_db_path))
        sla = SQLiteSLA(events, app.state.priority_service)
        print(json.dumps(scheduled_checks(app.state.workflow_service, sla, args.batch_size, True)))
    else:
        app = create_app(settings)
        app.state.auth_service.store.initialize()
        print(
            json.dumps(
                scheduled_checks(app.state.workflow_service, app.state.sla_service, args.batch_size)
            )
        )


if __name__ == "__main__":
    main()
