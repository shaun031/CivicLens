"""600 synthetic incidents, real SQLite scoring/ranking/history/merge/split/aging, no real data."""

import json
import tracemalloc
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter
from uuid import uuid4

from app.core.config import Settings
from app.models.incident import Actor
from app.scripts.benchmark_phase5 import seed
from app.scripts.evaluate_clustering import environment
from app.services.priority_service import build_priority_service


def benchmark(count=600):
    with TemporaryDirectory(prefix="civiclens-priority-benchmark-") as directory:
        incidents = environment(Path(directory))
        seed(incidents.repository.store, count)
        for identity in incidents.repository.source_ids("", count):
            incidents.ensure_singleton(identity)
        service = build_priority_service(Settings(_env_file=None, app_env="test"), incidents)
        now = datetime(2026, 11, 20, tzinfo=UTC)
        service.clock = lambda: now
        ids = service.repository.batch("", count)
        tracemalloc.start()
        times = []
        start = perf_counter()
        for identity in ids:
            single = perf_counter()
            service.calculate(identity)
            times.append((perf_counter() - single) * 1000)
        elapsed = perf_counter() - start
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        def duration(operation):
            before = perf_counter()
            value = operation()
            return round((perf_counter() - before) * 1000, 3), value

        queue_ms, page = duration(
            lambda: service.repository.queue(
                {"status": "OPEN"}, 20, None, None, now.timestamp(), service.config.version
            )
        )
        filter_ms, filtered = duration(
            lambda: service.repository.queue(
                {"status": "OPEN", "category": "POTHOLE", "minSeverity": 2},
                20,
                None,
                None,
                now.timestamp(),
                service.config.version,
            )
        )
        history_ms, _ = duration(lambda: service.repository.history(ids[0], 20, None))
        with incidents.repository.store.connection() as db:
            eligible = [
                r[0]
                for r in db.execute(
                    "SELECT incident_id FROM complaints WHERE category='POTHOLE' "
                    "AND status='SUBMITTED' AND latitude=12.96 AND longitude=77.58 LIMIT 2"
                )
            ]
        a, b = [incidents.require(identity).model_dump(mode="json") for identity in eligible]

        def merge():
            merged = incidents.mutate(
                "MERGE",
                {
                    "operationId": str(uuid4()),
                    "sourceIncidentId": b["incidentId"],
                    "targetIncidentId": a["incidentId"],
                    "expectedSourceVersion": b["version"],
                    "expectedTargetVersion": a["version"],
                    "reason": "Synthetic benchmark inspected physical issue",
                    "confirmed": True,
                    "physicalIssueConfirmed": True,
                },
                Actor("benchmark-admin", "ADMIN"),
            )
            service.calculate(a["incidentId"])
            return merged

        merge_ms, merged = duration(merge)

        def split():
            member = incidents.members(merged["incidentId"])[-1]
            new = incidents.mutate(
                "SPLIT",
                {
                    "operationId": str(uuid4()),
                    "sourceIncidentId": merged["incidentId"],
                    "expectedSourceVersion": merged["version"],
                    "complaintIds": [member.complaint.complaintId],
                    "confirmed": True,
                    "reason": "Synthetic split and independent score recalculation",
                },
                Actor("benchmark-admin", "ADMIN"),
            )
            service.calculate(merged["incidentId"])
            service.calculate(new["incidentId"])

        split_ms, _ = duration(split)
        now += timedelta(days=1)
        aging_ms, _ = duration(lambda: [service.calculate(identity) for identity in ids[:100]])
        with service.repository.store.connection() as db:
            plan = [
                row[3]
                for row in db.execute(
                    "EXPLAIN QUERY PLAN SELECT incident_id FROM incident_priority "
                    "ORDER BY urgent_hazard DESC,effective_score DESC,"
                    "unresolved_seconds DESC,incident_id LIMIT 20"
                )
            ]
        return {
            "syntheticOnly": True,
            "incidents": len(ids),
            "bulkMs": round(elapsed * 1000, 3),
            "medianCalculationMs": round(median(times), 3),
            "incidentsPerSecond": round(len(ids) / elapsed, 2),
            "peakTracedBytes": peak,
            "queue20Ms": queue_ms,
            "queueRows": len(page[0]),
            "filteredQueueMs": filter_ms,
            "filteredRows": len(filtered[0]),
            "history20Ms": history_ms,
            "mergeAndRecalculateMs": merge_ms,
            "splitAndRecalculateMs": split_ms,
            "aging100Ms": aging_ms,
            "rankIndexPlan": plan,
            "databaseOperations": "Bounded snapshot + guarded write; no citywide input load",
            "limitations": "Serial SQLite; traced Python allocations only; no cloud/SLA claim",
        }


if __name__ == "__main__":
    print(json.dumps(benchmark(), indent=2))
