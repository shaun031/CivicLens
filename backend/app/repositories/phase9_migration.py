def migrate_phase9(db):
    """Additive work sidecars; triggers participate in the existing clustering transaction."""
    db.executescript("""
        BEGIN IMMEDIATE;
        CREATE TABLE IF NOT EXISTS work_meta (
            singleton INTEGER PRIMARY KEY CHECK(singleton=1), revision INTEGER NOT NULL);
        INSERT OR IGNORE INTO work_meta VALUES(1,0);
        CREATE TABLE IF NOT EXISTS departments (
            id TEXT PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
            description TEXT NOT NULL, active INTEGER NOT NULL CHECK(active IN(0,1)),
            areas TEXT NOT NULL CHECK(json_valid(areas)), version INTEGER NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            created_by TEXT NOT NULL, updated_by TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS routing_rules (
            id TEXT PRIMARY KEY, category TEXT NOT NULL,
            department_id TEXT NOT NULL REFERENCES departments(id),
            precedence INTEGER NOT NULL CHECK(precedence BETWEEN 0 AND 1000),
            active INTEGER NOT NULL CHECK(active IN(0,1)), version INTEGER NOT NULL,
            UNIQUE(category,department_id));
        CREATE INDEX IF NOT EXISTS routing_category ON routing_rules(category,active);
        CREATE TABLE IF NOT EXISTS officer_memberships (
            id TEXT PRIMARY KEY, officer_id TEXT NOT NULL REFERENCES users(id),
            department_id TEXT NOT NULL REFERENCES departments(id),
            active INTEGER NOT NULL CHECK(active IN(0,1)),
            availability TEXT NOT NULL
                CHECK(availability IN('AVAILABLE','BUSY','UNAVAILABLE','ON_LEAVE')),
            capacity REAL CHECK(capacity>0 AND capacity<=10000),
            areas TEXT NOT NULL CHECK(json_valid(areas)), version INTEGER NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, assigned_by TEXT NOT NULL,
            UNIQUE(officer_id,department_id));
        CREATE INDEX IF NOT EXISTS membership_department
            ON officer_memberships(department_id,active);
        CREATE INDEX IF NOT EXISTS membership_officer ON officer_memberships(officer_id,active);
        CREATE TABLE IF NOT EXISTS incident_assignments (
            incident_id TEXT PRIMARY KEY REFERENCES incidents(incident_id),
            department_id TEXT REFERENCES departments(id), officer_id TEXT REFERENCES users(id),
            status TEXT NOT NULL DEFAULT 'UNASSIGNED'
                CHECK(status IN('UNASSIGNED','DEPARTMENT_ASSIGNED','OFFICER_ASSIGNED',
                                'IN_PROGRESS','NEEDS_REVIEW')),
            method TEXT, rule_version TEXT, explanation TEXT NOT NULL DEFAULT '[]',
            version INTEGER NOT NULL DEFAULT 0, source_version INTEGER NOT NULL DEFAULT 0,
            route_pending INTEGER NOT NULL DEFAULT 1, available_at REAL NOT NULL DEFAULT 0,
            percentage INTEGER NOT NULL DEFAULT 0 CHECK(percentage BETWEEN 0 AND 100),
            assigned_at TEXT, updated_at TEXT, assigned_by TEXT,
            CHECK(officer_id IS NULL OR department_id IS NOT NULL));
        CREATE INDEX IF NOT EXISTS assignment_department
            ON incident_assignments(department_id,status,incident_id);
        CREATE INDEX IF NOT EXISTS assignment_officer
            ON incident_assignments(officer_id,status,incident_id);
        CREATE INDEX IF NOT EXISTS assignment_pending
            ON incident_assignments(route_pending,available_at,incident_id);
        CREATE TABLE IF NOT EXISTS work_history (
            event_id TEXT PRIMARY KEY, entity_id TEXT NOT NULL,
            operation_id TEXT REFERENCES incident_operations(operation_id),
            kind TEXT NOT NULL, actor_id TEXT NOT NULL, actor_type TEXT NOT NULL,
            reason TEXT NOT NULL, before_state TEXT NOT NULL CHECK(json_valid(before_state)),
            after_state TEXT NOT NULL CHECK(json_valid(after_state)), created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS work_history_entity
            ON work_history(entity_id,created_at,event_id);
        INSERT OR IGNORE INTO incident_assignments(incident_id) SELECT incident_id FROM incidents;
        CREATE TRIGGER IF NOT EXISTS work_incident_created AFTER INSERT ON incidents BEGIN
            INSERT OR IGNORE INTO incident_assignments(incident_id) VALUES(NEW.incident_id);
        END;
        CREATE TRIGGER IF NOT EXISTS work_membership_changed
        AFTER INSERT ON incident_membership_events BEGIN
            INSERT INTO work_history SELECT lower(hex(randomblob(16))),incident_id,NULL,
                'ASSIGNMENT_REVIEW_REQUIRED','membership-transaction','SYSTEM',
                'Incident membership changed; responsibility and officer must be reviewed',
                json_object('departmentId',department_id,'officerId',officer_id,'status',status,
                            'version',version),
                json_object('departmentId',NULL,'officerId',NULL,'status','NEEDS_REVIEW',
                            'version',version+1),NEW.created_at
                FROM incident_assignments
                WHERE incident_id IN(NEW.previous_incident_id,NEW.new_incident_id)
                AND (department_id IS NOT NULL OR officer_id IS NOT NULL);
            UPDATE incident_assignments
                SET department_id=NULL,officer_id=NULL,status='NEEDS_REVIEW',
                percentage=0,version=version+1,route_pending=1,available_at=0,
                method=CASE WHEN department_id IS NOT NULL OR officer_id IS NOT NULL
                    OR method='REVIEW_LOCK' THEN 'REVIEW_LOCK' ELSE method END,
                explanation='["Membership changed; administrative review required"]'
                WHERE incident_id IN(NEW.previous_incident_id,NEW.new_incident_id);
        END;
        CREATE TRIGGER IF NOT EXISTS work_lifecycle_changed AFTER UPDATE OF status ON incidents
        WHEN OLD.status<>NEW.status BEGIN
            INSERT INTO work_history SELECT lower(hex(randomblob(16))),incident_id,NULL,
                'LIFECYCLE_REVIEW_REQUIRED','lifecycle-transaction','SYSTEM',
                'Canonical incident lifecycle changed; assignment suspended pending review',
                json_object('departmentId',department_id,'officerId',officer_id,'status',status),
                json_object('departmentId',department_id,'officerId',NULL,'status','NEEDS_REVIEW'),
                NEW.updated_at FROM incident_assignments WHERE incident_id=NEW.incident_id;
            UPDATE incident_assignments SET officer_id=NULL,status='NEEDS_REVIEW',percentage=0,
                version=version+1,route_pending=1,available_at=0 WHERE incident_id=NEW.incident_id;
        END;
        CREATE TRIGGER IF NOT EXISTS work_account_changed
        AFTER UPDATE OF role,is_active,is_verified ON users
        WHEN NEW.role<>'OFFICER' OR NEW.is_active=0 OR NEW.is_verified=0 BEGIN
            INSERT INTO work_history SELECT lower(hex(randomblob(16))),incident_id,NULL,
                'OFFICER_ELIGIBILITY_LOST','account-transaction','SYSTEM',
                'Assigned account is no longer an active verified officer',
                json_object('officerId',officer_id,'status',status),
                json_object('officerId',NULL,'status','NEEDS_REVIEW'),NEW.updated_at
                FROM incident_assignments WHERE officer_id=NEW.id;
            UPDATE incident_assignments SET officer_id=NULL,status='NEEDS_REVIEW',
                version=version+1 WHERE officer_id=NEW.id;
        END;
        CREATE TRIGGER IF NOT EXISTS work_assignment_revision
        AFTER UPDATE ON incident_assignments BEGIN
            UPDATE work_meta SET revision=revision+1 WHERE singleton=1;
        END;
        CREATE TRIGGER IF NOT EXISTS work_priority_revision AFTER UPDATE ON incident_priority BEGIN
            UPDATE work_meta SET revision=revision+1 WHERE singleton=1;
        END;
        CREATE TRIGGER IF NOT EXISTS work_created_revision
        AFTER INSERT ON incident_assignments BEGIN
            UPDATE work_meta SET revision=revision+1 WHERE singleton=1;
        END;
        PRAGMA user_version=7;
        COMMIT;
    """)
