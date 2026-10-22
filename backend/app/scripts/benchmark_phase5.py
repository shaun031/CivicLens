"""Disposable synthetic benchmark. Never opens the developer's configured database."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter
from uuid import uuid4

from app.core.config import Settings
from app.integrations.database.sqlite_complaints import SQLiteComplaints
from app.models.discovery import Bounds, Nearby, SearchFilters
from app.repositories.auth_store import AuthStore
from app.utils.geography import geo_cell


def seed(store: AuthStore, count: int = 5000) -> str:
    """Synthetic-only identifiers, titles and approved points; no live municipal data."""
    owners = [str(uuid4()), str(uuid4())]
    now = datetime.now(UTC)
    timestamp = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    categories = ["POTHOLE", "GARBAGE", "DRAINAGE", "DAMAGED_ROAD"]
    statuses = ["SUBMITTED", "UNDER_REVIEW", "ASSIGNED", "IN_PROGRESS", "RESOLVED", "REJECTED"]
    with store.connection() as db:
        for index, owner in enumerate(owners):
            db.execute(
                "INSERT INTO users(id,email,display_name,password_hash,role,"
                "created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                (
                    owner,
                    f"synthetic-{index}@example.invalid",
                    "Synthetic benchmark user",
                    "NO_LOGIN_BENCHMARK_ONLY",
                    "CITIZEN",
                    timestamp,
                    timestamp,
                ),
            )
        for index in range(count):
            complaint_id = str(uuid4())
            created = (
                (now - timedelta(days=index % 60, seconds=index))
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z")
            )
            latitude, longitude = 12.96 + (index % 10) * 0.003, 77.58 + (index % 20) * 0.003
            db.execute(
                "INSERT INTO complaints VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    complaint_id,
                    owners[0 if index % 5 < 3 else 1],
                    f"Synthetic surface defect number {index}",
                    "Synthetic road surface inspection data for local performance testing only.",
                    categories[index % 4],
                    "HIGH" if index % 2 else "LOW",
                    latitude,
                    longitude,
                    "Synthetic test junction",
                    "Synthetic test road",
                    statuses[index % 6],
                    None,
                    created,
                    created,
                ),
            )
            if index % 10 == 0:
                db.execute(
                    "INSERT INTO complaint_publications VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        complaint_id,
                        1,
                        "PUBLISHED",
                        str(uuid4()),
                        "Synthetic approved surface defect for benchmark only",
                        latitude,
                        longitude,
                        timestamp,
                        geo_cell(latitude, longitude),
                        "synthetic-admin",
                        timestamp,
                    ),
                )
    return owners[0]


def benchmark(count=5000) -> dict:
    with TemporaryDirectory(prefix="civiclens-phase5-benchmark-") as directory:
        root = Path(directory)
        settings = Settings(
            _env_file=None,
            app_env="test",
            local_db_path=root / "benchmark.db",
            local_evidence_root=root / "private",
        )
        store = AuthStore(settings.local_db_path)
        store.initialize()
        owner = seed(store, count)
        repository = SQLiteComplaints(store, settings)
        first = repository.list(owner, 20, None)
        operations = {
            "search": lambda: repository.list(owner, 20, None, SearchFilters(q="surface")),
            "combined_filters": lambda: repository.list(
                owner,
                20,
                None,
                SearchFilters(
                    q="surface", category="POTHOLE", status="SUBMITTED", reportedSeverity="LOW"
                ),
            ),
            "pagination": lambda: repository.list(owner, 20, first.nextCursor),
            "summary": lambda: repository.summary(owner, 30),
            "bounding_box": lambda: repository.discovery.public_page(
                Bounds(minLatitude=12.95, maxLatitude=13.0, minLongitude=77.57, maxLongitude=77.65),
                None,
                None,
                50,
                None,
            ),
            "radius": lambda: repository.discovery.nearby_page(
                Nearby(latitude=12.972, longitude=77.595, radiusMeters=5000), None, None, 50, None
            ),
            "owner_radius_200km": lambda: repository.discovery.citizen_nearby(
                owner,
                Nearby(latitude=12.972, longitude=77.595, radiusMeters=200000),
                None,
                None,
                50,
                None,
            ),
        }
        measurements = {}
        for name, operation in operations.items():
            times = []
            for _ in range(5):
                start = perf_counter()
                result = operation()
                times.append((perf_counter() - start) * 1000)
            measurements[name] = {
                "medianMs": round(median(times), 3),
                "maxMs": round(max(times), 3),
                "returned": len(result.items) if hasattr(result, "items") else result.total,
            }
        with store.connection() as db:
            search_plan = [
                row[3]
                for row in db.execute(
                    "EXPLAIN QUERY PLAN SELECT complaint_id FROM complaints "
                    "WHERE citizen_id=? AND category=? "
                    "ORDER BY created_at,complaint_id LIMIT 20",
                    (owner, "POTHOLE"),
                )
            ]
            geo_plan = [
                row[3]
                for row in db.execute(
                    "EXPLAIN QUERY PLAN SELECT public_issue_id FROM complaint_publications "
                    "WHERE publication_status='PUBLISHED' AND public_geo_cell=?",
                    (geo_cell(12.972, 77.595),),
                )
            ]
            owner_count = db.execute(
                "SELECT COUNT(*) FROM complaints WHERE citizen_id=?", (owner,)
            ).fetchone()[0]
            public_count = db.execute("SELECT COUNT(*) FROM complaint_publications").fetchone()[0]
            radius_plans = {}
            for name, sql, params in [
                (
                    "owner_radius",
                    "SELECT complaint_id FROM complaints INDEXED BY "
                    "complaints_owner_radius WHERE citizen_id=? AND latitude BETWEEN ? AND ? "
                    "AND longitude BETWEEN ? AND ?",
                    (owner, 11, 15, 75, 80),
                ),
                (
                    "public_radius",
                    "SELECT public_issue_id FROM complaint_publications INDEXED BY "
                    "publications_radius WHERE publication_status=? "
                    "AND public_latitude BETWEEN ? AND ? AND public_longitude BETWEEN ? AND ?",
                    ("PUBLISHED", 11, 15, 75, 80),
                ),
            ]:
                radius_plans[name] = [r[3] for r in db.execute("EXPLAIN QUERY PLAN " + sql, params)]
        return {
            "syntheticOnly": True,
            "records": count,
            "ownerRecords": owner_count,
            "publishedRecords": public_count,
            "runsPerQuery": 5,
            "measurements": measurements,
            "queryPlans": {
                "owner_category": search_plan,
                "geographic_cell": geo_plan,
                **radius_plans,
            },
            "limitations": "Local warmed SQLite microbenchmark, not production/cloud or "
            "concurrency capacity. All files are temporary and removed on exit.",
        }


def main():
    print(json.dumps(benchmark(), indent=2))


if __name__ == "__main__":
    main()
