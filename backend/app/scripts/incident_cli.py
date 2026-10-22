import argparse
import json
import sqlite3
from contextlib import contextmanager

from app.core.config import Settings
from app.integrations.database.sqlite_complaints import SQLiteComplaints
from app.models.discovery import search_matches, search_normalize
from app.repositories.auth_store import AuthStore
from app.services.complaint_factory import build_complaint_service
from app.services.duplicate_detection_service import build_duplicate_service
from app.services.incident_service import build_incident_service


class ReadOnlyStore(AuthStore):
    @contextmanager
    def connection(self):
        db = sqlite3.connect(f"{self.path.resolve().as_uri()}?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        db.create_function("search_normalize", 1, search_normalize, deterministic=True)
        db.create_function("search_matches", 2, search_matches, deterministic=True)
        try:
            yield db
        finally:
            db.close()


def arguments(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--after", default="")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def local_service(parser, args):
    if not 1 <= args.limit <= 500:
        parser.error("Batch limit must be 1–500")
    settings = Settings()
    if settings.app_env not in ("local", "test"):
        parser.error("Incident maintenance is local-only; no AWS connection is permitted")
    if not settings.local_db_path.exists():
        parser.error("Start/migrate the local app first; no database was created")
    store = (
        ReadOnlyStore(settings.local_db_path) if args.dry_run else AuthStore(settings.local_db_path)
    )
    if not args.dry_run:
        store.initialize()
    else:
        with store.connection() as db:
            if db.execute("PRAGMA user_version").fetchone()[0] != 8:
                parser.error(
                    "Read-only diagnostics require schema8; run the trusted migration first"
                )
    complaints = build_complaint_service(settings, store)
    complaints.repository = SQLiteComplaints(store, settings)
    matching = build_duplicate_service(settings, complaints)
    service = build_incident_service(settings, complaints, matching)
    matching.incidents = service
    return service


def output(value):
    print(json.dumps(value, default=str, allow_nan=False), flush=True)
