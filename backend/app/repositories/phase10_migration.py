from app.events.schema import new_event


def ensure_phase10_revision(db):
    """Add the counterpart invalidator without resetting already migrated durable work."""
    columns = {row[1] for row in db.execute("PRAGMA table_info(event_outbox)")}
    if "event_version" not in columns:
        db.execute("ALTER TABLE event_outbox ADD COLUMN event_version INTEGER NOT NULL DEFAULT 1")
    db.execute("""CREATE TRIGGER IF NOT EXISTS event_previous_membership
        AFTER UPDATE OF incident_id ON complaints
        WHEN OLD.incident_id IS NOT NULL AND NEW.incident_id IS NOT OLD.incident_id BEGIN
        INSERT INTO event_outbox(event_id,event_type,aggregate_type,aggregate_id,
            correlation_id,occurred_at) VALUES(
            lower(hex(randomblob(4)))||'-'||lower(hex(randomblob(2)))||'-4'||
            substr(lower(hex(randomblob(2))),2)||'-a'||substr(lower(hex(randomblob(2))),2)||'-'||
            lower(hex(randomblob(6))), 'IncidentMembershipChanged','INCIDENT',
            OLD.incident_id,OLD.incident_id,strftime('%Y-%m-%dT%H:%M:%fZ','now')); END""")


def migrate_phase10(db):
    """Additive migration; domain triggers and business writes share the same transaction."""
    db.executescript("""
        BEGIN IMMEDIATE;
        CREATE TABLE IF NOT EXISTS event_outbox (
            event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL,
            event_version INTEGER NOT NULL DEFAULT 1,
            aggregate_type TEXT NOT NULL,
            aggregate_id TEXT NOT NULL, correlation_id TEXT NOT NULL, causation_id TEXT,
            occurred_at TEXT NOT NULL, payload TEXT NOT NULL DEFAULT '{}'
            CHECK(json_valid(payload)),
            status TEXT NOT NULL DEFAULT 'PENDING', attempts INTEGER NOT NULL DEFAULT 0,
            available_at REAL NOT NULL DEFAULT 0, lease_token TEXT, dispatched_at TEXT,
            error_category TEXT);
        CREATE INDEX IF NOT EXISTS outbox_due ON event_outbox(status,available_at,event_id);
        CREATE TABLE IF NOT EXISTS event_queue (
            message_id TEXT PRIMARY KEY, event_id TEXT NOT NULL, consumer TEXT NOT NULL,
            envelope TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'PENDING',
            available_at REAL NOT NULL DEFAULT 0, lease_token TEXT,
            attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 5,
            created_at TEXT NOT NULL, processed_at TEXT, error_category TEXT,
            dead_at TEXT, redrives INTEGER NOT NULL DEFAULT 0, acknowledged_at TEXT,
            UNIQUE(event_id,consumer));
        CREATE INDEX IF NOT EXISTS queue_due ON event_queue(state,available_at,message_id);
        CREATE TABLE IF NOT EXISTS event_receipts (
            event_id TEXT NOT NULL, consumer TEXT NOT NULL, handler_version INTEGER NOT NULL,
            completed_at TEXT NOT NULL, PRIMARY KEY(event_id,consumer,handler_version));
        CREATE TABLE IF NOT EXISTS workflow_executions (
            workflow_id TEXT PRIMARY KEY, workflow_type TEXT NOT NULL,
            aggregate_id TEXT NOT NULL, correlation_id TEXT NOT NULL,
            event_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'PENDING', current_step TEXT,
            attempt_count INTEGER NOT NULL DEFAULT 0, started_at TEXT, updated_at TEXT NOT NULL,
            completed_at TEXT, error_category TEXT, incident_id TEXT, review_required INTEGER
            NOT NULL
            DEFAULT 0, workflow_version INTEGER NOT NULL DEFAULT 1,
            owner_token TEXT, lease_until REAL NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS workflow_status ON
        workflow_executions(status,updated_at,workflow_id);
        CREATE INDEX IF NOT EXISTS workflow_aggregate ON
        workflow_executions(aggregate_id,workflow_id);
        CREATE TABLE IF NOT EXISTS workflow_steps (
            workflow_id TEXT NOT NULL REFERENCES workflow_executions(workflow_id),
            step TEXT NOT NULL, status TEXT NOT NULL, result TEXT NOT NULL
            CHECK(json_valid(result)),
            updated_at TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY(workflow_id,step));
        CREATE TABLE IF NOT EXISTS notifications (
            notification_id TEXT PRIMARY KEY, recipient_user_id TEXT NOT NULL REFERENCES users(id),
            notification_type TEXT NOT NULL, title TEXT NOT NULL, message TEXT NOT NULL,
            entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, target_url TEXT NOT NULL,
            read_at TEXT, created_at TEXT NOT NULL, delivery_status TEXT NOT NULL DEFAULT 'IN_APP',
            deduplication_key TEXT NOT NULL UNIQUE);
        CREATE INDEX IF NOT EXISTS notification_owner ON
        notifications(recipient_user_id,created_at DESC,
                                                         notification_id DESC);
        CREATE INDEX IF NOT EXISTS notification_unread ON notifications(recipient_user_id,read_at);
        CREATE TABLE IF NOT EXISTS sla_policies (
            policy_id TEXT PRIMARY KEY, priority_band TEXT NOT NULL, category TEXT,
            department_id TEXT REFERENCES departments(id), urgent INTEGER NOT NULL DEFAULT 0,
            response_hours REAL NOT NULL CHECK(response_hours>0 AND response_hours<=8760),
            resolution_hours REAL NOT NULL CHECK(resolution_hours>=response_hours
                                               AND resolution_hours<=17520),
            version INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL, updated_by TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sla_checks (
            incident_id TEXT PRIMARY KEY REFERENCES incidents(incident_id),
            next_due REAL NOT NULL DEFAULT 0, cycle TEXT NOT NULL, opened_at TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0, error_category TEXT);
        CREATE INDEX IF NOT EXISTS sla_due ON sla_checks(next_due,incident_id);
        CREATE TABLE IF NOT EXISTS escalations (
            escalation_id TEXT PRIMARY KEY, incident_id TEXT NOT NULL REFERENCES
            incidents(incident_id),
            cycle TEXT NOT NULL, milestone TEXT NOT NULL, deadline TEXT NOT NULL,
            policy_id TEXT NOT NULL, policy_version INTEGER NOT NULL,
            created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'OPEN', acknowledged_at TEXT,
            acknowledged_by TEXT, UNIQUE(incident_id,cycle,milestone));
        CREATE INDEX IF NOT EXISTS escalation_incident ON
        escalations(incident_id,created_at,escalation_id);
        CREATE TABLE IF NOT EXISTS workflow_audit (
            id TEXT PRIMARY KEY, entity_id TEXT NOT NULL, kind TEXT NOT NULL,
            actor_id TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS workflow_audit_entity ON workflow_audit(entity_id,created_at,id);
        INSERT OR IGNORE INTO sla_checks(incident_id,cycle,opened_at)
            SELECT incident_id,created_at,first_reported_at FROM incidents WHERE status='OPEN';
    """)
    # SQLite generates UUIDs: old CLI writers also publish within their business transaction.
    uuid = (
        "(lower(hex(randomblob(4)))||'-'||lower(hex(randomblob(2)))||'-4'||"
        "substr(lower(hex(randomblob(2))),2)||'-a'||substr(lower(hex(randomblob(2))),2)||'-'||"
        "lower(hex(randomblob(6))))"
    )
    now = "strftime('%Y-%m-%dT%H:%M:%fZ','now')"

    def trigger(name, clause, kind, aggregate, identity, payload="'{}'"):
        db.execute(
            f"CREATE TRIGGER IF NOT EXISTS {name} {clause} BEGIN "
            "INSERT INTO event_outbox(event_id,event_type,aggregate_type,aggregate_id,"
            "correlation_id,occurred_at,payload) VALUES("
            f"{uuid},'{kind}','{aggregate}',{identity},{identity},{now},{payload}); END"
        )

    trigger(
        "event_complaint",
        "AFTER INSERT ON complaints",
        "ComplaintSubmitted",
        "COMPLAINT",
        "NEW.complaint_id",
    )
    trigger(
        "event_membership",
        "AFTER UPDATE OF incident_id ON complaints WHEN NEW.incident_id IS NOT "
        "OLD.incident_id AND NEW.incident_id IS NOT NULL",
        "IncidentMembershipChanged",
        "INCIDENT",
        "NEW.incident_id",
    )
    trigger(
        "event_priority",
        "AFTER UPDATE ON incident_priority WHEN NEW.priority_band IS NOT OLD.priority_band "
        "OR NEW.urgent_hazard<>OLD.urgent_hazard",
        "IncidentPriorityChanged",
        "INCIDENT",
        "NEW.incident_id",
    )
    trigger(
        "event_department",
        "AFTER UPDATE ON incident_assignments WHEN NEW.department_id IS NOT "
        "OLD.department_id AND NEW.department_id IS NOT NULL",
        "IncidentDepartmentAssigned",
        "INCIDENT",
        "NEW.incident_id",
    )
    trigger(
        "event_officer",
        "AFTER UPDATE ON incident_assignments WHEN NEW.officer_id IS NOT OLD.officer_id "
        "AND NEW.officer_id IS NOT NULL",
        "IncidentOfficerAssigned",
        "INCIDENT",
        "NEW.incident_id",
        "json_object('officerId',NEW.officer_id)",
    )
    trigger(
        "event_start",
        "AFTER UPDATE ON incident_assignments WHEN NEW.status='IN_PROGRESS' AND "
        "OLD.status='OFFICER_ASSIGNED'",
        "IncidentWorkStarted",
        "INCIDENT",
        "NEW.incident_id",
    )
    trigger(
        "event_progress",
        "AFTER UPDATE ON incident_assignments WHEN OLD.status='IN_PROGRESS' AND "
        "(NEW.percentage<>OLD.percentage OR NEW.status<>OLD.status)",
        "IncidentProgressUpdated",
        "INCIDENT",
        "NEW.incident_id",
    )
    trigger(
        "event_lifecycle",
        "AFTER UPDATE OF status ON incidents WHEN NEW.status<>OLD.status",
        "IncidentStatusChanged",
        "INCIDENT",
        "NEW.incident_id",
    )
    db.execute("""CREATE TRIGGER IF NOT EXISTS sla_incident_insert AFTER INSERT ON incidents BEGIN
        INSERT OR IGNORE INTO sla_checks(incident_id,cycle,opened_at)
        VALUES(NEW.incident_id,NEW.created_at,NEW.first_reported_at); END""")
    db.execute("""CREATE TRIGGER IF NOT EXISTS sla_incident_lifecycle
        AFTER UPDATE OF status ON incidents BEGIN
        UPDATE sla_checks SET next_due=0,
        cycle=CASE WHEN NEW.status='OPEN' THEN NEW.updated_at ELSE cycle END,
        opened_at=CASE WHEN NEW.status='OPEN' THEN NEW.updated_at ELSE opened_at END
        WHERE incident_id=NEW.incident_id; END""")
    db.execute("""CREATE TRIGGER IF NOT EXISTS sla_assignment
        AFTER UPDATE ON incident_assignments BEGIN
        UPDATE sla_checks SET next_due=0 WHERE incident_id=NEW.incident_id; END""")
    db.execute("""CREATE TRIGGER IF NOT EXISTS sla_priority AFTER UPDATE ON incident_priority
        WHEN NEW.priority_band IS NOT OLD.priority_band OR NEW.urgent_hazard<>OLD.urgent_hazard
        BEGIN
        UPDATE sla_checks SET next_due=0 WHERE incident_id=NEW.incident_id; END""")
    for band, response, resolution in (
        ("LOW", 336, 672),
        ("MEDIUM", 168, 336),
        ("HIGH", 72, 168),
        ("CRITICAL", 24, 72),
    ):
        db.execute(
            "INSERT OR IGNORE INTO "
            "sla_policies(policy_id,priority_band,response_hours,resolution_hours,updated_a"
            "t,updated_by) VALUES(?,?,?,?,?,?)",
            (band, band, response, resolution, "2026-01-01T00:00:00Z", "migration-demo-defaults"),
        )
    # Adopt existing durable P6/P7 jobs; never erase/reset pending work during an upgrade.
    rows = db.execute(
        "SELECT source_id FROM matching_jobs WHERE state IN('PENDING','RETRY','RUNNING') "
        "UNION SELECT source_id FROM clustering_jobs WHERE state "
        "IN('PENDING','RETRY','RUNNING')"
    ).fetchall()
    for row in rows:
        event = new_event("ComplaintSubmitted", row[0])
        db.execute(
            "INSERT INTO "
            "event_outbox(event_id,event_type,aggregate_type,aggregate_id,correlation_id,oc"
            "curred_at) VALUES(?,?,?,?,?,?)",
            (
                str(event.eventId),
                event.eventType,
                event.aggregateType,
                str(event.aggregateId),
                str(event.correlationId),
                event.occurredAt.isoformat(),
            ),
        )
    db.execute("PRAGMA user_version=8")
    db.commit()
