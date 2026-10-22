def migrate_phase8(db, replace_invalidators=False):
    """Sidecar state references existing incident IDs; no original table is rebuilt."""
    replacement = (
        "".join(
            f'DROP TRIGGER IF EXISTS "{name}";'
            for name in (
                "priority_incident_changed",
                "priority_membership_changed",
                "priority_reporter_changed",
                "priority_complaint_changed",
            )
        )
        if replace_invalidators
        else ""
    )
    db.executescript(
        "BEGIN IMMEDIATE;"
        + replacement
        + """
        CREATE TABLE IF NOT EXISTS priority_meta (
            singleton INTEGER PRIMARY KEY CHECK(singleton=1), queue_revision INTEGER NOT NULL
        );
        INSERT OR IGNORE INTO priority_meta VALUES(1,0);
        CREATE TABLE IF NOT EXISTS incident_priority (
            incident_id TEXT PRIMARY KEY REFERENCES incidents(incident_id),
            controls TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(controls)),
            controls_version INTEGER NOT NULL DEFAULT 0,
            result_revision INTEGER NOT NULL DEFAULT 0,
            membership_epoch INTEGER NOT NULL DEFAULT 0,
            generation INTEGER NOT NULL DEFAULT 1,
            needs_recalculation INTEGER NOT NULL DEFAULT 1 CHECK(needs_recalculation IN (0,1)),
            source_version INTEGER NOT NULL DEFAULT 0,
            config_version TEXT NOT NULL DEFAULT '',
            result TEXT CHECK(result IS NULL OR json_valid(result)),
            fingerprint TEXT,
            calculated_score REAL CHECK(calculated_score BETWEEN 0 AND 100),
            effective_score REAL CHECK(effective_score BETWEEN 0 AND 100),
            priority_band TEXT CHECK(priority_band IN ('LOW','MEDIUM','HIGH','CRITICAL')),
            assessment_status TEXT,
            severity REAL, public_impact REAL,
            urgent_hazard INTEGER NOT NULL DEFAULT 0,
            override_status TEXT NOT NULL DEFAULT 'NONE',
            unresolved_seconds REAL NOT NULL DEFAULT 0 CHECK(unresolved_seconds>=0),
            age_open_since TEXT,
            age_frozen_seconds REAL NOT NULL DEFAULT 0 CHECK(age_frozen_seconds>=0),
            age_quality TEXT NOT NULL DEFAULT 'APPROXIMATE_BASELINE',
            calculated_at TEXT, next_due REAL NOT NULL DEFAULT 0,
            available_at REAL NOT NULL DEFAULT 0, lease_token TEXT,
            attempts INTEGER NOT NULL DEFAULT 0, error_category TEXT
        );
        CREATE INDEX IF NOT EXISTS priority_rank ON incident_priority(
            urgent_hazard DESC,effective_score DESC,unresolved_seconds DESC,incident_id);
        CREATE INDEX IF NOT EXISTS priority_pending ON incident_priority(
            needs_recalculation,available_at,incident_id);
        CREATE INDEX IF NOT EXISTS priority_due ON incident_priority(next_due,incident_id);
        CREATE TABLE IF NOT EXISTS priority_history (
            event_id TEXT PRIMARY KEY, incident_id TEXT NOT NULL REFERENCES incidents(incident_id),
            operation_id TEXT REFERENCES incident_operations(operation_id),
            kind TEXT NOT NULL, actor_id TEXT NOT NULL, reason TEXT NOT NULL,
            fingerprint TEXT NOT NULL, snapshot TEXT NOT NULL CHECK(json_valid(snapshot)),
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS priority_history_incident
            ON priority_history(incident_id,created_at,event_id);
        INSERT OR IGNORE INTO incident_priority(incident_id,age_open_since,age_frozen_seconds,
                                                age_quality)
            SELECT incident_id,CASE WHEN status='OPEN' THEN first_reported_at END,
                CASE WHEN status='RESOLVED' THEN
                    coalesce(max(0,(julianday(resolved_at)-julianday(first_reported_at))*86400),0)
                ELSE 0 END,
                CASE WHEN julianday(first_reported_at) IS NULL OR
                    (status='RESOLVED' AND julianday(resolved_at) IS NULL)
                    THEN 'INVALID' ELSE 'APPROXIMATE_BASELINE' END FROM incidents;
        CREATE TRIGGER IF NOT EXISTS priority_incident_created AFTER INSERT ON incidents BEGIN
            INSERT OR IGNORE INTO incident_priority(incident_id,age_open_since,age_frozen_seconds,
                                                    age_quality)
            VALUES(NEW.incident_id,CASE WHEN NEW.status='OPEN' THEN NEW.first_reported_at END,
                CASE WHEN NEW.status='RESOLVED' THEN coalesce(max(0,
                    (julianday(NEW.resolved_at)-julianday(NEW.first_reported_at))*86400),0)
                ELSE 0 END,
                CASE WHEN julianday(NEW.first_reported_at) IS NULL OR
                    (NEW.status='RESOLVED' AND julianday(NEW.resolved_at) IS NULL)
                    THEN 'INVALID' ELSE 'APPROXIMATE_BASELINE' END);
        END;
        CREATE TRIGGER IF NOT EXISTS priority_incident_changed
        AFTER UPDATE OF version,status,first_reported_at,resolved_at ON incidents BEGIN
            UPDATE incident_priority SET needs_recalculation=1,generation=generation+1,
                available_at=0,lease_token=NULL,error_category=NULL,
                age_frozen_seconds=CASE WHEN OLD.status='OPEN' AND NEW.status<>'OPEN' THEN
                    age_frozen_seconds+coalesce(max(0,(julianday(
                        coalesce(NEW.resolved_at,NEW.updated_at))-julianday(age_open_since))*86400),0)
                    ELSE age_frozen_seconds END,
                age_open_since=CASE WHEN NEW.status<>'OPEN' THEN NULL
                    WHEN OLD.status<>'OPEN' THEN NEW.updated_at
                    WHEN age_frozen_seconds=0 THEN NEW.first_reported_at
                    ELSE age_open_since END,
                age_quality=CASE WHEN julianday(NEW.first_reported_at) IS NULL OR
                    (NEW.status='RESOLVED' AND julianday(NEW.resolved_at) IS NULL)
                    THEN 'INVALID' ELSE age_quality END
            WHERE incident_id=NEW.incident_id;
        END;
        CREATE TRIGGER IF NOT EXISTS priority_membership_changed AFTER INSERT ON incident_audit
        WHEN json_array_length(NEW.payload,'$.changes')>0 BEGIN
            UPDATE incident_priority SET membership_epoch=membership_epoch+1,
                generation=generation+1,needs_recalculation=1,available_at=0,lease_token=NULL
            WHERE incident_id=NEW.incident_id;
        END;
        CREATE TRIGGER IF NOT EXISTS priority_reporter_changed
        AFTER UPDATE OF role,is_active,is_verified ON users BEGIN
            UPDATE incident_priority SET generation=generation+1,needs_recalculation=1,
                available_at=0,lease_token=NULL WHERE incident_id IN (
                SELECT incident_id FROM complaints
                WHERE citizen_id=NEW.id AND incident_id IS NOT NULL);
        END;
        CREATE TRIGGER IF NOT EXISTS priority_complaint_changed
        AFTER UPDATE OF status,reported_severity ON complaints BEGIN
            UPDATE incident_priority SET generation=generation+1,needs_recalculation=1,
                available_at=0,lease_token=NULL WHERE incident_id=NEW.incident_id;
        END;
        CREATE TRIGGER IF NOT EXISTS priority_queue_insert AFTER INSERT ON incident_priority BEGIN
            UPDATE priority_meta SET queue_revision=queue_revision+1 WHERE singleton=1;
        END;
        CREATE TRIGGER IF NOT EXISTS priority_queue_change
        AFTER UPDATE OF generation,controls_version,result ON incident_priority BEGIN
            UPDATE priority_meta SET queue_revision=queue_revision+1 WHERE singleton=1;
        END;
        PRAGMA user_version=6;
        COMMIT;
    """
    )


def ensure_priority_revision(db):
    # Additive compatibility for a database opened by the earlier local Phase8 draft.
    columns = {row[1] for row in db.execute("PRAGMA table_info(incident_priority)")}
    if "result_revision" not in columns:
        db.execute(
            "ALTER TABLE incident_priority ADD COLUMN result_revision INTEGER NOT NULL DEFAULT 0"
        )
    trigger = db.execute(
        "SELECT sql FROM sqlite_master WHERE type='trigger' AND name='priority_incident_changed'"
    ).fetchone()
    if trigger is None or "lease_token=NULL" not in trigger[0]:
        # Upgrade only draft invalidation triggers; never remove data or score history.
        migrate_phase8(db, replace_invalidators=True)
