"""Disposable 600-record SQLite benchmark; no developer data, AWS, or production claims."""

import json
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter
from uuid import uuid4

from app.models.incident import Actor
from app.scripts.benchmark_phase5 import seed
from app.scripts.evaluate_clustering import environment
from app.services.incident_reconciliation import reconcile


def benchmark(count=600):
    with TemporaryDirectory(prefix="civiclens-incident-bench-") as folder:
        service = environment(Path(folder))
        seed(service.repository.store, count)
        ids = service.repository.source_ids("", count)
        times = []
        for identity in ids:
            start = perf_counter()
            service.ensure_singleton(identity)
            times.append((perf_counter() - start) * 1000)
        with service.repository.store.connection() as db:
            eligible = [
                row[0]
                for row in db.execute(
                    "SELECT incident_id FROM complaints "
                    "WHERE category='POTHOLE' AND status='SUBMITTED' "
                    "AND latitude=12.96 AND longitude=77.58 LIMIT 6"
                )
            ]
        target = service.require(eligible[0]).model_dump(mode="json")
        merge_times = []
        for identity in eligible[1:]:
            source = service.require(identity)
            data = {
                "operationId": str(uuid4()),
                "sourceIncidentId": identity,
                "expectedSourceVersion": source.version,
                "targetIncidentId": target["incidentId"],
                "expectedTargetVersion": target["version"],
                "confirmed": True,
                "physicalIssueConfirmed": True,
                "reason": "Synthetic benchmark physical-identity review",
            }
            start = perf_counter()
            target = service.mutate("MERGE", data, Actor("benchmark-admin", "ADMIN"))
            merge_times.append((perf_counter() - start) * 1000)
        start = perf_counter()
        members = service.members(target["incidentId"])
        membership_ms = (perf_counter() - start) * 1000
        start = perf_counter()
        split = service.mutate(
            "SPLIT",
            {
                "operationId": str(uuid4()),
                "sourceIncidentId": target["incidentId"],
                "expectedSourceVersion": target["version"],
                "complaintIds": [members[-1].complaint.complaintId],
                "confirmed": True,
                "reason": "Synthetic benchmark split correction",
            },
            Actor("benchmark-admin", "ADMIN"),
        )
        split_ms = (perf_counter() - start) * 1000
        start = perf_counter()
        page, _ = service.repository.catalog({"sort": "newest", "status": "OPEN"}, 20, None)
        list_ms = (perf_counter() - start) * 1000
        start = perf_counter()
        report = reconcile(service, 500)
        reconciliation_ms = (perf_counter() - start) * 1000
        start = perf_counter()
        for identity in ids[:500]:
            service.ensure_singleton(identity)
        backfill_ms = (perf_counter() - start) * 1000
        start = perf_counter()
        matching = service.matching.process_one(members[0].complaint.complaintId)
        match_ms = (perf_counter() - start) * 1000
        start = perf_counter()
        clustering = service.process_one(members[0].complaint.complaintId)
        cluster_ms = (perf_counter() - start) * 1000
        return {
            "syntheticOnly": True,
            "records": count,
            "singletonMedianMs": round(median(times), 3),
            "singletonTotalMs": round(sum(times), 3),
            "mergeMedianMs": round(median(merge_times), 3),
            "splitMs": round(split_ms, 3),
            "membershipLookupMs": round(membership_ms, 3),
            "reporterCount": split["uniqueReporterCount"],
            "list20Ms": round(list_ms, 3),
            "listReturned": len(page),
            "reconcile500Ms": round(reconciliation_ms, 3),
            "reconciliationIssues": len(report["issues"]),
            "idempotentBackfill500Ms": round(backfill_ms, 3),
            "matchingMs": round(match_ms, 3),
            "clusteringCheckMs": round(cluster_ms, 3),
            "clusteringDecision": clustering.get("decision"),
            "matchingCompared": matching.get("compared"),
            "limitations": "Serial local SQLite; no AWS/concurrency capacity or SLA claim",
        }


if __name__ == "__main__":
    print(json.dumps(benchmark(), indent=2))
