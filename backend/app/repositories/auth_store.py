import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class AuthStore:
    """Local-only SQLite storage. Connections are short-lived and transactions explicit."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2, 3, 4, 5, 6, 7, 8):
                raise RuntimeError("Unsupported local authentication schema version")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    display_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('CITIZEN','OFFICER','ADMIN')),
                    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
                    is_verified INTEGER NOT NULL DEFAULT 1 CHECK(is_verified IN (0,1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_login_at TEXT
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
                CREATE TABLE IF NOT EXISTS password_resets (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS rate_limits (
                    bucket TEXT PRIMARY KEY,
                    attempts INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL
                );
            """)
            if version < 2:
                # Additive, transactional migration; never replace/reset Phase 2 accounts.
                db.executescript("""
                    BEGIN IMMEDIATE;
                    CREATE TABLE IF NOT EXISTS complaints (
                        complaint_id TEXT PRIMARY KEY,
                        citizen_id TEXT NOT NULL REFERENCES users(id),
                        title TEXT NOT NULL CHECK(length(title) BETWEEN 10 AND 150),
                        description TEXT NOT NULL CHECK(length(description) BETWEEN 20 AND 2000),
                        category TEXT NOT NULL CHECK(category IN ('POTHOLE','DAMAGED_ROAD',
                            'BROKEN_STREETLIGHT','GARBAGE','DRAINAGE',
                            'PUBLIC_PROPERTY_DAMAGE','OTHER')),
                        reported_severity TEXT NOT NULL
                            CHECK(reported_severity IN ('LOW','MEDIUM','HIGH')),
                        latitude REAL NOT NULL CHECK(latitude BETWEEN -90 AND 90),
                        longitude REAL NOT NULL CHECK(longitude BETWEEN -180 AND 180),
                        landmark TEXT,
                        address_label TEXT,
                        status TEXT NOT NULL DEFAULT 'SUBMITTED' CHECK(status IN ('SUBMITTED',
                            'UNDER_REVIEW','ASSIGNED','IN_PROGRESS','RESOLVED','REJECTED')),
                        incident_id TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS complaints_citizen_created
                        ON complaints(citizen_id, created_at DESC, complaint_id DESC);
                    CREATE TABLE IF NOT EXISTS complaint_images (
                        image_id TEXT PRIMARY KEY,
                        complaint_id TEXT NOT NULL
                            REFERENCES complaints(complaint_id) ON DELETE CASCADE,
                        storage_key TEXT NOT NULL UNIQUE,
                        content_type TEXT NOT NULL CHECK(content_type='image/jpeg'),
                        file_size INTEGER NOT NULL CHECK(file_size BETWEEN 1 AND 1572864),
                        created_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS complaint_images_owner
                        ON complaint_images(complaint_id);
                    CREATE TABLE IF NOT EXISTS complaint_requests (
                        citizen_id TEXT NOT NULL REFERENCES users(id),
                        request_key TEXT NOT NULL,
                        fingerprint TEXT NOT NULL,
                        complaint_id TEXT NOT NULL UNIQUE REFERENCES complaints(complaint_id),
                        PRIMARY KEY(citizen_id,request_key)
                    );
                    PRAGMA user_version=2;
                    COMMIT;
                """)
            if version < 3:
                from app.repositories.phase5_migration import migrate_phase5

                migrate_phase5(db)
            if version < 4:
                from app.repositories.phase6_migration import migrate_phase6

                migrate_phase6(db)
            if version < 5:
                from app.repositories.phase7_migration import migrate_phase7

                migrate_phase7(db)
            if version < 6:
                from app.repositories.phase8_migration import migrate_phase8

                migrate_phase8(db)
            from app.repositories.phase8_migration import ensure_priority_revision

            ensure_priority_revision(db)
            if version < 7:
                from app.repositories.phase9_migration import migrate_phase9

                migrate_phase9(db)
            if version < 8:
                from app.repositories.phase10_migration import migrate_phase10

                migrate_phase10(db)
            from app.repositories.phase10_migration import ensure_phase10_revision

            ensure_phase10_revision(db)
            from app.repositories.phase11_migration import ensure_analytics

            ensure_analytics(db)
            from app.repositories.phase12_migration import ensure_civic_intelligence

            ensure_civic_intelligence(db)
            # Additive indexes only: no row rebuild, deletion or schema-version reset.
            db.execute(
                "CREATE INDEX IF NOT EXISTS complaints_owner_radius "
                "ON complaints(citizen_id,latitude,longitude,complaint_id)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS publications_radius ON complaint_publications"
                "(publication_status,public_latitude,public_longitude,public_issue_id)"
            )

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        from app.models.discovery import search_matches, search_normalize

        db.create_function("search_normalize", 1, search_normalize, deterministic=True)
        db.create_function("search_matches", 2, search_matches, deterministic=True)
        from app.utils.geography import haversine

        db.create_function("haversine", 4, haversine, deterministic=True)
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()
