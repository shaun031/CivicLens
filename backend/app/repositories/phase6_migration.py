def migrate_phase6(db) -> None:
    """Additive outbox migration. No complaint columns/identities/publication are changed."""
    db.executescript("""
        BEGIN IMMEDIATE;
        CREATE INDEX IF NOT EXISTS complaints_internal_geography
            ON complaints(latitude, longitude, category, status, complaint_id);
        CREATE TABLE IF NOT EXISTS duplicate_candidates (
            candidate_id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL REFERENCES complaints(complaint_id),
            duplicate_id TEXT NOT NULL REFERENCES complaints(complaint_id),
            combined_score REAL NOT NULL CHECK(combined_score BETWEEN 0 AND 1),
            distance_meters REAL NOT NULL CHECK(distance_meters >= 0),
            classification TEXT NOT NULL,
            review_status TEXT NOT NULL DEFAULT 'PENDING_REVIEW'
                CHECK(review_status IN
                    ('PENDING_REVIEW','DISMISSED','REVIEWED_POSSIBLE_DUPLICATE')),
            reviewed_by TEXT, reviewed_at TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            payload TEXT NOT NULL CHECK(json_valid(payload))
                CHECK(json_extract(payload,'$.geographicScore') BETWEEN 0 AND 1)
                CHECK(json_extract(payload,'$.textScore') BETWEEN 0 AND 1)
                CHECK(json_extract(payload,'$.imageScore') IS NULL
                      OR json_extract(payload,'$.imageScore') BETWEEN 0 AND 1),
            UNIQUE(source_id, duplicate_id), CHECK(source_id < duplicate_id)
        );
        CREATE INDEX IF NOT EXISTS duplicate_candidates_score
            ON duplicate_candidates(combined_score DESC, candidate_id);
        CREATE INDEX IF NOT EXISTS duplicate_candidates_other ON duplicate_candidates(duplicate_id);
        CREATE TABLE IF NOT EXISTS image_fingerprints (
            image_id TEXT NOT NULL REFERENCES complaint_images(image_id) ON DELETE CASCADE,
            algorithm_version TEXT NOT NULL,
            fingerprint TEXT NOT NULL CHECK(length(fingerprint)=16),
            informative INTEGER NOT NULL CHECK(informative IN (0,1)),
            PRIMARY KEY(image_id, algorithm_version)
        );
        CREATE TABLE IF NOT EXISTS matching_jobs (
            source_id TEXT PRIMARY KEY REFERENCES complaints(complaint_id) ON DELETE CASCADE,
            state TEXT NOT NULL
                CHECK(state IN ('PENDING','RUNNING','RETRY','COMPLETE','INCOMPLETE')),
            attempts INTEGER NOT NULL DEFAULT 0,
            available_at REAL NOT NULL DEFAULT 0, lease_token TEXT,
            config_version TEXT, result TEXT, updated_at TEXT NOT NULL,
            error_category TEXT
        );
        CREATE INDEX IF NOT EXISTS matching_jobs_queue ON matching_jobs(state, available_at);
        INSERT OR IGNORE INTO matching_jobs(source_id,state,updated_at)
            SELECT complaint_id,'PENDING',updated_at FROM complaints;
        CREATE TRIGGER IF NOT EXISTS complaints_matching_outbox AFTER INSERT ON complaints BEGIN
            INSERT INTO matching_jobs(source_id,state,updated_at)
            VALUES(NEW.complaint_id,'PENDING',NEW.updated_at);
        END;
        PRAGMA user_version=4;
        COMMIT;
    """)
