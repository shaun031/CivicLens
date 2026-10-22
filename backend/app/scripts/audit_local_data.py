"""Read-only, aggregate-only SQLite diagnostics. Never initializes or repairs a database."""

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path

# Fixed SQL only. Missing old-schema tables produce NOT_VERIFIED, never fake zeroes.
CHECKS = {
    "danglingComplaintOwner": (
        {"complaints", "users"},
        "SELECT count(*) FROM complaints c LEFT JOIN users u ON u.id=c.citizen_id "
        "WHERE u.id IS NULL",
    ),
    "danglingCanonicalMembership": (
        {"complaints", "incidents"},
        "SELECT count(*) FROM complaints c LEFT JOIN incidents i USING(incident_id) "
        "WHERE c.incident_id IS NOT NULL AND i.incident_id IS NULL",
    ),
    "retiredCanonicalMembership": (
        {"complaints", "incidents"},
        "SELECT count(*) FROM complaints JOIN incidents USING(incident_id) "
        "WHERE incidents.status IN ('MERGED','SUPERSEDED')",
    ),
    "danglingIncidentAlias": (
        {"incidents"},
        "SELECT count(*) FROM incidents a LEFT JOIN incidents b "
        "ON b.incident_id=a.merged_into_incident_id "
        "WHERE a.merged_into_incident_id IS NOT NULL AND b.incident_id IS NULL",
    ),
    "canonicalMemberCounts": (
        {"incidents", "complaints"},
        "SELECT count(*) FROM incidents i WHERE i.status IN ('OPEN','RESOLVED') "
        "AND i.total_complaint_count != (SELECT count(*) FROM complaints c "
        "WHERE c.incident_id=i.incident_id)",
    ),
    "canonicalReporterCounts": (
        {"incidents", "complaints", "users"},
        "SELECT count(*) FROM incidents i WHERE i.status IN ('OPEN','RESOLVED') "
        "AND i.unique_reporter_count != (SELECT count(DISTINCT c.citizen_id) FROM complaints c "
        "JOIN users u ON u.id=c.citizen_id WHERE c.incident_id=i.incident_id "
        "AND c.status!='REJECTED' AND u.is_active=1 AND u.is_verified=1 AND u.role='CITIZEN')",
    ),
    "orphanAssignment": (
        {"incident_assignments", "incidents", "departments", "users"},
        "SELECT count(*) FROM incident_assignments a LEFT JOIN incidents i USING(incident_id) "
        "LEFT JOIN departments d ON d.id=a.department_id LEFT JOIN users u ON u.id=a.officer_id "
        "WHERE i.incident_id IS NULL OR (a.department_id IS NOT NULL AND d.id IS NULL) "
        "OR (a.officer_id IS NOT NULL AND (u.id IS NULL OR u.role!='OFFICER'))",
    ),
    "multiplePendingRepairs": (
        {"repair_attempts"},
        "SELECT count(*) FROM (SELECT incident_id FROM repair_attempts "
        "WHERE state IN ('PENDING_VERIFICATION','INFORMATION_REQUIRED') "
        "GROUP BY incident_id HAVING count(*)>1)",
    ),
    "duplicateVerificationResponses": (
        {"repair_verifications"},
        "SELECT count(*) FROM (SELECT request_id FROM repair_verifications "
        "GROUP BY request_id HAVING count(*)>1)",
    ),
    "duplicateRecurrencePairs": (
        {"incident_recurrences"},
        "SELECT count(*) FROM (SELECT previous_incident_id,new_incident_id "
        "FROM incident_recurrences GROUP BY previous_incident_id,new_incident_id "
        "HAVING count(*)>1)",
    ),
    "duplicateNotifications": (
        {"notifications"},
        "SELECT count(*) FROM (SELECT deduplication_key FROM notifications "
        "GROUP BY deduplication_key HAVING count(*)>1)",
    ),
    "duplicateConsumerMessages": (
        {"event_queue"},
        "SELECT count(*) FROM (SELECT event_id,consumer FROM event_queue "
        "GROUP BY event_id,consumer HAVING count(*)>1)",
    ),
}


def read_only(path):
    path = Path(path).resolve(strict=True)
    db = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=10)
    db.execute("PRAGMA query_only=ON")
    return db


def audit(path):
    with closing(read_only(path)) as db:
        db.execute("BEGIN")
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        integrity = [r[0] for r in db.execute("PRAGMA integrity_check")]
        foreign = len(db.execute("PRAGMA foreign_key_check").fetchall())
        checks = {}
        for name, (required, sql) in CHECKS.items():
            if not required <= tables:
                checks[name] = {
                    "status": "NOT_VERIFIED",
                    "missingTables": sorted(required - tables),
                }
                continue
            try:
                count = db.execute(sql).fetchone()[0]
                checks[name] = {"status": "FAIL" if count else "PASS", "violations": count}
            except sqlite3.OperationalError:
                checks[name] = {"status": "NOT_VERIFIED", "reason": "Schema revision incompatible"}
        status = (
            "FAIL"
            if integrity != ["ok"] or foreign or any(v["status"] == "FAIL" for v in checks.values())
            else "NOT_VERIFIED"
            if any(v["status"] == "NOT_VERIFIED" for v in checks.values())
            else "PASS"
        )
        return {
            "status": status,
            "readOnly": True,
            "schemaVersion": db.execute("PRAGMA user_version").fetchone()[0],
            "integrity": integrity,
            "foreignKeyViolations": foreign,
            "checks": checks,
            "limitations": "Structural diagnostics, not a full priority recomputation or proof "
            "of evidence availability, account identity or physical repair quality. No repairs.",
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.database)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
