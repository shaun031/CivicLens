import hashlib
import json
import logging
import time
from dataclasses import asdict

from app.algorithms.duplicate_detection.candidate_selection import ACTIVE_STATUSES
from app.algorithms.duplicate_detection.image_similarity import compare
from app.algorithms.duplicate_detection.matching_engine import match
from app.algorithms.duplicate_detection.models import canonical_pair
from app.algorithms.duplicate_detection.text_similarity import TEXT_ENGINE
from app.algorithms.incident_clustering import (
    ClusteringConfig,
    automatic_evidence,
    eligible_category,
    physical_cohesion,
)
from app.models.incident import (
    Actor,
    Incident,
    IncidentError,
    IncidentPlan,
    IncidentStatus,
    Member,
    MembershipChange,
    stable_id,
)
from app.repositories.duplicate_candidate_repository import match_input, timestamp

logger = logging.getLogger(__name__)
SYSTEM = Actor("local-clustering-worker", "SYSTEM")
MAX_SCORE_SNAPSHOT_BYTES = 200_000


class IncidentService:
    def __init__(self, repository, matching, settings):
        self.repository, self.matching = repository, matching
        self.config = ClusteringConfig.from_settings(settings)
        self.seconds = settings.matching_job_seconds

    def require(self, identity: str) -> Incident:
        incident = self.repository.load(identity)
        if incident is None:
            raise IncidentError(404, "Incident not found")
        return incident

    def resolve(self, identity: str) -> tuple[Incident, list[str]]:
        visited = []
        for _ in range(64):
            if identity in visited:
                raise IncidentError(409, "Incident alias cycle requires audited reconciliation")
            visited.append(identity)
            incident = self.require(identity)
            if incident.status not in (IncidentStatus.MERGED, IncidentStatus.SUPERSEDED):
                return incident, visited
            if not incident.mergedIntoIncidentId:
                return incident, visited
            identity = incident.mergedIntoIncidentId
        raise IncidentError(409, "Alias depth exceeds the safe traversal bound")

    def require_member(self, identity: str) -> Member:
        member = self.repository.member(identity)
        if member is None:
            raise IncidentError(404, "Complaint not found")
        return member

    def members(self, identity: str) -> list[Member]:
        return self.repository.members(identity, self.config.max_members)

    @staticmethod
    def refreshed(
        incident: Incident,
        members: list[Member],
        now: str,
        retired: str | None = None,
        target: str | None = None,
    ) -> Incident:
        values = incident.model_dump()
        values.update(
            version=incident.version + 1,
            updatedAt=now,
            totalComplaintCount=len(members),
            uniqueReporterCount=len(
                {m.complaint.citizenId for m in members if m.eligible_reporter}
            ),
        )
        if members:
            representative = next(
                (
                    m.complaint
                    for m in members
                    if m.complaint.complaintId == incident.representativeComplaintId
                ),
                None,
            )
            representative = representative or min(
                (m.complaint for m in members), key=lambda c: (c.createdAt, c.complaintId)
            )
            values.update(
                canonicalTitle=representative.title,
                canonicalDescription=representative.description,
                category=representative.category,
                latitude=representative.latitude,
                longitude=representative.longitude,
                representativeComplaintId=representative.complaintId,
                firstReportedAt=min(m.complaint.createdAt for m in members),
                lastReportedAt=max(m.complaint.createdAt for m in members),
            )
        else:
            values.update(status=retired or IncidentStatus.SUPERSEDED, mergedIntoIncidentId=target)
        return Incident.model_validate(values)

    @staticmethod
    def new_incident(identity: str, members: list[Member], now: str) -> Incident:
        representative = min(
            (member.complaint for member in members),
            key=lambda complaint: (complaint.createdAt, complaint.complaintId),
        )
        return Incident(
            incidentId=identity,
            canonicalTitle=representative.title,
            canonicalDescription=representative.description,
            category=representative.category,
            latitude=representative.latitude,
            longitude=representative.longitude,
            status="OPEN"
            if any(m.complaint.status in ACTIVE_STATUSES for m in members)
            else "RESOLVED",
            representativeComplaintId=representative.complaintId,
            totalComplaintCount=len(members),
            uniqueReporterCount=len(
                {m.complaint.citizenId for m in members if m.eligible_reporter}
            ),
            firstReportedAt=min(m.complaint.createdAt for m in members),
            lastReportedAt=max(m.complaint.createdAt for m in members),
            createdAt=now,
            updatedAt=now,
            resolvedAt=now
            if all(m.complaint.status not in ACTIVE_STATUSES for m in members)
            else None,
            version=1,
        )

    def ensure_singleton(self, complaint_id: str) -> dict:
        for attempt in range(3):
            member = self.require_member(complaint_id)
            if member.complaint.incidentId:
                incident, _ = self.resolve(member.complaint.incidentId)
                return incident.model_dump(mode="json")
            now = timestamp()
            identity = stable_id(f"singleton/{complaint_id}")
            operation = stable_id(f"initial/{complaint_id}")
            plan = IncidentPlan(
                operation,
                operation,
                "INITIAL_ASSIGNMENT",
                SYSTEM,
                "Recoverable singleton assignment; no duplicate consolidation",
                {identity: None},
                {identity: self.new_incident(identity, [member], now)},
                [MembershipChange(complaint_id, None, identity)],
                [member],
                identity,
                now,
            )
            try:
                return self.repository.commit(plan)
            except IncidentError as error:
                if error.status != 409 or attempt == 2:
                    raise
        raise AssertionError("Unreachable assignment retry")

    @staticmethod
    def check_admin(actor: Actor):
        if actor.type != "ADMIN":
            raise IncidentError(403, "Administrator membership permission is required")

    def operation_key(
        self, operation: str, data: dict, actor: Actor
    ) -> tuple[str, str, dict | None]:
        identity = stable_id(f"operation/{actor.id}/{data['operationId']}")
        fingerprint = hashlib.sha256(
            json.dumps(
                {"operation": operation, "actor": actor.id, "input": data},
                sort_keys=True,
                default=str,
            ).encode()
        ).hexdigest()
        return identity, fingerprint, self.repository.operation(identity, fingerprint)

    def validate_open(self, incident: Incident, expected_version: int):
        if incident.status != IncidentStatus.OPEN:
            raise IncidentError(409, "Only a current OPEN incident may receive or merge reports")
        if incident.version != expected_version:
            raise IncidentError(409, "Stale incident version; refresh and confirm again")

    def mutate(self, kind: str, data: dict, actor: Actor) -> dict:
        try:
            return self._mutate(kind, data, actor)
        except IncidentError:
            # Another worker can commit the SAME operation between the initial replay
            # read and snapshot validation. A durable receipt wins over stale reads.
            self.check_admin(actor)
            _, _, replay = self.operation_key(kind, data, actor)
            if replay is not None:
                return replay
            raise

    def _mutate(self, kind: str, data: dict, actor: Actor) -> dict:
        self.check_admin(actor)
        if not data.get("confirmed") or len(data.get("reason", "").strip()) < 10:
            raise IncidentError(422, "Explicit confirmation and a written reason are required")
        operation, fingerprint, replay = self.operation_key(kind, data, actor)
        if replay is not None:
            return replay
        now = timestamp()
        source = self.require(data["sourceIncidentId"])
        if source.version != data["expectedSourceVersion"]:
            raise IncidentError(
                409, "Stale source incident version; refresh before applying changes"
            )
        source_members = self.members(source.incidentId)
        if source.status not in (IncidentStatus.OPEN, IncidentStatus.RESOLVED):
            raise IncidentError(409, "Retired incident references cannot be changed")
        if kind == "RECHECK":
            updated = self.refreshed(source, source_members, now)
            plan = IncidentPlan(
                operation,
                fingerprint,
                kind,
                actor,
                data["reason"],
                {source.incidentId: source},
                {source.incidentId: updated},
                [],
                source_members,
                source.incidentId,
                now,
            )
            return self.repository.commit(plan)
        if kind in ("MANUAL_LINK", "MERGE"):
            if not data.get("physicalIssueConfirmed"):
                raise IncidentError(422, "An administrator must confirm the same physical issue")
            target = self.require(data["targetIncidentId"])
            self.validate_open(target, data["expectedTargetVersion"])
            self.validate_open(source, data["expectedSourceVersion"])
            if source.incidentId == target.incidentId:
                raise IncidentError(409, "Reports already belong to this incident")
            target_members = self.members(target.incidentId)
            moved = (
                source_members
                if kind == "MERGE"
                else [
                    member
                    for member in source_members
                    if member.complaint.complaintId == data["complaintId"]
                ]
            )
            if not moved or any(m.complaint.status not in ACTIVE_STATUSES for m in moved):
                raise IncidentError(409, "Complaint is not an eligible current member")
            remaining = [m for m in source_members if m not in moved]
            combined = target_members + moved
            valid, explanation = physical_cohesion(combined, self.config, self.matching.config)
            if not valid:
                raise IncidentError(422, explanation)
            evidence = {"physicalIssueConfirmed": True, "explanation": explanation}
            if data.get("matchingCandidateId"):
                candidate = self.matching.repository.candidate(data["matchingCandidateId"])
                if not candidate:
                    raise IncidentError(409, "Matching candidate no longer exists")
                pairs = {candidate["sourceComplaintId"], candidate["possibleDuplicateId"]}
                all_ids = {m.complaint.complaintId for m in combined}
                if not pairs <= all_ids:
                    raise IncidentError(
                        409, "Matching evidence does not describe these current members"
                    )
                evidence["candidateId"] = candidate["candidateId"]
                evidence["scoreSnapshot"] = candidate
            after = {
                source.incidentId: self.refreshed(
                    source,
                    remaining,
                    now,
                    IncidentStatus.MERGED if kind == "MERGE" else IncidentStatus.SUPERSEDED,
                    target.incidentId if not remaining else None,
                ),
                target.incidentId: self.refreshed(target, combined, now),
            }
            return self.repository.commit(
                IncidentPlan(
                    operation,
                    fingerprint,
                    kind,
                    actor,
                    data["reason"],
                    {source.incidentId: source, target.incidentId: target},
                    after,
                    [
                        MembershipChange(
                            m.complaint.complaintId, source.incidentId, target.incidentId, evidence
                        )
                        for m in moved
                    ],
                    source_members + target_members,
                    target.incidentId,
                    now,
                )
            )
        if kind in ("SPLIT", "UNLINK"):
            selected = set(data["complaintIds"])
            moved = [m for m in source_members if m.complaint.complaintId in selected]
            if len(moved) != len(selected) or not moved or len(moved) == len(source_members):
                raise IncidentError(
                    409, "Select current members and leave at least one member in the source"
                )
            valid, explanation = physical_cohesion(moved, self.config, self.matching.config)
            if not valid:
                raise IncidentError(422, explanation)
            remaining = [m for m in source_members if m not in moved]
            new_id = stable_id(f"split/{operation}")
            return self.repository.commit(
                IncidentPlan(
                    operation,
                    fingerprint,
                    kind,
                    actor,
                    data["reason"],
                    {source.incidentId: source, new_id: None},
                    {
                        source.incidentId: self.refreshed(source, remaining, now),
                        new_id: self.new_incident(new_id, moved, now),
                    },
                    [
                        MembershipChange(
                            m.complaint.complaintId,
                            source.incidentId,
                            new_id,
                            {"correction": data["reason"]},
                        )
                        for m in moved
                    ],
                    source_members,
                    new_id,
                    now,
                )
            )
        raise IncidentError(422, "Unsupported incident operation")

    def recommendations(self, source: Member, deadline: float) -> tuple[list[dict], bool]:
        ids, truncated = self.repository.candidates(
            source.complaint.complaintId, self.config.target_limit * self.config.max_members
        )
        targets, outcomes = {}, []
        evidence_bytes = 0
        for identity in ids:
            candidate = self.matching.repository.candidate(identity)
            if not candidate or candidate["reviewStatus"] == "DISMISSED":
                continue
            other_id = next(
                key
                for key in (candidate["sourceComplaintId"], candidate["possibleDuplicateId"])
                if key != source.complaint.complaintId
            )
            other = self.repository.member(other_id)
            if other is None:
                continue
            if not other.complaint.incidentId:
                self.ensure_singleton(other_id)
                other = self.require_member(other_id)
            target, _ = self.resolve(other.complaint.incidentId)
            if target.incidentId != source.complaint.incidentId and target.status == "OPEN":
                targets.setdefault(target.incidentId, (target, candidate))
        if len(targets) > self.config.target_limit:
            truncated = True
        for target, candidate in list(targets.values())[: self.config.target_limit]:
            if time.perf_counter() >= deadline:
                truncated = True
                break
            members = self.members(target.incidentId)
            combined = [source] + members
            valid, reason = physical_cohesion(combined, self.config, self.matching.config, True)
            snapshots = []
            if (
                candidate["configVersion"] != self.matching.config.version
                or candidate["modelVersion"] != TEXT_ENGINE.version
            ):
                valid, reason = False, "Stale matching model/config; recheck Phase 6 evidence first"
            if not source.eligible_reporter or not eligible_category(source.complaint.category):
                valid, reason = (
                    False,
                    "Automatic links require an eligible reporter and known category",
                )
            if valid:
                cached_images = {
                    m.complaint.complaintId: self.matching.fingerprints(m.complaint)
                    for m in combined
                }
                for index, first in enumerate(combined):
                    for second in combined[index + 1 :]:
                        if time.perf_counter() >= deadline:
                            truncated, valid, reason = (
                                True,
                                False,
                                "Full-member comparison time budget exceeded",
                            )
                            break
                        pair_id, _, _ = canonical_pair(
                            first.complaint.complaintId, second.complaint.complaintId
                        )
                        reviewed = self.matching.repository.candidate(pair_id)
                        if reviewed and reviewed["reviewStatus"] == "DISMISSED":
                            valid, reason = (
                                False,
                                "Administrator previously dismissed a member-pair suggestion",
                            )
                            break
                        signal = compare(
                            cached_images[first.complaint.complaintId],
                            cached_images[second.complaint.complaintId],
                        )
                        result = match(
                            match_input(first.complaint),
                            match_input(second.complaint),
                            self.matching.config,
                            signal,
                        )
                        passed, reason = automatic_evidence(result, self.config)
                        if not passed:
                            valid = False
                            break
                        snapshot = asdict(result)
                        snapshot.pop("timings")
                        evidence_bytes += len(json.dumps(snapshot, default=str).encode())
                        if evidence_bytes > MAX_SCORE_SNAPSHOT_BYTES:
                            truncated, valid, reason = (
                                True,
                                False,
                                "Score snapshot budget exceeded; manual review required",
                            )
                            break
                        snapshots.append(snapshot)
                    if not valid:
                        break
            outcomes.append(
                {
                    "targetIncidentId": target.incidentId,
                    "targetVersion": target.version,
                    "candidateId": candidate["candidateId"],
                    "eligibleForAutoLink": valid,
                    "explanation": reason,
                    "evidence": snapshots,
                }
            )
        return outcomes, truncated

    def process_one(self, source_id: str | None = None):
        claimed = self.repository.claim(source_id)
        if not claimed:
            return None
        source_id, token = claimed
        started = time.perf_counter()
        try:
            self.ensure_singleton(source_id)
            source = self.require_member(source_id)
            current = self.require(source.complaint.incidentId)
            current_members = self.members(current.incidentId)
            singleton = (
                len(current_members) == 1 and current_members[0].complaint.complaintId == source_id
            )
            recommendations, incomplete = self.recommendations(source, started + self.seconds)
            matching_job = self.matching.repository.job(source_id)
            matching_complete = bool(
                matching_job
                and matching_job["state"] == "COMPLETE"
                and not (matching_job.get("report") or {}).get("incomplete")
            )
            report = {
                "mode": self.config.mode,
                "incidentId": current.incidentId,
                "recommendations": recommendations,
                "incomplete": incomplete,
                "matchingComplete": matching_complete,
                "decision": "KEEP_SEPARATE_REVIEW",
                "config": asdict(self.config),
                "runId": token,
            }
            if (
                self.config.mode == "CONSERVATIVE_AUTO_LINK"
                and not incomplete
                and matching_complete
                and singleton
                and current.status == "OPEN"
                and source.complaint.status in ACTIVE_STATUSES
                and len(recommendations) == 1
                and recommendations[0]["eligibleForAutoLink"]
            ):
                recommendation = recommendations[0]
                target = self.require(recommendation["targetIncidentId"])
                members = self.members(target.incidentId)
                if target.version != recommendation["targetVersion"]:
                    raise IncidentError(409, "Incident changed during automatic validation")
                now = timestamp()
                operation = stable_id(f"auto/{token}")
                plan = IncidentPlan(
                    operation,
                    operation,
                    "AUTOMATIC_LINK",
                    SYSTEM,
                    "Explicit conservative mode; fresh all-member checks; no competing incident",
                    {current.incidentId: current, target.incidentId: target},
                    {
                        current.incidentId: self.refreshed(
                            current, [], now, "SUPERSEDED", target.incidentId
                        ),
                        target.incidentId: self.refreshed(target, members + [source], now),
                    },
                    [
                        MembershipChange(
                            source_id, current.incidentId, target.incidentId, recommendation
                        )
                    ],
                    [source] + members,
                    target.incidentId,
                    now,
                )
                try:
                    result = self.repository.commit(plan)
                    report.update(decision="AUTOMATIC_LINK", incidentId=result["incidentId"])
                except IncidentError as error:
                    if error.status != 413:
                        raise
                    report.update(decision="ATOMIC_ENVELOPE_REVIEW", explanation=error.message)
            elif len(recommendations) > 1:
                report["decision"] = "AMBIGUOUS_COMPETING_INCIDENTS"
            elif not singleton:
                report["decision"] = "ESTABLISHED_CLUSTER_NO_AUTOMATIC_MOVE"
            report["durationMs"] = (time.perf_counter() - started) * 1000
            self.repository.finish_job(source_id, token, report)
            return report
        except Exception as error:
            logger.warning("operation=clustering error_category=%s", type(error).__name__)
            self.repository.fail_job(source_id, token, type(error).__name__)
            return {"state": "RETRY", "errorCategory": type(error).__name__}


def build_incident_service(settings, complaints, matching):
    if settings.complaint_provider == "sqlite":
        from app.repositories.incident_repository import SQLiteIncidents

        repository = SQLiteIncidents(complaints.repository)
    else:
        from app.integrations.database.dynamodb_incidents import DynamoIncidents

        repository = DynamoIncidents(complaints.repository, matching.repository)
    return IncidentService(repository, matching, settings)
