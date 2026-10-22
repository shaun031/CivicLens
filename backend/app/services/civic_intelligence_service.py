import copy
import hashlib
import json
import logging
import sqlite3
from uuid import uuid4

from app.algorithms.duplicate_detection.image_similarity import compare, fingerprint
from app.algorithms.recurrence import evaluate
from app.analytics.fairness import compare_areas
from app.integrations.storage.base import StorageCollision, StorageUnavailable
from app.models.incident import IncidentError
from app.repositories.civic_intelligence_repository import require

logger = logging.getLogger(__name__)


class CivicIntelligenceService:
    def __init__(self, repository, complaints, analytics, settings, priorities):
        self.repository, self.complaints, self.analytics = repository, complaints, analytics
        self.settings, self.priorities = settings, priorities
        self._fairness_cache = {}

    def upload_action(self, kind, identity, data, actor, uploads):
        require(len(uploads) <= 2, "At most two images are accepted", 422)
        images, staged = [], []
        # Fingerprint original bytes; reused operation IDs cannot replace evidence.
        data = data | {
            "evidenceFingerprint": hashlib.sha256(
                b"".join(
                    hashlib.sha256(u.content).digest() + u.content_type.encode() for u in uploads
                )
            ).hexdigest()
        }
        sanitized = [self.complaints.evidence.sanitize(u) for u in uploads]
        try:
            for content in sanitized:
                image_id = str(uuid4())
                # Reuse existing private evidence namespace and least-privilege S3 IAM.
                key = f"complaints/{uuid4()}/{image_id}.jpg"
                staged.append(key)
                try:
                    self.complaints.storage.put(key, content)
                except StorageCollision:
                    staged.pop()  # A collision belongs to an earlier request; never delete it.
                    raise
                images.append({"imageId": image_id, "storageKey": key, "fileSize": len(content)})
            action = self.repository.submit if kind == "submit" else self.repository.respond
            result = action(identity, data, actor, images)
            # Idempotent receipt may reference original images rather than this retry's staging.
            with self.repository.store.connection() as db:
                referenced = (
                    {
                        r[0]
                        for r in db.execute(
                            "SELECT storage_key FROM repair_evidence WHERE storage_key IN ("
                            + ",".join("?" for _ in staged)
                            + ")",
                            staged,
                        )
                    }
                    if staged
                    else set()
                )
            self.complaints.cleanup([k for k in staged if k not in referenced], identity)
            return result
        except IncidentError:
            self.complaints.cleanup(staged, identity)
            raise
        except StorageUnavailable as error:
            self.complaints.cleanup(staged, identity)
            raise IncidentError(
                503, "Private repair evidence storage unavailable; retry"
            ) from error
        except sqlite3.IntegrityError as error:
            self.complaints.cleanup(staged, identity)
            raise IncidentError(409, "Repair constraint conflict; refresh and review") from error

    def decision(self, identity, kind, data, actor):
        result = self.repository.decision(identity, kind, data, actor)
        if kind == "reopen":
            # Transaction already invalidates P8. Calculation is recoverable by existing worker.
            try:
                self.priorities.calculate(result["incidentId"])
            except IncidentError:
                logger.warning("operation=repair_reopen priority_recalculation=pending")
        return result

    def check_recurrence(self, identity, data, actor):
        current, candidates = self.repository.historical_candidates(identity, self.settings)

        def images(row):
            result = []
            for key in self.repository.complaint_image_keys(row["representative_complaint_id"]):
                try:
                    value = fingerprint(self.complaints.storage.get(key))
                    if value:
                        result.append(value)
                except StorageUnavailable:
                    pass  # Missing image is explicitly optional, not a positive signal.
            return result

        current_images = images(current) if candidates else []
        scores = []
        for previous in candidates:
            image = compare(images(previous), current_images)
            score = evaluate(
                previous,
                current,
                previous["verified_at"],
                radius=self.settings.recurrence_radius_meters,
                horizon=self.settings.recurrence_horizon_days,
                threshold=self.settings.recurrence_review_threshold,
                image=image.score,
            )
            scores.append((previous, score))
        return self.repository.save_candidates(identity, current, scores, data, actor)

    def fairness(self, filters):
        revision = self.repository.revision()
        key = (revision, filters.model_dump_json(), int(self.analytics.clock().timestamp() // 30))
        if key in self._fairness_cache:
            return copy.deepcopy(self._fairness_cache[key])
        # Revision fence joins consistent P11 source to P12 data without fake snapshots.
        intelligence = self.repository.intelligence_snapshot()
        _, _, rows, _, _, _, meta, _ = self.analytics.calculate(filters)
        require(
            meta["dataFreshness"]["sourceRevision"] == intelligence["revision"],
            "Source changed during comparison; retry",
            409,
        )
        require(len(rows) <= 5000, "Fairness cohort exceeds bounded aggregation", 413)
        result = compare_areas(
            rows,
            intelligence,
            filters.grid,
            self.settings.fairness_minimum_sample,
            self.settings.fairness_response_ratio,
            self.settings.fairness_rate_gap,
        )
        require(
            len(result["areas"]) <= 2000,
            "Too many areas; select a coarser grid or smaller viewport",
            413,
        )
        value = (
            meta | result | {"scope": self.settings.analytics_scope, "maximumCacheAgeSeconds": 30}
        )
        if len(self._fairness_cache) >= 16:
            self._fairness_cache.clear()
        self._fairness_cache[key] = value
        return copy.deepcopy(value)

    def report(self, kind, filters):
        from app.analytics.reporting import INTELLIGENCE_REPORTS

        require(kind in INTELLIGENCE_REPORTS, "Unknown intelligence report type", 422)
        value = self.fairness(filters)
        if kind == "repair-verification-outcomes":
            snapshot = self.repository.intelligence_snapshot()
            start, end = filters.window(self.settings.analytics_timezone, self.analytics.clock())
            _, _, incidents, _, _, _, _, _ = self.analytics.calculate(filters)
            ids = {r["incident_id"] for r in incidents}
            from app.analytics.metrics import stamp

            rows = [
                {
                    "incidentId": r["incident_id"],
                    "cycle": r["cycle"],
                    "state": r["state"],
                    "submittedAt": r["submitted_at"],
                    "verifiedAt": r["verified_at"],
                }
                for r in snapshot["repairs"]
                if r["incident_id"] in ids and start <= stamp(r["submitted_at"]) < end
            ]
        else:
            columns = [
                "areaId",
                "incidentCount",
                "responseObservations",
                "missingWorkStart",
                "medianWorkStartHours",
                "slaObservations",
                "missingSla",
                "overdueRate",
                "activeIncidents",
                "verifiedResolutionRate",
                "confirmedRecurrenceIncidents",
                "potentialRecurrenceIncidents",
                "status",
            ]
            rows = [{k: area[k] for k in columns} for area in value["areas"]]
        require(len(rows) <= 2000, "Report exceeds 2000 rows; narrow filters", 413)
        return {
            "title": kind.replace("-", " ").title(),
            "reportType": kind,
            "generatedAt": value["calculatedAt"],
            "reportingTimezone": value["reportingTimezone"],
            "filters": value["filters"],
            "window": value["window"],
            "dataFreshness": value["dataFreshness"],
            "definitions": json.dumps(value["definitions"], sort_keys=True)
            + " "
            + "; ".join(value["limitations"]),
            "sampleSize": len(rows),
            "columns": list(rows[0]) if rows else ["areaId", "incidentCount"],
            "rows": rows,
            "nextCursor": None,
            "pageOnly": False,
        }
