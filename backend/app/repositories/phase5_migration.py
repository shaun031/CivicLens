import sqlite3


def migrate_phase5(db: sqlite3.Connection, enable_fts: bool = True) -> None:
    """One additive transaction. No account, complaint or image table is rebuilt."""
    db.executescript("""
        BEGIN IMMEDIATE;
        CREATE INDEX IF NOT EXISTS complaints_owner_status
            ON complaints(citizen_id,status,created_at,complaint_id);
        CREATE INDEX IF NOT EXISTS complaints_owner_category
            ON complaints(citizen_id,category,created_at,complaint_id);
        CREATE TABLE IF NOT EXISTS complaint_publications (
            complaint_id TEXT PRIMARY KEY REFERENCES complaints(complaint_id) ON DELETE CASCADE,
            citizen_requested INTEGER NOT NULL DEFAULT 0 CHECK(citizen_requested IN (0,1)),
            publication_status TEXT NOT NULL DEFAULT 'PRIVATE'
                CHECK(publication_status IN ('PRIVATE','PENDING_REVIEW','PUBLISHED','REJECTED')),
            public_issue_id TEXT UNIQUE,
            public_summary TEXT,
            public_latitude REAL CHECK(public_latitude BETWEEN -90 AND 90),
            public_longitude REAL CHECK(public_longitude BETWEEN -180 AND 180),
            published_at TEXT,
            public_geo_cell TEXT,
            reviewed_by TEXT,
            reviewed_at TEXT,
            CHECK(publication_status <> 'PUBLISHED' OR (citizen_requested=1
                AND public_issue_id IS NOT NULL AND length(public_summary) BETWEEN 15 AND 300
                AND public_latitude IS NOT NULL AND public_longitude IS NOT NULL
                AND published_at IS NOT NULL AND public_geo_cell IS NOT NULL))
        );
        CREATE INDEX IF NOT EXISTS publications_geo
            ON complaint_publications(public_geo_cell,public_issue_id)
            WHERE publication_status='PUBLISHED';
        CREATE TABLE IF NOT EXISTS publication_audit (
            event_id TEXT PRIMARY KEY,
            complaint_id TEXT NOT NULL,
            actor_id TEXT NOT NULL,
            action TEXT NOT NULL,
            from_status TEXT NOT NULL,
            to_status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS publication_audit_entity
            ON publication_audit(complaint_id,created_at,event_id);
    """)
    try:
        if enable_fts:
            try:
                db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS complaint_search USING fts5(text)")
            except sqlite3.OperationalError as error:
                if "no such module: fts5" not in str(error).lower():
                    raise
                enable_fts = False
        if enable_fts:
            db.execute(
                "INSERT OR REPLACE INTO complaint_search(rowid,text) "
                "SELECT rowid,search_normalize(title||' '||description||' '||"
                "COALESCE(landmark,'')||' '||COALESCE(address_label,'')) FROM complaints"
            )
            # execute, not executescript: do not implicitly commit the in-flight migration.
            db.execute("""CREATE TRIGGER IF NOT EXISTS complaints_search_insert
                AFTER INSERT ON complaints BEGIN
                INSERT INTO complaint_search(rowid,text) VALUES(new.rowid,
                    search_normalize(new.title||' '||new.description||' '||
                    COALESCE(new.landmark,'')||' '||COALESCE(new.address_label,''))); END""")
            db.execute("""CREATE TRIGGER IF NOT EXISTS complaints_search_update
                AFTER UPDATE OF title,description,landmark,address_label ON complaints BEGIN
                DELETE FROM complaint_search WHERE rowid=old.rowid;
                INSERT INTO complaint_search(rowid,text) VALUES(new.rowid,
                    search_normalize(new.title||' '||new.description||' '||
                    COALESCE(new.landmark,'')||' '||COALESCE(new.address_label,''))); END""")
            db.execute("""CREATE TRIGGER IF NOT EXISTS complaints_search_delete
                AFTER DELETE ON complaints BEGIN
                DELETE FROM complaint_search WHERE rowid=old.rowid; END""")
        db.execute("PRAGMA user_version=3")
        db.commit()
    except Exception:
        db.rollback()
        raise
