"""Indexed local search, aggregate analytics and approved-only geographic projection."""

import hashlib
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException

from app.models.complaint import ComplaintPage, ComplaintSummary
from app.models.discovery import (
    Bounds,
    Category,
    Nearby,
    Publication,
    PublicationReview,
    PublicIssue,
    PublicIssuePage,
    SearchFilters,
    search_terms,
)
from app.repositories.complaint_repository import RepositoryUnavailable
from app.utils.context_cursor import pack_cursor, unpack_cursor
from app.utils.geography import cells_for_bounds, geo_cell, haversine, inside_bounds


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def publication_from_row(row) -> Publication:
    if not row:
        return Publication()
    return Publication(
        citizenRequestedPublication=bool(row["citizen_requested"]),
        publicationStatus=row["publication_status"],
        publicIssueId=row["public_issue_id"],
        publicSummary=row["public_summary"],
        publicLatitude=row["public_latitude"],
        publicLongitude=row["public_longitude"],
        publishedAt=row["published_at"],
    )


class SQLiteDiscovery:
    def __init__(self, complaints):
        self.complaints, self.store = complaints, complaints.store

    def search(
        self, citizen: str, limit: int, cursor: str | None, filters: SearchFilters
    ) -> ComplaintPage:
        context = {"owner": citizen, "provider": "sqlite-search", **filters.model_dump(mode="json")}
        key = unpack_cursor(cursor, context, (3,))
        column = {"createdAt": "created_at", "category": "category", "status": "status"}[
            filters.sortBy
        ]
        direction = "ASC" if filters.sortOrder == "asc" else "DESC"
        operator = ">" if direction == "ASC" else "<"
        where, params = ["c.citizen_id=?"], [citizen]
        for value, name in [
            (filters.category, "category"),
            (filters.status, "status"),
            (filters.reportedSeverity, "reported_severity"),
        ]:
            if value:
                where.append(f"c.{name}=?")
                params.append(value)
        if filters.dateFrom:
            where.append("c.created_at>=?")
            params.append(f"{filters.dateFrom.isoformat()}T00:00:00.000Z")
        if filters.dateTo:
            where.append("c.created_at<=?")
            params.append(f"{filters.dateTo.isoformat()}T23:59:59.999Z")
        try:
            with self.store.connection() as db:
                db.execute("BEGIN")  # count + page use one read snapshot
                if filters.q:
                    if db.execute(
                        "SELECT 1 FROM sqlite_master WHERE name='complaint_search'"
                    ).fetchone():
                        where.append(
                            "c.rowid IN (SELECT rowid FROM complaint_search "
                            "WHERE complaint_search MATCH ?)"
                        )
                        params.append(
                            " AND ".join(f'"{term}"*' for term in search_terms(filters.q))
                        )
                    else:
                        where.append(
                            "search_matches(c.title||' '||c.description||' '||"
                            "COALESCE(c.landmark,'')||' '||COALESCE(c.address_label,''),?)"
                        )
                        params.append(filters.q)
                predicate = " AND ".join(where)
                total = db.execute(
                    f"SELECT COUNT(*) FROM complaints c WHERE {predicate}", params
                ).fetchone()[0]
                if key:
                    where.append(f"(c.{column},c.created_at,c.complaint_id) {operator} (?,?,?)")
                    params.extend(key)
                rows = db.execute(
                    f"SELECT c.* FROM complaints c WHERE {' AND '.join(where)} "
                    f"ORDER BY c.{column} {direction},c.created_at {direction},"
                    f"c.complaint_id {direction} LIMIT ?",
                    [*params, limit + 1],
                ).fetchall()
                items = self.complaints.hydrate_many(db, rows[:limit])
                token = (
                    pack_cursor(
                        context,
                        [
                            rows[limit - 1][column],
                            rows[limit - 1]["created_at"],
                            rows[limit - 1]["complaint_id"],
                        ],
                    )
                    if len(rows) > limit
                    else None
                )
                return ComplaintPage(items=items, nextCursor=token, total=total)
        except sqlite3.Error as error:
            raise RepositoryUnavailable from error

    def summary(self, citizen: str, days: int = 30) -> ComplaintSummary:
        today = datetime.now(UTC).date()
        start = today - timedelta(days=days - 1)
        try:
            with self.store.connection() as db:
                db.execute("BEGIN")
                counts = {
                    row[0]: row[1]
                    for row in db.execute(
                        "SELECT status,COUNT(*) FROM complaints WHERE citizen_id=? GROUP BY status",
                        (citizen,),
                    )
                }
                categories = [
                    {"category": row[0], "count": row[1]}
                    for row in db.execute(
                        "SELECT category,COUNT(*) FROM complaints WHERE citizen_id=? "
                        "GROUP BY category ORDER BY category",
                        (citizen,),
                    )
                ]
                trend = dict(
                    db.execute(
                        "SELECT substr(created_at,1,10),COUNT(*) FROM complaints "
                        "WHERE citizen_id=? AND created_at>=? AND created_at<=? "
                        "GROUP BY substr(created_at,1,10)",
                        (citizen, f"{start}T00:00:00.000Z", f"{today}T23:59:59.999Z"),
                    )
                )
                rows = db.execute(
                    "SELECT * FROM complaints WHERE citizen_id=? "
                    "ORDER BY created_at DESC,complaint_id DESC LIMIT 3",
                    (citizen,),
                ).fetchall()
                return ComplaintSummary(
                    total=sum(counts.values()),
                    counts=counts,
                    byCategory=categories,
                    submissionTrend=[
                        {
                            "date": str(start + timedelta(days=i)),
                            "count": trend.get(str(start + timedelta(days=i)), 0),
                        }
                        for i in range(days)
                    ]
                    if counts
                    else [],
                    recent=self.complaints.hydrate_many(db, rows),
                    trendDays=days,
                )
        except sqlite3.Error as error:
            raise RepositoryUnavailable from error

    def _change(
        self,
        complaint_id: str,
        actor: str,
        requested: bool | None = None,
        review: PublicationReview | None = None,
    ) -> Publication:
        try:
            with self.store.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                complaint = db.execute(
                    "SELECT * FROM complaints WHERE complaint_id=?", (complaint_id,)
                ).fetchone()
                if not complaint or (review is None and complaint["citizen_id"] != actor):
                    raise HTTPException(404, "Complaint not found.")
                row = db.execute(
                    "SELECT * FROM complaint_publications WHERE complaint_id=?", (complaint_id,)
                ).fetchone()
                previous = publication_from_row(row)
                current = previous.model_copy(deep=True)
                timestamp = utc_now()
                if review is None:
                    current.citizenRequestedPublication = bool(requested)
                    if requested:
                        if previous.publicationStatus == "PUBLISHED":
                            return previous
                        current.publicationStatus = "PENDING_REVIEW"
                    else:
                        current.publicationStatus = "PRIVATE"
                    action = "REQUEST" if requested else "WITHDRAW"
                else:
                    action = review.decision
                    if review.decision == "APPROVE":
                        if (
                            not previous.citizenRequestedPublication
                            or previous.publicationStatus != "PENDING_REVIEW"
                        ):
                            raise HTTPException(
                                409, "Only a pending citizen publication request can be approved."
                            )
                        current.publicationStatus = "PUBLISHED"
                        current.publicIssueId = previous.publicIssueId or str(uuid4())
                        current.publicSummary = review.publicSummary
                        # ~110m latitude precision; administrator chooses a general public point.
                        current.publicLatitude = round(review.publicLatitude, 3)
                        current.publicLongitude = round(review.publicLongitude, 3)
                        if current.publicLongitude == 180:
                            current.publicLongitude = -180.0
                        current.publishedAt = timestamp
                    elif review.decision == "REJECT":
                        if previous.publicationStatus not in ("PENDING_REVIEW", "PUBLISHED"):
                            raise HTTPException(409, "No active publication request to reject.")
                        current.publicationStatus = "REJECTED"
                    else:
                        if previous.publicationStatus != "PUBLISHED":
                            raise HTTPException(409, "The issue is not published.")
                        current.publicationStatus = "PRIVATE"
                        current.citizenRequestedPublication = False
                if current.publicationStatus != "PUBLISHED":
                    current.publicSummary = current.publicLatitude = current.publicLongitude = (
                        current.publishedAt
                    ) = None
                cell = (
                    geo_cell(current.publicLatitude, current.publicLongitude)
                    if current.publicationStatus == "PUBLISHED"
                    else None
                )
                db.execute(
                    "INSERT INTO complaint_publications VALUES (?,?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(complaint_id) DO UPDATE SET "
                    "citizen_requested=excluded.citizen_requested,"
                    "publication_status=excluded.publication_status,"
                    "public_issue_id=excluded.public_issue_id,public_summary=excluded.public_summary,"
                    "public_latitude=excluded.public_latitude,"
                    "public_longitude=excluded.public_longitude,published_at=excluded.published_at,"
                    "public_geo_cell=excluded.public_geo_cell,"
                    "reviewed_by=excluded.reviewed_by,reviewed_at=excluded.reviewed_at",
                    (
                        complaint_id,
                        int(current.citizenRequestedPublication),
                        current.publicationStatus,
                        current.publicIssueId,
                        current.publicSummary,
                        current.publicLatitude,
                        current.publicLongitude,
                        current.publishedAt,
                        cell,
                        actor if review else None,
                        timestamp if review else None,
                    ),
                )
                db.execute(
                    "INSERT INTO publication_audit VALUES (?,?,?,?,?,?,?)",
                    (
                        str(uuid4()),
                        complaint_id,
                        actor,
                        action,
                        previous.publicationStatus,
                        current.publicationStatus,
                        timestamp,
                    ),
                )
                return current
        except sqlite3.Error as error:
            raise RepositoryUnavailable from error

    def request_publication(self, complaint_id: str, actor: str, requested: bool) -> Publication:
        return self._change(complaint_id, actor, requested=requested)

    def review_publication(
        self, complaint_id: str, actor: str, review: PublicationReview
    ) -> Publication:
        return self._change(complaint_id, actor, review=review)

    def _candidates(self, bounds: Bounds) -> list[PublicIssue]:
        found = {}
        evaluated = 0
        with self.store.connection() as db:
            # Cell equality uses the sparse index; the entire private table is never read.
            for cell in cells_for_bounds(bounds):
                rows = db.execute(
                    "SELECT p.public_issue_id,p.public_summary,p.public_latitude,"
                    "p.public_longitude,p.published_at,c.category,c.status "
                    "FROM complaint_publications p JOIN complaints c USING(complaint_id) "
                    "WHERE p.publication_status='PUBLISHED' AND p.public_geo_cell=? LIMIT ?",
                    (cell, self.complaints.settings.discovery_candidate_limit + 1),
                ).fetchall()
                evaluated += len(rows)
                for row in rows:
                    if inside_bounds(row["public_latitude"], row["public_longitude"], bounds):
                        found[row["public_issue_id"]] = PublicIssue(
                            publicIssueId=row["public_issue_id"],
                            category=row["category"],
                            status=row["status"],
                            summary=row["public_summary"],
                            latitude=row["public_latitude"],
                            longitude=row["public_longitude"],
                            publishedAt=row["published_at"],
                        )
                if evaluated > self.complaints.settings.discovery_candidate_limit:
                    raise HTTPException(
                        422, "Too many geographic candidates. Zoom in or reduce the radius."
                    )
        return list(found.values())

    def public_page(
        self,
        bounds: Bounds,
        category: Category | None,
        status: str | None,
        limit: int,
        cursor: str | None,
        nearby: Nearby | None = None,
    ) -> PublicIssuePage:
        context = {
            "provider": "public-sqlite",
            "bounds": bounds.model_dump(),
            "nearby": nearby.model_dump() if nearby else None,
            "category": category,
            "status": status,
        }
        key = unpack_cursor(cursor, context, (2,) if nearby else (1,))
        items = [
            item
            for item in self._candidates(bounds)
            if (category is None or item.category == category)
            and (status is None or item.status == status)
        ]
        if nearby:
            for item in items:
                item.distanceMeters = haversine(
                    nearby.latitude, nearby.longitude, item.latitude, item.longitude
                )
            items = [item for item in items if item.distanceMeters <= nearby.radiusMeters]

        def ordering(item):
            return (item.distanceMeters, item.publicIssueId) if nearby else (item.publicIssueId,)

        items.sort(key=ordering)
        if key:
            try:
                items = [item for item in items if ordering(item) > tuple(key)]
            except TypeError as error:
                raise HTTPException(400, "Invalid pagination key.") from error
        page = items[:limit]
        return PublicIssuePage(
            items=page,
            nextCursor=pack_cursor(context, list(ordering(page[-1])))
            if len(items) > limit
            else None,
        )

    def public_details(self, public_id: str) -> PublicIssue | None:
        with self.store.connection() as db:
            row = db.execute(
                "SELECT p.*,c.category,c.status FROM complaint_publications p "
                "JOIN complaints c USING(complaint_id) WHERE public_issue_id=? "
                "AND publication_status='PUBLISHED'",
                (public_id,),
            ).fetchone()
            if not row:
                return None
            return PublicIssue(
                publicIssueId=row["public_issue_id"],
                category=row["category"],
                status=row["status"],
                summary=row["public_summary"],
                latitude=row["public_latitude"],
                longitude=row["public_longitude"],
                publishedAt=row["published_at"],
            )

    def public_rate(self, identity: str) -> None:
        bucket = "public#" + hashlib.sha256(identity.encode()).hexdigest()
        now = int(time.time())
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM rate_limits WHERE bucket=?", (bucket,)).fetchone()
            if (
                row
                and row["expires_at"] > now
                and row["attempts"] >= self.complaints.settings.public_query_rate_limit
            ):
                raise HTTPException(
                    429,
                    "Public query limit reached. Try again shortly.",
                    headers={"Retry-After": str(row["expires_at"] - now)},
                )
            if not row or row["expires_at"] <= now:
                db.execute("INSERT OR REPLACE INTO rate_limits VALUES (?,1,?)", (bucket, now + 60))
            else:
                db.execute("UPDATE rate_limits SET attempts=attempts+1 WHERE bucket=?", (bucket,))

    def nearby_page(self, query: Nearby, category, status, limit, cursor):
        from app.integrations.database.sqlite_nearby import radius_rows

        rows, token = radius_rows(self, query, category, status, limit, cursor)
        return PublicIssuePage(
            items=[
                PublicIssue(
                    publicIssueId=r["issueId"],
                    summary=r["title"],
                    category=r["category"],
                    status=r["status"],
                    latitude=r["latitude"],
                    longitude=r["longitude"],
                    publishedAt=r["createdAt"],
                    distanceMeters=r["distanceMeters"],
                )
                for r in rows
            ],
            nextCursor=token,
        )

    def citizen_nearby(self, owner, query, category, status, limit, cursor):
        from app.integrations.database.sqlite_nearby import citizen_page

        return citizen_page(self, owner, query, category, status, limit, cursor)

    def latest_location(self, owner):
        with self.store.connection() as db:
            row = db.execute(
                "SELECT latitude,longitude FROM complaints WHERE citizen_id=? "
                "AND status<>'REJECTED' ORDER BY created_at DESC,complaint_id DESC LIMIT 1",
                (owner,),
            ).fetchone()
            return {"latitude": row[0], "longitude": row[1]} if row else None
