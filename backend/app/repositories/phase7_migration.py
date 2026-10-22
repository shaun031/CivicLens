def migrate_phase7(db) -> None:
    """No existing tables are rebuilt. Historical assignment is an explicit bounded job."""
    db.executescript("""
        BEGIN IMMEDIATE;
        CREATE TABLE IF NOT EXISTS incidents (
            incident_id TEXT PRIMARY KEY,
            canonical_title TEXT NOT NULL,
            canonical_description TEXT NOT NULL,
            category TEXT NOT NULL,
            latitude REAL NOT NULL CHECK(latitude BETWEEN -90 AND 90),
            longitude REAL NOT NULL CHECK(longitude BETWEEN -180 AND 180),
            status TEXT NOT NULL CHECK(status IN ('OPEN','RESOLVED','MERGED','SUPERSEDED')),
            representative_complaint_id TEXT NOT NULL REFERENCES complaints(complaint_id),
            total_complaint_count INTEGER NOT NULL CHECK(total_complaint_count>=0),
            unique_reporter_count INTEGER NOT NULL CHECK(unique_reporter_count>=0),
            first_reported_at TEXT NOT NULL, last_reported_at TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, resolved_at TEXT,
            merged_into_incident_id TEXT REFERENCES incidents(incident_id),
            version INTEGER NOT NULL CHECK(version>=1),
            CHECK(unique_reporter_count<=total_complaint_count),
            CHECK(merged_into_incident_id IS NULL OR merged_into_incident_id<>incident_id),
            CHECK(status<>'MERGED' OR merged_into_incident_id IS NOT NULL),
            CHECK(status NOT IN ('MERGED','SUPERSEDED') OR total_complaint_count=0)
        );
        CREATE INDEX IF NOT EXISTS incidents_catalog ON incidents(created_at,incident_id);
        CREATE INDEX IF NOT EXISTS incidents_status ON incidents(status,created_at,incident_id);
        CREATE INDEX IF NOT EXISTS complaints_incident_members
            ON complaints(incident_id,created_at,complaint_id);
        CREATE TABLE IF NOT EXISTS incident_operations (
            operation_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
            operation TEXT NOT NULL, actor_id TEXT NOT NULL, reason TEXT NOT NULL,
            result TEXT NOT NULL CHECK(json_valid(result)), created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS incident_membership_events (
            membership_event_id TEXT PRIMARY KEY,
            operation_id TEXT NOT NULL REFERENCES incident_operations(operation_id),
            complaint_id TEXT NOT NULL REFERENCES complaints(complaint_id),
            previous_incident_id TEXT REFERENCES incidents(incident_id),
            new_incident_id TEXT NOT NULL REFERENCES incidents(incident_id),
            operation TEXT NOT NULL, reason TEXT NOT NULL, actor_id TEXT NOT NULL,
            actor_type TEXT NOT NULL, matching_candidate_id TEXT, matching_score_snapshot TEXT,
            created_at TEXT NOT NULL, UNIQUE(operation_id,complaint_id)
        );
        CREATE INDEX IF NOT EXISTS membership_events_previous
            ON incident_membership_events(previous_incident_id,created_at,membership_event_id);
        CREATE INDEX IF NOT EXISTS membership_events_new
            ON incident_membership_events(new_incident_id,created_at,membership_event_id);
        CREATE TABLE IF NOT EXISTS incident_audit (
            event_id TEXT PRIMARY KEY,
            incident_id TEXT NOT NULL REFERENCES incidents(incident_id),
            operation_id TEXT NOT NULL REFERENCES incident_operations(operation_id),
            operation TEXT NOT NULL, actor_id TEXT NOT NULL, reason TEXT NOT NULL,
            created_at TEXT NOT NULL, payload TEXT NOT NULL CHECK(json_valid(payload)),
            UNIQUE(operation_id,incident_id)
        );
        CREATE INDEX IF NOT EXISTS incident_audit_history
            ON incident_audit(incident_id,created_at,event_id);
        CREATE TABLE IF NOT EXISTS clustering_jobs (
            source_id TEXT PRIMARY KEY REFERENCES complaints(complaint_id),
            state TEXT NOT NULL CHECK(state IN ('PENDING','RUNNING','RETRY','COMPLETE')),
            attempts INTEGER NOT NULL DEFAULT 0,
            available_at REAL NOT NULL DEFAULT 0, lease_token TEXT,
            rerun_requested INTEGER NOT NULL DEFAULT 0 CHECK(rerun_requested IN (0,1)),
            report TEXT, error_category TEXT, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS clustering_jobs_queue ON clustering_jobs(state,available_at);
        INSERT OR IGNORE INTO clustering_jobs(source_id,state,updated_at)
            SELECT complaint_id,'PENDING',updated_at FROM complaints;
        CREATE TRIGGER IF NOT EXISTS complaints_clustering_outbox AFTER INSERT ON complaints BEGIN
            INSERT INTO clustering_jobs(source_id,state,updated_at)
            VALUES(NEW.complaint_id,'PENDING',NEW.updated_at);
        END;
        CREATE TRIGGER IF NOT EXISTS complaints_valid_incident_insert
        BEFORE INSERT ON complaints WHEN NEW.incident_id IS NOT NULL BEGIN
            SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM incidents
                WHERE incident_id=NEW.incident_id AND status IN ('OPEN','RESOLVED'))
                THEN RAISE(ABORT,'Invalid incident membership') END;
        END;
        CREATE TRIGGER IF NOT EXISTS complaints_valid_incident_update
        BEFORE UPDATE OF incident_id ON complaints WHEN NEW.incident_id IS NOT NULL BEGIN
            SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM incidents
                WHERE incident_id=NEW.incident_id AND status IN ('OPEN','RESOLVED'))
                THEN RAISE(ABORT,'Invalid incident membership') END;
        END;
        PRAGMA user_version=5;
        COMMIT;
    """)
