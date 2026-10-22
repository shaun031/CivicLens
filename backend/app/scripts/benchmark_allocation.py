"""Real SQLite synthetic benchmark; all records stay in a disposable temporary directory."""

import json
import statistics
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from app.core.config import Settings
from app.main import create_app
from app.models.incident import Actor
from app.models.user import Role
from app.schemas.auth import RegisterInput


def main():
    with tempfile.TemporaryDirectory(prefix="civiclens-allocation-") as directory:
        settings = Settings(
            _env_file=None, app_env="test", local_db_path=Path(directory) / "bench.db"
        )
        app = create_app(settings)
        app.state.auth_service.store.initialize()
        repo = app.state.work_service.repository
        actor = Actor("synthetic-benchmark", "ADMIN")

        def common():
            return {
                "operationId": str(uuid4()),
                "confirmed": True,
                "reason": "Synthetic benchmark municipal allocation operation",
            }

        repo.seed(common(), actor)
        department = next(
            d["id"] for d in repo.departments()["items"] if d["code"] == "ROAD_MAINTENANCE"
        )
        now = repo.clock().isoformat()
        users = []
        for index in range(12):
            user = app.state.auth_service.register(
                RegisterInput(
                    display_name=f"Synthetic Officer {index}",
                    email=f"officer{index}@example.com",
                    password="Synthetic benchmark passphrase 1234",
                    confirm_password="Synthetic benchmark passphrase 1234",
                ),
                Role.OFFICER,
            )
            users.append(user.id)
            repo.save_membership(
                department,
                common()
                | {
                    "officerId": user.id,
                    "active": True,
                    "expectedVersion": 0,
                    "capacity": 100,
                    "areas": [],
                    "availability": "ON_LEAVE" if index == 11 else "AVAILABLE",
                },
                actor,
            )
        citizen = str(uuid4())
        with repo.store.connection() as db:
            db.execute(
                "INSERT INTO users VALUES(?,?,?,'unused','CITIZEN',1,1,?,?,NULL)",
                (citizen, "synthetic@example.com", "Synthetic Citizen", now, now),
            )
            for _ in range(300):
                report, identity = str(uuid4()), str(uuid4())
                db.execute(
                    "INSERT INTO complaints(complaint_id,citizen_id,title,description,category,"
                    "reported_severity,latitude,longitude,status,created_at,updated_at) "
                    "VALUES(?,?,'Synthetic road defect',"
                    "'Synthetic road defect for a bounded benchmark',"
                    "'POTHOLE','LOW',12.97,77.59,'SUBMITTED',?,?)",
                    (report, citizen, now, now),
                )
                db.execute(
                    "INSERT INTO incidents VALUES(?, 'Synthetic road defect',"
                    "'Synthetic allocation benchmark','POTHOLE',12.97,77.59,'OPEN',"
                    "?,1,1,?,?,?,?,NULL,NULL,1)",
                    (identity, report, now, now, now, now),
                )
                db.execute(
                    "UPDATE complaints SET incident_id=? WHERE complaint_id=?", (identity, report)
                )
        samples = {
            key: []
            for key in (
                "routing",
                "recommendation",
                "assignment",
                "officerQueue",
                "departmentQueue",
                "workload",
                "reassignment",
            )
        }

        def measured(key, callback):
            start = time.perf_counter()
            result = callback()
            samples[key].append((time.perf_counter() - start) * 1000)
            return result

        with repo.store.connection() as db:
            identities = [
                r[0] for r in db.execute("SELECT incident_id FROM incidents ORDER BY incident_id")
            ]
        for index, identity in enumerate(identities):
            app.state.priority_service.calculate(identity)
            payload = common() | {
                "expectedIncidentVersion": 1,
                "expectedAssignmentVersion": 0,
                "mode": "MANUAL_APPROVAL",
            }
            assigned = measured(
                "routing", lambda i=identity, p=payload: repo.assign(i, "ROUTE", p, actor)
            )
            measured("recommendation", lambda i=identity: repo.detail(i)["recommendations"])
            payload = common() | {
                "expectedIncidentVersion": 1,
                "expectedAssignmentVersion": assigned["version"],
                "officerId": users[index % 10],
                "capacityOverride": False,
            }
            measured(
                "assignment", lambda i=identity, p=payload: repo.assign(i, "OFFICER", p, actor)
            )
        for _ in range(20):
            measured("officerQueue", lambda: repo.queue({"limit": 20}, officer=users[0]))
            measured(
                "departmentQueue", lambda: repo.queue({"limit": 20, "departmentId": department})
            )
            measured("workload", lambda: repo.department_detail(department))
        state = repo.detail(identities[0])
        measured(
            "reassignment",
            lambda: repo.assign(
                identities[0],
                "REASSIGN",
                common()
                | {
                    "expectedIncidentVersion": 1,
                    "expectedAssignmentVersion": state["assignment"]["version"],
                    "departmentId": department,
                    "officerId": users[10],
                },
                actor,
            ),
        )
        print(
            json.dumps(
                {
                    "incidents": 300,
                    "officers": 12,
                    "medianMilliseconds": {
                        key: round(statistics.median(values), 3) for key, values in samples.items()
                    },
                    "note": "Serial local measurements, not labor estimates or a cloud SLA",
                }
            )
        )


if __name__ == "__main__":
    main()
