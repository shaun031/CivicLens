import hashlib
import sqlite3
import time

from fastapi import HTTPException

from app.core.config import Settings
from app.integrations.database.sqlite_discovery import SQLiteDiscovery, publication_from_row
from app.models.complaint import Complaint, ComplaintImage, ComplaintPage, ComplaintSummary
from app.models.discovery import SearchFilters
from app.repositories.auth_store import AuthStore
from app.repositories.complaint_repository import RepositoryUnavailable


class SQLiteComplaints:
    def __init__(self, store: AuthStore, settings: Settings):
        self.store, self.settings = store, settings
        self.discovery = SQLiteDiscovery(self)

    @staticmethod
    def hydrate(
        db: sqlite3.Connection, row: sqlite3.Row, image_rows=None, publication=None
    ) -> Complaint:
        complaint_id = row["complaint_id"]
        images = [
            ComplaintImage(
                imageId=item["image_id"],
                storageKey=item["storage_key"],
                contentType=item["content_type"],
                fileSize=item["file_size"],
                createdAt=item["created_at"],
                url=f"/complaints/{complaint_id}/images/{item['image_id']}",
            )
            for item in (
                image_rows
                if image_rows is not None
                else db.execute(
                    "SELECT * FROM complaint_images WHERE complaint_id=? ORDER BY image_id",
                    (complaint_id,),
                )
            )
        ]
        return Complaint(
            complaintId=complaint_id,
            citizenId=row["citizen_id"],
            title=row["title"],
            description=row["description"],
            category=row["category"],
            reportedSeverity=row["reported_severity"],
            latitude=row["latitude"],
            longitude=row["longitude"],
            landmark=row["landmark"],
            addressLabel=row["address_label"],
            status=row["status"],
            incidentId=row["incident_id"],
            createdAt=row["created_at"],
            updatedAt=row["updated_at"],
            images=images,
            publication=publication_from_row(
                publication
                if publication is not None
                else db.execute(
                    "SELECT * FROM complaint_publications WHERE complaint_id=?", (complaint_id,)
                ).fetchone()
            ).model_dump(),
        )

    @classmethod
    def hydrate_many(cls, db, rows) -> list[Complaint]:
        if not rows:
            return []
        ids = [row["complaint_id"] for row in rows]
        marks = ",".join("?" for _ in ids)
        images = {key: [] for key in ids}
        for item in db.execute(
            f"SELECT * FROM complaint_images WHERE complaint_id IN ({marks}) ORDER BY image_id", ids
        ):
            images[item["complaint_id"]].append(item)
        publications = {
            row["complaint_id"]: row
            for row in db.execute(
                f"SELECT * FROM complaint_publications WHERE complaint_id IN ({marks})", ids
            )
        }
        return [
            cls.hydrate(
                db, row, images[row["complaint_id"]], publications.get(row["complaint_id"], {})
            )
            for row in rows
        ]

    def _request(self, db, citizen: str, key: str, fingerprint: str) -> Complaint | None:
        row = db.execute(
            "SELECT * FROM complaint_requests WHERE citizen_id=? AND request_key=?", (citizen, key)
        ).fetchone()
        if row is None:
            return None
        if row["fingerprint"] != fingerprint:
            raise HTTPException(409, "This request key was already used with different content.")
        complaint = db.execute(
            "SELECT * FROM complaints WHERE complaint_id=? AND citizen_id=?",
            (row["complaint_id"], citizen),
        ).fetchone()
        return self.hydrate(db, complaint)

    def request(self, citizen: str, key: str, fingerprint: str) -> Complaint | None:
        try:
            with self.store.connection() as db:
                return self._request(db, citizen, key, fingerprint)
        except sqlite3.Error as error:
            raise RepositoryUnavailable from error

    def create(self, complaint: Complaint, key: str, fingerprint: str) -> tuple[Complaint, bool]:
        try:
            with self.store.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                existing = self._request(db, complaint.citizenId, key, fingerprint)
                if existing:
                    return existing, False
                now = int(time.time())
                bucket = hashlib.sha256(f"complaint:{complaint.citizenId}".encode()).hexdigest()
                rate = db.execute("SELECT * FROM rate_limits WHERE bucket=?", (bucket,)).fetchone()
                if (
                    rate
                    and rate["expires_at"] > now
                    and rate["attempts"] >= self.settings.complaint_rate_limit
                ):
                    raise HTTPException(
                        429,
                        "Complaint submission limit reached. Try again later.",
                        headers={"Retry-After": str(rate["expires_at"] - now)},
                    )
                if not rate or rate["expires_at"] <= now:
                    db.execute(
                        "INSERT OR REPLACE INTO rate_limits VALUES (?,1,?)",
                        (bucket, now + self.settings.complaint_rate_window),
                    )
                else:
                    db.execute(
                        "UPDATE rate_limits SET attempts=attempts+1 WHERE bucket=?", (bucket,)
                    )
                db.execute(
                    "INSERT INTO complaints VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        complaint.complaintId,
                        complaint.citizenId,
                        complaint.title,
                        complaint.description,
                        complaint.category,
                        complaint.reportedSeverity,
                        complaint.latitude,
                        complaint.longitude,
                        complaint.landmark,
                        complaint.addressLabel,
                        complaint.status,
                        complaint.incidentId,
                        complaint.createdAt,
                        complaint.updatedAt,
                    ),
                )
                for image in complaint.images:
                    db.execute(
                        "INSERT INTO complaint_images VALUES (?,?,?,?,?,?)",
                        (
                            image.imageId,
                            complaint.complaintId,
                            image.storageKey,
                            image.contentType,
                            image.fileSize,
                            image.createdAt,
                        ),
                    )
                db.execute(
                    "INSERT INTO complaint_requests VALUES (?,?,?,?)",
                    (complaint.citizenId, key, fingerprint, complaint.complaintId),
                )
            return complaint, True
        except sqlite3.Error as error:
            raise RepositoryUnavailable from error

    def get(self, complaint_id: str, citizen: str) -> Complaint | None:
        try:
            with self.store.connection() as db:
                row = db.execute(
                    "SELECT * FROM complaints WHERE complaint_id=? AND citizen_id=?",
                    (complaint_id, citizen),
                ).fetchone()
                return self.hydrate(db, row) if row else None
        except sqlite3.Error as error:
            raise RepositoryUnavailable from error

    def list(
        self, citizen: str, limit: int, cursor: str | None, filters: SearchFilters | None = None
    ) -> ComplaintPage:
        return self.discovery.search(citizen, limit, cursor, filters or SearchFilters())

    def summary(self, citizen: str, days: int = 30) -> ComplaintSummary:
        return self.discovery.summary(citizen, days)
