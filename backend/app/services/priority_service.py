import copy
import hashlib
import json
import logging
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import uuid4

from app.algorithms.priority_scoring.aging import utc
from app.algorithms.priority_scoring.config import PriorityConfig
from app.algorithms.priority_scoring.models import Assessment, PriorityInput
from app.algorithms.priority_scoring.scoring_engine import calculate
from app.models.incident import Actor, IncidentError, stable_id
from app.repositories.priority_repository import PriorityCommit

logger = logging.getLogger(__name__)
SYSTEM = Actor("priority-local-worker", "SYSTEM")


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, allow_nan=False).encode()
    ).hexdigest()


def result_dto(result):
    def camel(key):
        first, *rest = key.split("_")
        return first + "".join(word.title() for word in rest)

    return json.loads(
        json.dumps({camel(key): value for key, value in asdict(result).items()}, allow_nan=False)
    )


def assessment(value):
    return Assessment(
        score=value.get("score"),
        status=value.get("status", "UNASSESSED"),
        reason=value.get("reason", ""),
        evidence=tuple(value.get("evidenceReferences", [])),
        actor=value.get("assessedBy"),
        assessed_at=value.get("assessedAt"),
        epoch=value.get("epoch", 0),
    )


class PriorityService:
    def __init__(self, repository, incidents, settings, clock=None):
        self.repository, self.incidents = repository, incidents
        self.config = PriorityConfig.from_settings(settings)
        self.clock = clock or (lambda: datetime.now(UTC))

    def canonical(self, identity):
        return self.incidents.resolve(identity)[0].incidentId

    def stale_reasons(self, snapshot, now=None):
        record, incident = snapshot.record, snapshot.incident
        now = utc(now or self.clock())
        reasons = []
        if not record.get("result"):
            reasons.append("Priority has not been calculated")
        if record["needs_recalculation"] or record["source_version"] != incident.version:
            reasons.append("Incident, eligibility or assessment inputs changed")
        if record["config_version"] != self.config.version:
            reasons.append("Scoring configuration changed")
        if record["next_due"] <= now.timestamp():
            reasons.append("Aging/override review is due")
        return reasons

    def detail(self, identity):
        canonical = self.canonical(identity)
        snapshot = self.repository.snapshot(canonical)
        reasons = self.stale_reasons(snapshot)
        evidence = []
        for member in snapshot.members:
            report = member.complaint
            evidence.append({"id": report.complaintId, "label": report.title})
            evidence.extend(
                {"id": image.imageId, "label": f"Photo for {report.title}"}
                for image in report.images
            )
        return {
            "incident": snapshot.incident.model_dump(mode="json"),
            "requestedIncidentId": identity,
            "priority": snapshot.record["result"],
            "priorityRevision": snapshot.record["controls_version"],
            "incidentVersion": snapshot.incident.version,
            "membershipEpoch": snapshot.record["membership_epoch"],
            "controls": snapshot.record["controls"],
            "stale": bool(reasons),
            "staleReasons": reasons,
            "evidenceOptions": evidence,
            "processing": {
                "attempts": snapshot.record.get("attempts", 0),
                "errorCategory": snapshot.record.get("error_category"),
            },
            "currentConfigVersion": self.config.version,
        }

    def prepare(self, snapshot, controls, now):
        incident, row = snapshot.incident, snapshot.record
        members = snapshot.members
        unique = len({m.complaint.citizenId for m in members if m.eligible_reporter})
        quality = row.get("age_quality", "APPROXIMATE_BASELINE")
        for value in (incident.firstReportedAt, incident.resolvedAt):
            if value:
                try:
                    utc(value)
                except (ValueError, TypeError):
                    quality = "INVALID"
        danger_terms = (
            "exposed wire",
            "exposed electrical",
            "open drainage pit",
            "collapsed road",
            "unstable structure",
            "emergency access",
        )
        data = PriorityInput(
            incident.incidentId,
            incident.version,
            incident.status,
            incident.firstReportedAt,
            unique,
            len(members),
            now,
            assessment(controls.get("severity", {})),
            assessment(controls.get("publicImpact", {})),
            row["membership_epoch"],
            row.get("age_open_since"),
            row.get("age_frozen_seconds", 0),
            quality,
            any(m.eligible_reporter and m.complaint.reportedSeverity == "HIGH" for m in members),
            any(
                term in (m.complaint.title + " " + m.complaint.description).casefold()
                for m in members
                if m.eligible_reporter
                for term in danger_terms
            ),
            controls.get("hazard", {}),
            controls.get("override", {}),
        )
        result = result_dto(calculate(data, self.config))
        facts = {
            "status": incident.status,
            "firstReportedAt": incident.firstReportedAt,
            "openSince": row.get("age_open_since"),
            "frozenSeconds": row.get("age_frozen_seconds", 0),
            "uniqueReporters": unique,
            "totalReports": len(members),
            "members": [
                {
                    "complaintId": m.complaint.complaintId,
                    "eligibleReporter": m.eligible_reporter,
                    "reportedSeverity": m.complaint.reportedSeverity,
                }
                for m in members
            ],
            "controls": controls,
            "membershipEpoch": row["membership_epoch"],
        }
        meaningful = copy.deepcopy(result)
        for key in (
            "calculatedAt",
            "incidentVersion",
            "unresolvedSeconds",
            "unresolvedDays",
            "explanation",
        ):
            meaningful.pop(key)
        meaningful["factors"]["aging"].pop("rawValue")
        meaningful["factors"]["aging"]["normalizedValue"] = round(
            result["factors"]["aging"]["normalizedValue"], 2
        )
        fingerprint = digest({"facts": facts, "result": meaningful})
        due = now.timestamp() + self.config.refresh_seconds
        override = controls.get("override", {})
        if override.get("expiresAt") and override.get("status") == "ACTIVE":
            expires = utc(override["expiresAt"]).timestamp()
            if expires > now.timestamp():
                due = min(due, expires)
        return result, facts, fingerprint, due

    def calculate(self, identity, *, dry_run=False, lease_token=None):
        canonical = self.canonical(identity)
        # Retired originals are scored only by the worker to archive their own state/history.
        snapshot = self.repository.snapshot(canonical)
        return self.calculate_snapshot(snapshot, dry_run=dry_run, lease_token=lease_token)

    def calculate_snapshot(self, snapshot, *, dry_run=False, lease_token=None):
        now = utc(self.clock())
        result, facts, fingerprint, due = self.prepare(snapshot, snapshot.record["controls"], now)
        if dry_run:
            return {
                "dryRun": True,
                "incidentId": snapshot.incident.incidentId,
                "priority": result,
                "wouldChangeHistory": fingerprint != snapshot.record.get("fingerprint"),
            }
        return self.repository.commit(
            PriorityCommit(
                snapshot,
                result,
                snapshot.record["controls"],
                fingerprint,
                facts,
                due,
                SYSTEM,
                "Recomputed from authoritative incident, eligible members and versioned rubric",
                lease_token=lease_token,
            )
        )

    def change(self, identity, kind, data, actor):
        if actor.type != "ADMIN":
            raise IncidentError(403, "Only an administrator may assess or override priority")
        if not data.get("confirmed") or len(data.get("reason", "").strip()) < 10:
            raise IncidentError(422, "Explicit confirmation and a written reason are required")
        operation = stable_id(f"priority-operation/{actor.id}/{data['operationId']}")
        request_hash = digest(
            {"incidentId": identity, "kind": kind, "actor": actor.id, "data": data}
        )
        replay = self.repository.operation(operation, request_hash)
        if replay is not None:
            return replay
        try:
            if self.canonical(identity) != identity:
                raise IncidentError(
                    409, "Use the canonical incident ID and refresh before assessment"
                )
            snapshot = self.repository.snapshot(identity)
            if snapshot.incident.status not in ("OPEN", "RESOLVED"):
                raise IncidentError(409, "Retired incidents cannot receive priority controls")
            if (
                data["expectedIncidentVersion"] != snapshot.incident.version
                or data["expectedPriorityRevision"] != snapshot.record["controls_version"]
            ):
                raise IncidentError(
                    409, "Stale incident or assessment revision; refresh and confirm again"
                )
            now = utc(self.clock())
            timestamp = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")
            controls = copy.deepcopy(snapshot.record["controls"])
            evidence = data.get("evidenceReferences", [])
            allowed = {m.complaint.complaintId for m in snapshot.members} | {
                image.imageId for member in snapshot.members for image in member.complaint.images
            }
            if any(ref not in allowed for ref in evidence):
                raise IncidentError(
                    422, "Evidence must reference current member reports or their photos"
                )
            common = {
                "reason": data["reason"],
                "assessedBy": actor.id,
                "assessedAt": timestamp,
                "epoch": snapshot.record["membership_epoch"],
                "evidenceReferences": evidence,
            }
            if kind in ("SEVERITY", "PUBLIC_IMPACT"):
                controls["severity" if kind == "SEVERITY" else "publicImpact"] = common | {
                    "score": data.get("score"),
                    "status": data["status"],
                }
            elif kind == "HAZARD":
                if data["flag"] and not evidence:
                    raise IncidentError(422, "Verified hazard requires current supporting evidence")
                controls["hazard"] = common | {
                    "flag": data["flag"],
                    "status": "VERIFIED" if data["flag"] else "CLEARED",
                }
            elif kind == "OVERRIDE":
                expires = data.get("expiresAt")
                if expires:
                    try:
                        expired = utc(expires) <= now
                    except (ValueError, TypeError) as error:
                        raise IncidentError(
                            422, "Expiration must include a valid timezone"
                        ) from error
                    if expired:
                        raise IncidentError(422, "Override expiration must be in the future")
                controls["override"] = {
                    "overrideId": str(uuid4()),
                    "score": data["score"],
                    "reason": data["reason"],
                    "createdBy": actor.id,
                    "createdAt": timestamp,
                    "epoch": snapshot.record["membership_epoch"],
                    "expiresAt": expires,
                    "status": "ACTIVE",
                }
            elif kind == "REMOVE_OVERRIDE":
                controls["override"] = controls.get("override", {}) | {
                    "status": "REMOVED",
                    "removedBy": actor.id,
                    "removedAt": timestamp,
                    "removalReason": data["reason"],
                }
            elif kind != "RECALCULATE":
                raise IncidentError(422, "Unknown priority operation")
            try:
                result, facts, fingerprint, due = self.prepare(snapshot, controls, now)
            except (ValueError, TypeError) as error:
                raise IncidentError(
                    422, "Invalid priority assessment, evidence or timestamp"
                ) from error
            return self.repository.commit(
                PriorityCommit(
                    snapshot,
                    result,
                    controls,
                    fingerprint,
                    facts,
                    due,
                    actor,
                    data["reason"],
                    kind,
                    operation,
                    request_hash,
                )
            )
        except IncidentError:
            replay = self.repository.operation(operation, request_hash)
            if replay is not None:
                return replay
            raise

    def process_one(self):
        now = utc(self.clock()).timestamp()
        claim = self.repository.claim(now, self.config.version)
        if not claim:
            return None
        identity, token = claim
        try:
            return self.calculate_snapshot(self.repository.snapshot(identity), lease_token=token)
        except Exception as error:
            logger.warning(
                "operation=priority_recalculation error_category=%s", type(error).__name__
            )
            self.repository.fail(identity, token, now, type(error).__name__)
            return {"state": "RETRY", "errorCategory": type(error).__name__}


def build_priority_service(settings, incidents):
    if settings.complaint_provider == "sqlite":
        from app.repositories.priority_repository import SQLitePriority

        repository = SQLitePriority(incidents.repository)
    else:
        from app.integrations.database.dynamodb_priority import DynamoPriority

        repository = DynamoPriority(incidents.repository)
    return PriorityService(repository, incidents, settings)
