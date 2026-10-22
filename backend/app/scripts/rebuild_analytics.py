"""Local-only, restart-safe replacement of analytics-owned derived snapshots."""

import argparse
import json
from datetime import date

from app.analytics.filters import AnalyticsFilters
from app.core.config import Settings
from app.main import create_app
from app.models.incident import IncidentError
from app.repositories.analytics_repository import SQLiteAnalytics
from app.scripts.incident_cli import ReadOnlyStore
from app.services.analytics_service import VIEWS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--diagnose", action="store_true")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--aggregation", choices=VIEWS, action="append")
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--batch-size", type=int, choices=range(1, 51), default=25, metavar="1..50")
    parser.add_argument("--bounds", type=float, nargs=4, metavar=("SOUTH", "WEST", "NORTH", "EAST"))
    args = parser.parse_args()
    settings = Settings()
    if settings.complaint_provider != "sqlite":
        parser.error("Local-only command; no AWS service may be contacted")
    if not settings.local_db_path.is_file():
        parser.error("Start/migrate local backend first; no database was created")
    app = create_app(settings)
    readonly = args.dry_run or args.diagnose
    if readonly:
        store = ReadOnlyStore(settings.local_db_path)
        with store.connection() as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='analytics_meta'").fetchone():
                parser.error("Initialize Phase11 analytics first; diagnostic made no changes")
        app.state.analytics_service.repository = SQLiteAnalytics(store, settings)
    else:
        app.state.auth_service.store.initialize()
    try:
        bounds = (
            dict(zip(("south", "west", "north", "east"), args.bounds, strict=True))
            if args.bounds
            else {}
        )
        filters = AnalyticsFilters(start=args.start, end=args.end, limit=args.batch_size, **bounds)
        views = args.aggregation or [view for view in VIEWS if view != "hotspots" or args.bounds]
        print(
            json.dumps(
                {
                    "phase": "begin",
                    "aggregations": views,
                    "sourceProcessing": "bounded source snapshot",
                    "detailPageLimit": args.batch_size,
                    "dryRun": readonly,
                }
            ),
            flush=True,
        )
        for view in views:
            result = app.state.analytics_service.rebuild(filters, [view], readonly)
            print(json.dumps(result, allow_nan=False), flush=True)
    except (ValueError, IncidentError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
