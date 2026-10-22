"""Bounded resumable local historical recheck. Explicit opt-in; never accesses AWS."""

import argparse
import json
from contextlib import closing

from app.algorithms.duplicate_detection.config import MatchingConfig
from app.algorithms.duplicate_detection.text_similarity import TEXT_ENGINE
from app.core.config import Settings
from app.repositories.auth_store import AuthStore
from app.services.complaint_factory import build_complaint_service
from app.services.duplicate_detection_service import build_duplicate_service


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument(
        "--after", default="", help="Last printed complaint UUID; resume after this key"
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only-outdated", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.limit <= 500:
        parser.error("limit must be 1–500")
    settings = Settings()
    if settings.app_env not in ("local", "test"):
        parser.error("Historical CLI is local-only; no cloud writes are allowed")
    store = AuthStore(settings.local_db_path)
    if not store.path.exists():
        parser.error("Database does not exist; start the local application first")
    if args.dry_run:
        # Read-only: even an old schema is not migrated by a dry run.
        import sqlite3

        with closing(sqlite3.connect(f"{store.path.resolve().as_uri()}?mode=ro", uri=True)) as db:
            rows = db.execute(
                "SELECT complaint_id FROM complaints WHERE complaint_id>? "
                "ORDER BY complaint_id LIMIT ?",
                (args.after, args.limit),
            ).fetchall()
        print(
            json.dumps(
                {
                    "dryRun": True,
                    "ids": [row[0] for row in rows],
                    "note": "Outdated-version filtering is applied only on execution",
                }
            )
        )
        return
    store.initialize()
    service = build_duplicate_service(settings, build_complaint_service(settings, store))
    version = MatchingConfig.from_settings(settings).version if args.only_outdated else None
    ids = service.repository.historical_ids(
        args.after, args.limit, version, TEXT_ENGINE.version if args.only_outdated else None
    )
    for identity in ids:
        service.repository.enqueue(identity)
        service.process_one(identity)
        print(json.dumps({"resumeAfter": identity, "processing": service.repository.job(identity)}))
    print(
        json.dumps(
            {
                "processed": len(ids),
                "configVersion": service.config.version,
                "nextAfter": ids[-1] if ids else args.after,
            }
        )
    )


if __name__ == "__main__":
    main()
