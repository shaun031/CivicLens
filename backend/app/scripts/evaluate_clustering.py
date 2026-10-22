"""Actual local algorithms/repositories; oracle review is disclosed, not claimed as automation."""

import json
from collections import Counter, defaultdict
from dataclasses import replace
from itertools import combinations
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter
from uuid import NAMESPACE_URL, uuid5

from app.algorithms.clustering_evaluation_data import dataset
from app.algorithms.duplicate_detection.image_similarity import compare
from app.algorithms.duplicate_detection.matching_engine import match
from app.core.config import Settings
from app.models.complaint import Complaint, ComplaintImage
from app.models.incident import Actor, IncidentError
from app.repositories.auth_store import AuthStore
from app.repositories.duplicate_candidate_repository import match_input
from app.scripts.evaluate_matching import synthetic_image
from app.services.complaint_factory import build_complaint_service
from app.services.duplicate_detection_service import build_duplicate_service
from app.services.incident_service import build_incident_service


def pairwise_metrics(truth, predictions):
    counts = Counter()
    for first, second in combinations(truth, 2):
        same_truth, same_prediction = (
            truth[first] == truth[second],
            predictions[first] == predictions[second],
        )
        counts[
            "TP"
            if same_truth and same_prediction
            else "FN"
            if same_truth
            else "FP"
            if same_prediction
            else "TN"
        ] += 1
    tp, fp, fn = counts["TP"], counts["FP"], counts["FN"]
    p, r = tp / (tp + fp) if tp + fp else 0, tp / (tp + fn) if tp + fn else 0
    buckets = defaultdict(Counter)
    for identity, cluster in predictions.items():
        buckets[cluster][truth[identity]] += 1
    purity = sum(max(bucket.values()) for bucket in buckets.values()) / len(truth)
    return {
        "TP": tp,
        "FP": fp,
        "TN": counts["TN"],
        "FN": fn,
        "precision": round(p, 4),
        "recall": round(r, 4),
        "f1": round(2 * p * r / (p + r), 4) if p + r else 0,
        "incorrectMergedPairs": fp,
        "trueDuplicatePairsSeparated": fn,
        "purity": round(purity, 4),
        "predictedClusters": len(buckets),
    }


def environment(folder):
    settings = Settings(
        _env_file=None, app_env="test", local_db_path=Path(folder) / "evaluation.db"
    )
    store = AuthStore(settings.local_db_path)
    store.initialize()
    complaints = build_complaint_service(settings, store)
    matching = build_duplicate_service(settings, complaints)
    incidents = build_incident_service(settings, complaints, matching)
    matching.incidents = incidents
    return incidents


def insert_report(service, report, order, family_number):
    identity = str(uuid5(NAMESPACE_URL, f"clustering-eval-v1/{report.id}"))
    owner = str(uuid5(NAMESPACE_URL, f"clustering-eval-v1/{report.reporter}"))
    created = f"2026-10-20T00:00:{order:02d}.000Z"
    with service.repository.store.connection() as db:
        db.execute(
            "INSERT OR IGNORE INTO users"
            "(id,email,display_name,password_hash,role,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                owner,
                f"{owner}@example.invalid",
                "Synthetic only",
                "NO_LOGIN_EVALUATION",
                "CITIZEN",
                created,
                created,
            ),
        )
    images = []
    if report.image is not None:
        image_id = str(uuid5(NAMESPACE_URL, identity + "/image"))
        key = f"complaints/{identity}/{image_id}.jpg"
        content = synthetic_image(report.image)
        service.matching.storage.put(key, content)
        images = [
            ComplaintImage(
                imageId=image_id,
                storageKey=key,
                fileSize=len(content),
                createdAt=created,
                url=f"/complaints/{identity}/images/{image_id}",
            )
        ]
    complaint = Complaint(
        complaintId=identity,
        citizenId=owner,
        title=report.title,
        description=report.title + ". Synthetic local evaluation only, not a municipal record.",
        category=report.category,
        reportedSeverity="MEDIUM",
        latitude=12.9 + family_number * 0.01 + report.meters / 111195.08,
        longitude=77.5,
        status=report.status,
        createdAt=created,
        updatedAt=created,
        images=images,
    )
    service.repository.complaints.create(
        complaint, str(uuid5(NAMESPACE_URL, identity + "/request")), identity
    )
    return identity


def evaluate(split):
    reports = [row for row in dataset() if row.split == split]
    families = {
        name: index for index, name in enumerate(dict.fromkeys(row.family for row in reports))
    }
    truth = {row.id: row.truth for row in reports}
    predictions, reviews, durations = {}, 0, []
    baseline_edges = []
    with TemporaryDirectory(prefix="civiclens-cluster-evaluation-") as folder:
        service = environment(folder)
        service.config = replace(service.config, mode="CONSERVATIVE_AUTO_LINK")
        records = {}
        for index, row in enumerate(reports):
            started = perf_counter()
            identity = insert_report(service, row, index, families[row.family])
            records[row.id] = service.require_member(identity).complaint
            service.matching.process_one(identity)
            result = service.process_one(identity)
            assert result and "errorCategory" not in result, result
            reviews += bool(result["recommendations"] and result["decision"] != "AUTOMATIC_LINK")
            durations.append((perf_counter() - started) * 1000)
        for row in reports:
            identity = records[row.id].complaintId
            predictions[row.id] = service.require_member(identity).complaint.incidentId
        # Deliberately naive edge baseline uses Phase6 numeric similarity, ignores cohesion guards.
        parent = {row.id: row.id for row in reports}

        def root(identity):
            while parent[identity] != identity:
                identity = parent[identity]
            return identity

        hashes = {key: service.matching.fingerprints(value) for key, value in records.items()}
        for first, second in combinations(reports, 2):
            if first.family != second.family:
                continue
            a, b = records[first.id], records[second.id]
            result = match(
                match_input(a),
                match_input(b),
                service.matching.config,
                compare(hashes[first.id], hashes[second.id]),
            )
            if (
                result.combinedScore >= 0.80
                and result.categoryCompatibility != "INCOMPATIBLE"
                and result.distanceMeters
                <= min(
                    service.matching.config.radius(a.category),
                    service.matching.config.radius(b.category),
                )
                and a.status != "RESOLVED"
                and b.status != "RESOLVED"
            ):
                parent[root(first.id)] = root(second.id)
                baseline_edges.append((first.id, second.id))
        naive = {row.id: root(row.id) for row in reports}
    with TemporaryDirectory(prefix="civiclens-oracle-review-") as folder:
        service = environment(folder)
        grouped, oracle, merge_ms, rejected = {}, {}, [], 0
        for index, row in enumerate(reports):
            identity = insert_report(service, row, index, families[row.family])
            incident = service.ensure_singleton(identity)
            if row.truth in grouped:
                target = service.require(grouped[row.truth]).model_dump(mode="json")
                data = {
                    "operationId": str(uuid5(NAMESPACE_URL, row.id + "/oracle")),
                    "sourceIncidentId": incident["incidentId"],
                    "expectedSourceVersion": incident["version"],
                    "targetIncidentId": target["incidentId"],
                    "expectedTargetVersion": target["version"],
                    "confirmed": True,
                    "physicalIssueConfirmed": True,
                    "reason": "Simulated oracle review knows the synthetic physical ground truth",
                }
                started = perf_counter()
                try:
                    service.mutate("MERGE", data, Actor("synthetic-oracle", "ADMIN"))
                except IncidentError:
                    rejected += 1
                merge_ms.append((perf_counter() - started) * 1000)
            else:
                grouped[row.truth] = incident["incidentId"]
        for row in reports:
            identity = str(uuid5(NAMESPACE_URL, f"clustering-eval-v1/{row.id}"))
            oracle[row.id] = service.require_member(identity).complaint.incidentId
    return {
        "reports": len(reports),
        "families": len(families),
        "connectedComponents": pairwise_metrics(truth, naive),
        "conservativeAllMember": pairwise_metrics(truth, predictions),
        "reviewOnlySimulatedOracle": pairwise_metrics(truth, oracle),
        "reportsHeldForReview": reviews,
        "oracleActionsRejectedBySafetyBounds": rejected,
        "processingMedianMsPerComplaint": round(median(durations), 3),
        "oracleMergeMedianMs": round(median(merge_ms), 3) if merge_ms else None,
        "naiveEdgeCount": len(baseline_edges),
    }


def main():
    print(
        json.dumps(
            {
                "dataset": "synthetic-physical-groups-v1",
                "totalReports": len(dataset()),
                "tuning": evaluate("tuning"),
                "heldOut": evaluate("evaluation"),
                "selection": "Prototype defaults retained; no optimization on held-out families",
                "limitations": "Oracle approvals use ground truth unavailable to matching. "
                "Synthetic identities/images/GPS only; operational default remains REVIEW_ONLY.",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
