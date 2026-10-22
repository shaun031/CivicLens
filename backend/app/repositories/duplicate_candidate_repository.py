import json
import time
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from app.algorithms.duplicate_detection.category_compatibility import compatible_categories
from app.algorithms.duplicate_detection.config import MatchingConfig
from app.algorithms.duplicate_detection.geographic_similarity import envelope
from app.algorithms.duplicate_detection.image_similarity import FINGERPRINT_VERSION, Fingerprint
from app.algorithms.duplicate_detection.models import MatchInput, MatchResult, TextRecord
from app.models.complaint import Complaint


def timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def match_input(complaint: Complaint) -> MatchInput:
    return MatchInput(
        complaint.complaintId,
        complaint.category,
        complaint.latitude,
        complaint.longitude,
        TextRecord(complaint.title, complaint.description),
        complaint.status,
    )


class DuplicateRepository(Protocol):
    def load(self, source: str) -> Complaint | None: ...
    def nearby(
        self, source: MatchInput, config: MatchingConfig
    ) -> tuple[list[Complaint], bool]: ...
    def cached(self, image: str) -> Fingerprint | None: ...
    def cache(self, image: str, value: Fingerprint) -> None: ...
    def enqueue(self, source: str) -> None: ...
    def claim(self, source: str | None = None) -> tuple[str, str] | None: ...
    def finish(self, source: str, token: str, results: list[MatchResult], report: dict) -> None: ...
    def fail(self, source: str, token: str, category: str) -> None: ...
    def job(self, source: str) -> dict | None: ...
    def candidate(self, identity: str) -> dict | None: ...
    def catalog(self, filters: dict) -> list[dict]: ...
    def review(self, identity: str, status: str, admin: str) -> dict | None: ...


class SQLiteDuplicateRepository:
    def __init__(self, complaints):
        self.complaints, self.store = complaints, complaints.store

    def load(self, source: str) -> Complaint | None:
        with self.store.connection() as db:
            row = db.execute("SELECT * FROM complaints WHERE complaint_id=?", (source,)).fetchone()
            return self.complaints.hydrate(db, row) if row else None

    def nearby(self, source: MatchInput, config: MatchingConfig) -> tuple[list[Complaint], bool]:
        bounds = envelope(source.latitude, source.longitude, config.radius(source.category))
        categories = compatible_categories(source.category, config.allow_related_categories)
        marks = ",".join("?" for _ in categories)
        longitude = (
            "longitude BETWEEN ? AND ?"
            if bounds.west <= bounds.east
            else "(longitude>=? OR longitude<=?)"
        )
        with self.store.connection() as db:
            rows = db.execute(
                f"SELECT * FROM complaints INDEXED BY complaints_internal_geography "
                f"WHERE latitude BETWEEN ? AND ? AND {longitude} AND category IN ({marks}) "
                "AND status IN ('SUBMITTED','UNDER_REVIEW','ASSIGNED','IN_PROGRESS') "
                "AND complaint_id<>? ORDER BY latitude,longitude,complaint_id LIMIT ?",
                (
                    bounds.south,
                    bounds.north,
                    bounds.west,
                    bounds.east,
                    *categories,
                    source.complaint_id,
                    config.candidate_limit + 1,
                ),
            ).fetchall()
            return self.complaints.hydrate_many(db, rows[: config.candidate_limit]), len(
                rows
            ) > config.candidate_limit

    def cached(self, image: str) -> Fingerprint | None:
        with self.store.connection() as db:
            row = db.execute(
                "SELECT * FROM image_fingerprints WHERE image_id=? AND algorithm_version=?",
                (image, FINGERPRINT_VERSION),
            ).fetchone()
        return Fingerprint(row["fingerprint"], bool(row["informative"])) if row else None

    def cache(self, image: str, value: Fingerprint) -> None:
        with self.store.connection() as db:
            db.execute(
                "INSERT OR REPLACE INTO image_fingerprints VALUES(?,?,?,?)",
                (image, value.version, value.bits, int(value.informative)),
            )

    def enqueue(self, source: str) -> None:
        with self.store.connection() as db:
            db.execute(
                "INSERT INTO matching_jobs(source_id,state,updated_at) VALUES(?,'PENDING',?) "
                "ON CONFLICT(source_id) DO UPDATE SET state='PENDING',available_at=0,"
                "attempts=0,error_category=NULL,updated_at=excluded.updated_at "
                "WHERE matching_jobs.state<>'RUNNING' OR matching_jobs.available_at<?",
                (source, timestamp(), time.time()),
            )

    def claim(self, source: str | None = None) -> tuple[str, str] | None:
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT source_id FROM matching_jobs WHERE state IN ('PENDING','RETRY','RUNNING') "
                "AND available_at<=? AND (? IS NULL OR source_id=?) "
                "ORDER BY available_at,source_id LIMIT 1",
                (time.time(), source, source),
            ).fetchone()
            if not row:
                return None
            token = str(uuid4())
            db.execute(
                "UPDATE matching_jobs SET state='RUNNING',lease_token=?,attempts=attempts+1,"
                "available_at=?,updated_at=? WHERE source_id=?",
                (token, time.time() + 120, timestamp(), row[0]),
            )
            return row[0], token

    def finish(self, source: str, token: str, results: list[MatchResult], report: dict) -> None:
        now = timestamp()
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            lease = db.execute(
                "SELECT state,lease_token FROM matching_jobs WHERE source_id=?", (source,)
            ).fetchone()
            if not lease or lease[0] != "RUNNING" or lease[1] != token:
                raise RuntimeError("Matching lease lost")
            for result in results:
                payload = asdict(result)
                # Runtime timings belong to the run, not deterministic pair evidence.
                payload.pop("timings")
                db.execute(
                    "INSERT INTO duplicate_candidates(candidate_id,source_id,duplicate_id,"
                    "combined_score,distance_meters,classification,created_at,updated_at,payload) "
                    "VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(candidate_id) DO UPDATE SET "
                    "combined_score=excluded.combined_score,distance_meters=excluded.distance_meters,"
                    "classification=excluded.classification,updated_at=excluded.updated_at,"
                    "payload=excluded.payload",
                    (
                        result.candidateId,
                        result.sourceComplaintId,
                        result.possibleDuplicateId,
                        result.combinedScore,
                        result.distanceMeters,
                        result.classification,
                        now,
                        now,
                        json.dumps(payload, allow_nan=False),
                    ),
                )
            db.execute(
                "UPDATE matching_jobs SET state=?,available_at=0,config_version=?,result=?,"
                "error_category=NULL,updated_at=? WHERE source_id=?",
                (
                    "INCOMPLETE" if report["incomplete"] else "COMPLETE",
                    report["configVersion"],
                    json.dumps(report, allow_nan=False),
                    now,
                    source,
                ),
            )

    def fail(self, source: str, token: str, category: str) -> None:
        with self.store.connection() as db:
            db.execute(
                "UPDATE matching_jobs SET state='RETRY',available_at=?,error_category=?,"
                "updated_at=? WHERE source_id=? AND lease_token=? AND state='RUNNING'",
                (time.time() + 60, category, timestamp(), source, token),
            )

    def job(self, source: str) -> dict | None:
        with self.store.connection() as db:
            row = db.execute(
                "SELECT state,attempts,config_version,result,updated_at,error_category "
                "FROM matching_jobs WHERE source_id=?",
                (source,),
            ).fetchone()
        if not row:
            return None
        return {
            "state": row[0],
            "attempts": row[1],
            "configVersion": row[2],
            "report": json.loads(row[3]) if row[3] else None,
            "updatedAt": row[4],
            "errorCategory": row[5],
        }

    @staticmethod
    def unpack(row) -> dict:
        return json.loads(row["payload"]) | {
            "reviewStatus": row["review_status"],
            "reviewedAt": row["reviewed_at"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "lastCheckedAt": row["updated_at"],
        }

    def candidate(self, identity: str) -> dict | None:
        with self.store.connection() as db:
            row = db.execute(
                "SELECT * FROM duplicate_candidates WHERE candidate_id=?", (identity,)
            ).fetchone()
        return self.unpack(row) if row else None

    def catalog(self, filters: dict) -> list[dict]:
        where, args = (
            ["d.combined_score BETWEEN ? AND ?"],
            [filters["minScore"], filters["maxScore"]],
        )
        for key, column in (
            ("classification", "d.classification"),
            ("reviewStatus", "d.review_status"),
        ):
            if filters.get(key):
                where.append(f"{column}=?")
                args.append(filters[key])
        if filters.get("complaintId"):
            where.append("(d.source_id=? OR d.duplicate_id=?)")
            args.extend([filters["complaintId"]] * 2)
        if filters.get("category"):
            where.append("(a.category=? OR b.category=?)")
            args.extend([filters["category"]] * 2)
        if filters.get("q"):
            where.append("(instr(lower(a.title),lower(?))>0 OR instr(lower(b.title),lower(?))>0)")
            args.extend([filters["q"]] * 2)
        order = (
            "d.combined_score DESC,json_extract(d.payload,'$.textScore') DESC,"
            "d.distance_meters,d.candidate_id"
            if filters["sort"] == "score"
            else "d.updated_at DESC,d.candidate_id"
        )
        with self.store.connection() as db:
            rows = db.execute(
                "SELECT d.*,a.title AS source_title,b.title AS duplicate_title,"
                "a.category AS source_category,b.category AS duplicate_category "
                "FROM duplicate_candidates d JOIN complaints a ON a.complaint_id=d.source_id "
                "JOIN complaints b ON b.complaint_id=d.duplicate_id WHERE "
                + " AND ".join(where)
                + f" ORDER BY {order} LIMIT ? OFFSET ?",
                (*args, filters["limit"] + 1, filters["offset"]),
            ).fetchall()
        return [
            self.unpack(row)
            | {
                "sourceTitle": row["source_title"],
                "duplicateTitle": row["duplicate_title"],
                "sourceCategory": row["source_category"],
                "duplicateCategory": row["duplicate_category"],
            }
            for row in rows
        ]

    def review(self, identity: str, status: str, admin: str) -> dict | None:
        now = timestamp()
        with self.store.connection() as db:
            db.execute(
                "UPDATE duplicate_candidates SET review_status=?,reviewed_by=?,reviewed_at=? "
                "WHERE candidate_id=?",
                (status, admin, now, identity),
            )
            # Review metadata is retained by matching upserts; this is not an append-only audit log.
        return self.candidate(identity)

    def historical_ids(
        self,
        after: str,
        limit: int,
        config_version: str | None = None,
        model_version: str | None = None,
    ) -> list[str]:
        with self.store.connection() as db:
            return [
                row[0]
                for row in db.execute(
                    "SELECT c.complaint_id FROM complaints c LEFT JOIN matching_jobs j "
                    "ON j.source_id=c.complaint_id WHERE c.complaint_id>? AND "
                    "(? IS NULL OR j.config_version IS NULL OR j.config_version<>? "
                    "OR j.result IS NULL OR json_extract(j.result,'$.modelVersion') IS NULL "
                    "OR json_extract(j.result,'$.modelVersion')<>?) "
                    "ORDER BY c.complaint_id LIMIT ?",
                    (after, config_version, config_version, model_version, limit),
                )
            ]
