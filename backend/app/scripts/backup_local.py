"""Explicit quiesced local backup; never overwrite a backup or restore over live data."""

import argparse
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.integrations.storage.local_evidence import LocalEvidence
from app.scripts.audit_local_data import read_only


def evidence_keys(db):
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    keys = {r[0] for r in db.execute("SELECT storage_key FROM complaint_images")}
    if "repair_evidence" in tables:
        keys.update(r[0] for r in db.execute("SELECT storage_key FROM repair_evidence"))
    return keys


def digest(content):
    return hashlib.sha256(content).hexdigest()


def backup(database, evidence_root, destination, *, quiesced=False):
    if not quiesced:
        raise ValueError("Stop CivicLens APIs/workers first and explicitly confirm quiescence")
    source = Path(database).resolve(strict=True)
    evidence_root = Path(evidence_root).resolve()
    destination = Path(destination).resolve()
    if destination == evidence_root or evidence_root in destination.parents:
        raise ValueError("Backup destination cannot be inside evidence storage")
    if destination == source.parent or destination in source.parents:
        raise ValueError("Choose a separate, new backup directory")
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    output = destination / "database.sqlite3"
    # Incomplete failures remain visibly incomplete, never labelled a successful backup.
    with closing(read_only(source)) as src, closing(sqlite3.connect(output)) as target:
        src.backup(target)
    files = {}
    storage = LocalEvidence(evidence_root, 1572864)
    copied = LocalEvidence(destination / "evidence", 1572864)
    with closing(read_only(output)) as db:
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("Backup database integrity failed")
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Backup has foreign-key violations")
        for key in sorted(evidence_keys(db)):
            content = storage.get(key)
            copied.put(key, content)
            files[key] = digest(content)
    manifest = {
        "version": 1,
        "createdAt": datetime.now(UTC).isoformat(),
        "backupId": str(uuid4()),
        "databaseSha256": digest(output.read_bytes()),
        "evidence": files,
        "containsSecrets": "Database includes password hashes/session hashes. Protect directory; "
        "environment secrets and reset outbox are deliberately NOT copied.",
    }
    with (destination / "manifest.json").open("x", encoding="utf-8") as file:
        json.dump(manifest, file, indent=2)
    verify(destination)
    return {"status": "PASS", "evidenceObjects": len(files), "backupId": manifest["backupId"]}


def verify(directory):
    directory = Path(directory).resolve(strict=True)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != 1:
        raise ValueError("Unsupported backup manifest")
    database = directory / "database.sqlite3"
    if digest(database.read_bytes()) != manifest["databaseSha256"]:
        raise ValueError("Database digest mismatch")
    with closing(read_only(database)) as db:
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("Backup integrity failed")
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Backup foreign-key check failed")
        if evidence_keys(db) != set(manifest["evidence"]):
            raise ValueError("Evidence manifest does not match database")
    storage = LocalEvidence(directory / "evidence", 1572864)
    for key, expected in manifest["evidence"].items():
        if digest(storage.get(key)) != expected:
            raise ValueError("Evidence digest mismatch")
    return {"status": "PASS", "evidenceObjects": len(manifest["evidence"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--database", type=Path, required=True)
    create.add_argument("--evidence-root", type=Path, required=True)
    create.add_argument("--destination", type=Path, required=True)
    create.add_argument("--quiesced", action="store_true", required=True)
    check = sub.add_parser("verify")
    check.add_argument("directory", type=Path)
    args = parser.parse_args()
    result = (
        backup(args.database, args.evidence_root, args.destination, quiesced=args.quiesced)
        if args.command == "create"
        else verify(args.directory)
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
