"""100 real triage workflows in a disposable SQLite store; no cloud/auth timing claims."""

import json
import statistics
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from app.core.config import Settings
from app.events.schema import new_event, utcnow
from app.main import create_app
from app.models.incident import Actor
from app.services.sla_service import scheduled_checks


def main():
    with tempfile.TemporaryDirectory(prefix="civiclens-events-") as directory:
        app = create_app(
            Settings(
                _env_file=None,
                app_env="test",
                log_level="ERROR",
                local_db_path=Path(directory) / "bench.db",
            )
        )
        app.state.auth_service.store.initialize()
        work, runner = app.state.work_service.repository, app.state.workflow_service
        repo, now, citizen = runner.repository, utcnow().isoformat(), str(uuid4())
        work.seed(
            {
                "operationId": str(uuid4()),
                "confirmed": True,
                "reason": "Synthetic offline workflow benchmark configuration",
            },
            Actor("benchmark", "ADMIN"),
        )
        with repo.store.connection() as db:
            db.execute(
                "INSERT INTO users VALUES(?,?,?,'unused','CITIZEN',1,1,?,?,NULL)",
                (citizen, "synthetic@example.com", "Synthetic Citizen", now, now),
            )
            for index in range(100):
                db.execute(
                    "INSERT INTO complaints(complaint_id,citizen_id,title,description,category,"
                    "reported_severity,latitude,longitude,status,created_at,updated_at) "
                    "VALUES(?,?,'Synthetic road defect','Synthetic local workflow benchmark "
                    "report only','POTHOLE','LOW',?,77.59,'SUBMITTED',?,?)",
                    (str(uuid4()), citizen, 10 + index * 0.002, now, now),
                )
        dispatch, processing = [], []
        for _ in range(100):
            started = time.perf_counter()
            repo.dispatch_one()
            dispatch.append((time.perf_counter() - started) * 1000)
        started = time.perf_counter()
        for _ in range(100):
            start = time.perf_counter()
            runner.process_one()
            processing.append((time.perf_counter() - start) * 1000)
        elapsed = time.perf_counter() - started
        for _ in range(10):
            if not any(runner.batch(100).values()):
                break
        start = time.perf_counter()
        schedule = scheduled_checks(runner, app.state.sla_service, 100)
        sla_ms = (time.perf_counter() - start) * 1000
        first = repo.listing("workflow")["items"][0]["aggregate_id"]
        event = new_event("ComplaintSubmitted", first)
        start = time.perf_counter()
        for _ in range(100):
            repo.enqueue(event)
        duplicate_ms = (time.perf_counter() - start) * 1000
        runner.process_one()
        notification_times = []
        for _ in range(10):
            event = new_event("ComplaintSubmitted", first)
            start = time.perf_counter()
            repo.notify(
                event,
                citizen,
                "COMPLAINT_RECEIVED",
                "Synthetic notification",
                "Synthetic timing measurement only",
                "COMPLAINT",
                first,
                "/citizen/complaints",
            )
            notification_times.append((time.perf_counter() - start) * 1000)
        recovery_id = str(uuid4())
        with repo.store.connection() as db:
            db.execute(
                "INSERT INTO "
                "complaints(complaint_id,citizen_id,title,description,category,reported_s"
                "everity,latitude,longitude,status,created_at,updated_at) "
                "VALUES(?,?,'Synthetic retry fault report','Synthetic transient retry "
                "measurement only','POTHOLE','LOW',20,70,'SUBMITTED',?,?)",
                (recovery_id, citizen, now, now),
            )

        def fault(step):
            if step == "RunDuplicateDetection":
                raise OSError("Controlled benchmark fault")

        runner.fault = fault
        start = time.perf_counter()
        runner.batch(10)
        failed_attempt_ms = (time.perf_counter() - start) * 1000
        runner.fault = None
        from datetime import timedelta

        advanced = utcnow() + timedelta(seconds=3)
        repo.clock = lambda: advanced
        start = time.perf_counter()
        runner.batch(10)
        recovery_ms = (time.perf_counter() - start) * 1000
        repo.clock = utcnow
        for _ in range(10):
            if not any(runner.batch(100).values()):
                break
        with repo.store.connection() as db:
            db.execute(
                "INSERT INTO "
                "event_queue(message_id,event_id,consumer,envelope,created_at) "
                "VALUES(?,?,'triage','{}',?)",
                (str(uuid4()), str(uuid4()), now),
            )
        start = time.perf_counter()
        runner.process_one()
        dead_ms = (time.perf_counter() - start) * 1000
        assert repo.summary()["queue"]["DEAD"] == 1
        print(
            json.dumps(
                {
                    "syntheticComplaints": 101,
                    "normalWorkflows": 100,
                    "recoveredWorkflow": 1,
                    "simulatedRetryClockAdvanceSeconds": 3,
                    "failedAttemptMs": round(failed_attempt_ms, 3),
                    "recoveryWorkflowMs": round(recovery_ms, 3),
                    "notificationMedianMs": round(statistics.median(notification_times), 3),
                    "deadLetterProcessingMs": round(dead_ms, 3),
                    "dispatchMedianMs": round(statistics.median(dispatch), 3),
                    "workflowMedianMs": round(statistics.median(processing), 3),
                    "workflowsPerSecond": round(100 / elapsed, 3),
                    "slaSweepMs": round(sla_ms, 3),
                    "slaChecked": schedule["sla"]["checked"],
                    "duplicateEnqueue100Ms": round(duplicate_ms, 3),
                    "summary": repo.summary(),
                    "scope": "Disposable local SQLite only; no AWS performance claim",
                }
            )
        )


if __name__ == "__main__":
    main()
