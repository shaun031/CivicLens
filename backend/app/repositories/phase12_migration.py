def ensure_civic_intelligence(db):
    """Additive extension of schema8; never rebuild operational or evidence tables."""
    db.executescript("""
        CREATE TABLE IF NOT EXISTS repair_attempts (
            attempt_id TEXT PRIMARY KEY, incident_id TEXT NOT NULL REFERENCES incidents,
            officer_id TEXT NOT NULL REFERENCES users, department_id TEXT NOT NULL REFERENCES
            departments,
            cycle INTEGER NOT NULL CHECK(cycle>0), description TEXT NOT NULL,
            notes TEXT NOT NULL, repaired_at TEXT NOT NULL, submitted_at TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('PENDING_VERIFICATION','VERIFIED_RESOLVED',
                'REJECTED','REWORK_REQUIRED','REOPENED','INFORMATION_REQUIRED')),
            source_version INTEGER NOT NULL, assignment_version INTEGER NOT NULL,
            version INTEGER NOT NULL DEFAULT 1, verified_at TEXT, verified_by TEXT REFERENCES
            users,
            decision_reason TEXT, updated_at TEXT NOT NULL,
            UNIQUE(incident_id,cycle));
        CREATE UNIQUE INDEX IF NOT EXISTS repair_one_pending ON repair_attempts(incident_id)
            WHERE state IN ('PENDING_VERIFICATION','INFORMATION_REQUIRED');
        CREATE INDEX IF NOT EXISTS repair_incident ON repair_attempts(incident_id,cycle DESC);
        CREATE INDEX IF NOT EXISTS repair_pending ON
            repair_attempts(state,submitted_at,attempt_id);
        CREATE TABLE IF NOT EXISTS repair_verification_requests (
            request_id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL REFERENCES repair_attempts,
            citizen_id TEXT NOT NULL REFERENCES users, created_at TEXT NOT NULL,
            UNIQUE(attempt_id,citizen_id));
        CREATE INDEX IF NOT EXISTS repair_requests_citizen
            ON repair_verification_requests(citizen_id,created_at,request_id);
        CREATE TABLE IF NOT EXISTS repair_verifications (
            verification_id TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE
                REFERENCES repair_verification_requests,
            result TEXT NOT NULL CHECK(result IN ('CONFIRMED_FIXED','STILL_BROKEN','UNSURE')),
            feedback TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS repair_evidence (
            image_id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL REFERENCES repair_attempts,
            owner_id TEXT NOT NULL REFERENCES users, kind TEXT NOT NULL CHECK(kind IN
            ('REPAIR','FEEDBACK')),
            storage_key TEXT NOT NULL UNIQUE, file_size INTEGER NOT NULL CHECK(file_size
            BETWEEN 1 AND 1572864),
            approved INTEGER NOT NULL DEFAULT 0 CHECK(approved IN (0,1)), created_at TEXT NOT
            NULL);
        CREATE INDEX IF NOT EXISTS repair_evidence_attempt ON
            repair_evidence(attempt_id,image_id);
        CREATE TABLE IF NOT EXISTS incident_recurrences (
            recurrence_id TEXT PRIMARY KEY, previous_incident_id TEXT NOT NULL REFERENCES
            incidents,
            new_incident_id TEXT NOT NULL REFERENCES incidents,
            repair_attempt_id TEXT NOT NULL REFERENCES repair_attempts,
            score REAL NOT NULL CHECK(score BETWEEN 0 AND 1), distance REAL NOT NULL,
            days_since_repair REAL NOT NULL CHECK(days_since_repair>0),
            state TEXT NOT NULL CHECK(state IN ('POTENTIAL_RECURRENCE','CONFIRMED_RECURRENCE',
                'DISMISSED','INSUFFICIENT_EVIDENCE')),
            explanation TEXT NOT NULL CHECK(json_valid(explanation)), algorithm_version TEXT
            NOT NULL,
            previous_version INTEGER NOT NULL, new_version INTEGER NOT NULL,
            version INTEGER NOT NULL DEFAULT 1, review_reason TEXT, reviewed_by TEXT
            REFERENCES users,
            reviewed_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            CHECK(previous_incident_id<>new_incident_id),
            UNIQUE(previous_incident_id,new_incident_id));
        CREATE INDEX IF NOT EXISTS recurrence_new ON incident_recurrences(new_incident_id,state);
        CREATE INDEX IF NOT EXISTS recurrence_previous ON
            incident_recurrences(previous_incident_id,state);
        CREATE INDEX IF NOT EXISTS recurrence_catalog ON
            incident_recurrences(state,created_at,recurrence_id);
        CREATE INDEX IF NOT EXISTS recurrence_created ON
            incident_recurrences(created_at,recurrence_id);
        CREATE TABLE IF NOT EXISTS fairness_review_records (
            review_id TEXT PRIMARY KEY, area_id TEXT NOT NULL, context TEXT NOT NULL
            CHECK(json_valid(context)),
            state TEXT NOT NULL CHECK(state IN ('UNDER_ADMIN_REVIEW','REVIEWED')),
            notes TEXT NOT NULL, actor_id TEXT NOT NULL REFERENCES users, version INTEGER NOT
            NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS fairness_area ON fairness_review_records(area_id,updated_at);
        CREATE TABLE IF NOT EXISTS civic_intelligence_audit (
            audit_id TEXT PRIMARY KEY, entity_id TEXT NOT NULL, operation_id TEXT NOT NULL
                REFERENCES incident_operations, kind TEXT NOT NULL, actor_id TEXT NOT NULL
            REFERENCES users,
            reason TEXT NOT NULL, snapshot TEXT NOT NULL CHECK(json_valid(snapshot)),
            created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS civic_audit_entity ON
            civic_intelligence_audit(entity_id,created_at);
        CREATE TRIGGER IF NOT EXISTS repair_retired_membership AFTER UPDATE OF status ON incidents
        WHEN NEW.status IN ('MERGED','SUPERSEDED') BEGIN
            UPDATE repair_attempts SET state='REWORK_REQUIRED',version=version+1,
                decision_reason='Canonical retired; review current membership before new repair',
                updated_at=NEW.updated_at WHERE incident_id=NEW.incident_id
                AND state IN ('PENDING_VERIFICATION','INFORMATION_REQUIRED');
        END;
    """)
    for table in (
        "repair_attempts",
        "repair_verifications",
        "incident_recurrences",
        "fairness_review_records",
    ):
        for verb in ("INSERT", "UPDATE", "DELETE"):
            db.execute(
                f"CREATE TRIGGER IF NOT EXISTS analytics_{table}_{verb.lower()} AFTER {verb} "
                f"ON {table} BEGIN UPDATE analytics_meta SET revision=revision+1 "
                "WHERE singleton=1; END"
            )
