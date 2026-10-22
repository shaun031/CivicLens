def ensure_analytics(db):
    """Add analytics state while keeping schema8 read-only maintenance compatibility."""
    db.executescript("""
        CREATE TABLE IF NOT EXISTS analytics_meta (
            singleton INTEGER PRIMARY KEY CHECK(singleton=1), revision INTEGER NOT NULL DEFAULT 0,
            observed_at TEXT, observed_event_at TEXT,
            projection_version INTEGER NOT NULL DEFAULT 1);
        INSERT OR IGNORE INTO analytics_meta(singleton) VALUES(1);
        CREATE TABLE IF NOT EXISTS analytics_receipts (
            event_id TEXT PRIMARY KEY, occurred_at TEXT NOT NULL, observed_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS analytics_snapshots (
            identity TEXT PRIMARY KEY, source_revision INTEGER NOT NULL, version INTEGER NOT NULL,
            calculated_at TEXT NOT NULL, body TEXT NOT NULL CHECK(json_valid(body)));
        CREATE TABLE IF NOT EXISTS analytics_export_audit (
            id TEXT PRIMARY KEY, actor_id TEXT NOT NULL, report_type TEXT NOT NULL,
            filters TEXT NOT NULL CHECK(json_valid(filters)), row_count INTEGER NOT NULL,
            generated_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS analytics_complaint_date ON complaints(created_at,complaint_id);
        CREATE INDEX IF NOT EXISTS analytics_incident_geo
            ON incidents(latitude,longitude,incident_id);
        CREATE INDEX IF NOT EXISTS analytics_work_date ON work_history(created_at,entity_id);
        CREATE INDEX IF NOT EXISTS analytics_audit_date ON incident_audit(created_at,incident_id);
        CREATE INDEX IF NOT EXISTS analytics_escalation_date ON escalations(created_at,incident_id);
    """)
    # Revision invalidation is deliberately independent of event delivery: reads stay correct even
    # with a stopped worker, manual correction, account eligibility change or out-of-order events.
    for table in (
        "complaints",
        "incidents",
        "incident_priority",
        "incident_assignments",
        "departments",
        "officer_memberships",
        "users",
        "work_history",
        "incident_audit",
        "escalations",
        "sla_policies",
        "sla_checks",
    ):
        for verb in ("INSERT", "UPDATE", "DELETE"):
            db.execute(
                f"CREATE TRIGGER IF NOT EXISTS analytics_{table}_{verb.lower()} "
                f"AFTER {verb} ON {table} BEGIN UPDATE analytics_meta "
                "SET revision=revision+1 WHERE singleton=1; END"
            )
