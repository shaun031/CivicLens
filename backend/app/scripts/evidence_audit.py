"""Trusted local, read-only reconciliation report. Never deletes files or changes metadata."""

import argparse
import os
import time
from contextlib import closing
from uuid import uuid4

from app.core.config import get_settings
from app.integrations.storage.local_evidence import LocalEvidence
from app.scripts.audit_local_data import read_only
from app.scripts.backup_local import evidence_keys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minimum-age-hours", type=int, default=24)
    args = parser.parse_args()
    settings = get_settings()
    if settings.app_env != "local" or settings.auth_provider != "local":
        parser.error("Evidence audit requires explicit local mode")
    if not settings.local_db_path.is_file() or settings.local_evidence_root is None:
        parser.error("Initialize the local database before auditing evidence")
    if args.minimum_age_hours < 1:
        parser.error("Minimum age must be at least one hour")
    storage = LocalEvidence(settings.local_evidence_root, settings.max_upload_bytes)
    # Validate the configured root/ancestors without creating any directory.
    storage.path(f"complaints/{uuid4()}/{uuid4()}.jpg")
    with closing(read_only(settings.local_db_path)) as db:
        referenced = evidence_keys(db)
    files = set()
    cutoff = time.time() - args.minimum_age_hours * 3600
    old = set()
    for directory, children, filenames in os.walk(storage.root / "complaints", followlinks=False):
        from pathlib import Path

        parent = Path(directory)
        children[:] = [
            name
            for name in children
            if not (parent / name).is_symlink() and not (parent / name).is_junction()
        ]
        for name in filenames:
            path = parent / name
            key = path.relative_to(storage.root).as_posix()
            checked = storage.path(key)
            files.add(key)
            if checked.stat().st_mtime < cutoff:
                old.add(key)
    for key in sorted(referenced - files):
        print(f"MISSING referenced evidence: {key}")
    for key in sorted((files - referenced) & old):
        print(f"UNREFERENCED candidate (review before quarantine): {key}")
    print(f"Read-only audit: {len(referenced)} referenced, {len(files)} stored. Nothing changed.")


if __name__ == "__main__":
    main()
