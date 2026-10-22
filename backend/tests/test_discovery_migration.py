from pathlib import Path

from app.core.config import Settings
from app.integrations.database.sqlite_complaints import SQLiteComplaints
from app.models.discovery import SearchFilters
from app.repositories.auth_store import AuthStore
from app.repositories.phase5_migration import migrate_phase5
from app.scripts.benchmark_phase5 import seed


def test_v2_migration_backfills_fts_and_preserves_accounts_and_complaints(tmp_path: Path):
    store = AuthStore(tmp_path / "migrate.db")
    store.initialize()
    owner = seed(store, 100)
    with store.connection() as db:
        account = tuple(db.execute("SELECT id,password_hash FROM users ORDER BY id").fetchone())
        complaints = [
            tuple(row) for row in db.execute("SELECT * FROM complaints ORDER BY complaint_id")
        ]
        # Reconstruct the actual previous schema on this disposable fixture only.
        db.executescript(
            "DROP TABLE publication_audit; DROP TABLE complaint_publications; "
            "DROP TRIGGER complaints_search_insert; DROP TRIGGER complaints_search_update; "
            "DROP TRIGGER complaints_search_delete; DROP TABLE complaint_search; "
            "DROP INDEX complaints_owner_category; DROP INDEX complaints_owner_status; "
            "PRAGMA user_version=2;"
        )
    store.initialize()
    store.initialize()
    with store.connection() as db:
        assert (
            tuple(db.execute("SELECT id,password_hash FROM users ORDER BY id").fetchone())
            == account
        )
        assert [
            tuple(row) for row in db.execute("SELECT * FROM complaints ORDER BY complaint_id")
        ] == complaints
        assert db.execute("PRAGMA user_version").fetchone()[0] == 8
        assert db.execute("SELECT COUNT(*) FROM complaint_search").fetchone()[0] == 100
    repository = SQLiteComplaints(
        store, Settings(_env_file=None, app_env="test", local_db_path=store.path)
    )
    assert repository.list(owner, 20, None, SearchFilters(q="surface")).total == 60


def test_migration_without_fts_keeps_safe_search_operational(tmp_path):
    store = AuthStore(tmp_path / "fallback.db")
    store.initialize()
    owner = seed(store, 10)
    with store.connection() as db:
        db.executescript(
            "DROP TRIGGER complaints_search_insert; DROP TRIGGER complaints_search_update; "
            "DROP TRIGGER complaints_search_delete; DROP TABLE complaint_search; "
            "PRAGMA user_version=2;"
        )
        migrate_phase5(db, enable_fts=False)
    repository = SQLiteComplaints(
        store, Settings(_env_file=None, app_env="test", local_db_path=store.path)
    )
    assert repository.list(owner, 20, None, SearchFilters(q="SURFACE")).total == 6


def test_geographic_and_owner_filter_query_plans_use_indexes(tmp_path):
    store = AuthStore(tmp_path / "plans.db")
    store.initialize()
    owner = seed(store, 100)
    with store.connection() as db:
        geo = [
            row[3]
            for row in db.execute(
                "EXPLAIN QUERY PLAN SELECT public_issue_id FROM complaint_publications "
                "WHERE publication_status='PUBLISHED' AND public_geo_cell=?",
                ("g05:2059:5151",),
            )
        ]
        filters = [
            row[3]
            for row in db.execute(
                "EXPLAIN QUERY PLAN SELECT complaint_id FROM complaints "
                "WHERE citizen_id=? AND category=? ORDER BY created_at,complaint_id LIMIT 20",
                (owner, "POTHOLE"),
            )
        ]
        assert any("publications_geo" in step and "SEARCH" in step for step in geo)
        assert any("complaints_owner_category" in step and "SEARCH" in step for step in filters)


def test_fts_delete_trigger_removes_deleted_search_entry(tmp_path):
    store = AuthStore(tmp_path / "delete.db")
    store.initialize()
    seed(store, 10)
    with store.connection() as db:
        row = db.execute("SELECT rowid,complaint_id FROM complaints LIMIT 1").fetchone()
        # Delete only this disposable unassigned report's durable outboxes first.
        db.execute("DELETE FROM clustering_jobs WHERE source_id=?", (row["complaint_id"],))
        db.execute("DELETE FROM matching_jobs WHERE source_id=?", (row["complaint_id"],))
        db.execute("DELETE FROM complaints WHERE complaint_id=?", (row["complaint_id"],))
        assert (
            db.execute(
                "SELECT rowid FROM complaint_search WHERE rowid=?", (row["rowid"],)
            ).fetchone()
            is None
        )
