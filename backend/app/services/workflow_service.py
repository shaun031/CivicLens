"""Bounded orchestration of existing Phase 6–9 services; no duplicated domain algorithms."""

import logging
import time

from app.events.schema import Event, consumer, new_event
from app.models.incident import IncidentError, stable_id
from app.schemas.work import AssignmentAction

logger = logging.getLogger(__name__)
STEPS = (
    "ValidateComplaint",
    "RunDuplicateDetection",
    "EvaluateClustering",
    "RecalculatePriority",
    "RouteDepartment",
    "EvaluateNotifications",
)


class WorkflowService:
    def __init__(self, repository, matching, incidents, priorities, work):
        self.repository, self.matching, self.incidents = repository, matching, incidents
        self.priorities, self.work = priorities, work
        self.fault = None  # Explicit test-only injection point; never configured through HTTP/env.
        self.analytics = None
        self.intelligence = None
        from app.events.registry import HandlerRegistry

        self.registry = HandlerRegistry()
        self.registry.register("triage", self.triage)
        self.registry.register("priority", self.priority_event)
        self.registry.register("notify", lambda event, message: self.notify(event))

    def stage(self, name, event, workflow):
        source = str(event.aggregateId)
        member = self.incidents.repository.member(source)
        if name == "ValidateComplaint":
            eligible = bool(
                member
                and member.eligible_reporter
                and member.complaint.status not in ("REJECTED", "RESOLVED")
            )
            if eligible and event.eventType == "ComplaintSubmitted":
                self.notify(event)
            return {"eligible": eligible}
        if member is None:
            raise IncidentError(404, "Complaint no longer exists")
        if name == "RunDuplicateDetection":
            job = self.matching.repository.job(source)
            if not job or job["state"] not in ("COMPLETE", "INCOMPLETE"):
                self.matching.process_one(source)
                job = self.matching.repository.job(source)
            if not job or job["state"] not in ("COMPLETE", "INCOMPLETE"):
                raise RuntimeError("Duplicate analysis is pending retry")
            return {"completed": True, "reviewRequired": job["state"] == "INCOMPLETE"}
        if name == "EvaluateClustering":
            job = self.incidents.repository.job(source)
            if not job or job["state"] != "COMPLETE":
                self.incidents.process_one(source)
                job = self.incidents.repository.job(source)
            if not job or job["state"] != "COMPLETE":
                raise RuntimeError("Clustering is pending retry")
            report = job.get("report") or {}
            return {
                "incidentId": self.incidents.require_member(source).complaint.incidentId,
                "reviewRequired": bool(report.get("recommendations") or report.get("incomplete"))
                and report.get("decision") != "AUTOMATIC_LINK",
                "decision": report.get("decision", "REVIEW_REQUIRED"),
            }
        identity = self.incidents.require_member(source).complaint.incidentId
        identity = self.incidents.resolve(identity)[0].incidentId
        if name == "RecalculatePriority":
            if self.priorities.detail(identity)["stale"]:
                self.priorities.calculate(identity)
            return {"incidentId": identity, "completed": True}
        if name == "RouteDepartment":
            detail = self.work.detail(identity)
            assignment = detail["assignment"]
            if assignment["departmentId"] or assignment["method"] == "REVIEW_LOCK":
                return {
                    "incidentId": identity,
                    "skipped": "EXISTING_CONFIRMED_ASSIGNMENT_OR_REVIEW_LOCK",
                    "reviewRequired": assignment["status"] == "NEEDS_REVIEW",
                }
            action = AssignmentAction(
                operationId=stable_id(
                    f"workflow-route/{workflow['workflow_id']}/{detail['incidentVersion']}/{assignment['version']}"
                ),
                confirmed=True,
                reason="Automated triage routing using current authoritative configuration",
                expectedIncidentVersion=detail["incidentVersion"],
                expectedAssignmentVersion=assignment["version"],
            )
            result = self.work.route_event(
                {"version": 1, "incidentId": identity, "action": action.model_dump(mode="json")}
            )
            return {"incidentId": identity, "reviewRequired": result["status"] == "NEEDS_REVIEW"}
        if name == "EvaluateNotifications":
            self.notify(event)
            if self.intelligence:
                self.intelligence.check_recurrence(
                    identity,
                    {"operationId": stable_id(f"recurrence-workflow/{event.eventId}/{identity}")},
                    {"id": member.complaint.citizenId, "role": "CITIZEN"},
                )
            previous = self.repository.detail(workflow["workflow_id"])
            if previous["review_required"]:
                duplicate = (
                    self.repository.step(workflow["workflow_id"], "RunDuplicateDetection") or {}
                )
                clustering = (
                    self.repository.step(workflow["workflow_id"], "EvaluateClustering") or {}
                )
                review_kind = (
                    "DuplicateReviewRequired"
                    if duplicate.get("reviewRequired") or clustering.get("reviewRequired")
                    else "RoutingReviewRequired"
                )
                review = new_event(
                    review_kind,
                    source,
                    correlation=event.correlationId,
                    cause=event.eventId,
                )
                review = Event.parse(
                    review.model_dump(mode="json")
                    | {"eventId": stable_id("review/" + workflow["workflow_id"])}
                )
                self.repository.publish(review)
            return {"incidentId": identity, "completed": True}
        raise ValueError("Unknown workflow step")

    def triage(self, event, message):
        workflow = self.repository.workflow_begin(event, message)
        identity = workflow["workflow_id"]
        if workflow["status"] in ("COMPLETED", "COMPLETED_WITH_REVIEW_REQUIRED", "CANCELLED"):
            return
        if message["attempts"] > message["max_attempts"]:
            raise RuntimeError("Workflow retry budget exhausted after expired leases")
        for name in STEPS:
            result = self.repository.step(identity, name)
            if result is None:
                self.repository.step_start(identity, name, message)
                if self.fault:
                    self.fault(name)
                result = self.stage(name, event, workflow)
                self.repository.step(identity, name, result, message)
            if name == "ValidateComplaint" and not result["eligible"]:
                self.repository.workflow_finish(identity, message, cancelled=True)
                return
        self.repository.workflow_finish(identity, message)

    def notify(self, event):
        repo, kind, identity = self.repository, event.eventType, str(event.aggregateId)
        if kind.startswith(
            ("Repair", "Recurrence", "PotentialRecurrence", "FairnessReview")
        ) or kind in ("IncidentVerifiedResolved", "IncidentReopened"):
            self.notify_intelligence(event)
            return
        if event.aggregateType == "COMPLAINT":
            member = self.incidents.repository.member(identity)
            if not member:
                return
            if kind == "ComplaintSubmitted":
                repo.notify(
                    event,
                    member.complaint.citizenId,
                    "COMPLAINT_RECEIVED",
                    "Complaint received",
                    "Your report has been stored. Automated triage and municipal assessment "
                    "may still be pending.",
                    "COMPLAINT",
                    identity,
                    f"/citizen/complaints/{identity}",
                )
                return
            if kind in ("DuplicateReviewRequired", "RoutingReviewRequired", "WorkflowFailed"):
                category = "ADMIN_ACTION_REQUIRED"
                for admin in repo.admins():
                    repo.notify(
                        event,
                        admin,
                        category,
                        "Processing review required",
                        "A report needs authorized duplicate, routing, or workflow review. "
                        "No automatic merge or priority override was applied.",
                        "COMPLAINT",
                        identity,
                        "/admin/workflows",
                    )
                return
        incident = self.incidents.repository.load(identity)
        if incident is None or incident.status in ("MERGED", "SUPERSEDED"):
            return
        if kind == "IncidentPriorityChanged":
            detail = self.priorities.detail(identity)
            priority = detail.get("priority") or {}
            if not detail["stale"] and priority.get("urgentHazard"):
                for admin in repo.admins():
                    repo.notify(
                        event,
                        admin,
                        "URGENT_HAZARD_REVIEW",
                        "Verified hazard requires attention",
                        "Review the incident's current safety assessment and municipal response.",
                        "INCIDENT",
                        identity,
                        f"/admin/incidents/{identity}",
                    )
            return
        if kind == "IncidentOverdue":
            for admin in repo.admins():
                repo.notify(
                    event,
                    admin,
                    "INCIDENT_OVERDUE",
                    "Demonstration SLA target exceeded",
                    "An operational response or resolution target is overdue. This does "
                    "not change assessed severity.",
                    "INCIDENT",
                    identity,
                    "/admin/workflows",
                )
            return
        detail = self.work.detail(identity)
        assignment = detail["assignment"]
        if kind in ("IncidentOfficerAssigned", "IncidentOfficerReassigned"):
            officer = str(event.payload.get("officerId", ""))
            if officer and assignment["officerId"] == officer:
                # Current server-side authorization rechecked; stale events grant no access.
                try:
                    self.work.detail(identity, officer)
                except IncidentError as error:
                    if error.status == 404:
                        return
                    raise
                repo.notify(
                    event,
                    officer,
                    "OFFICER_ASSIGNED",
                    "New incident assigned",
                    "An incident is assigned to you. Open your authorized work queue for "
                    "current details.",
                    "INCIDENT",
                    identity,
                    f"/officer/incidents/{identity}",
                )
            return
        mapping = {
            "IncidentDepartmentAssigned": ("INCIDENT_ASSIGNED", "Department assigned"),
            "IncidentWorkStarted": ("WORK_STARTED", "Work started"),
            "IncidentProgressUpdated": ("WORK_PROGRESS_UPDATED", "Work progress updated"),
            "IncidentStatusChanged": ("INCIDENT_STATUS_CHANGED", "Incident status updated"),
        }
        if kind not in mapping:
            return
        notification_type, title = mapping[kind]
        for member in self.incidents.members(identity):
            if member.eligible_reporter:
                complaint = member.complaint
                repo.notify(
                    event,
                    complaint.citizenId,
                    notification_type,
                    title,
                    "There is an update on the incident associated with your report. View "
                    "your report for current information.",
                    "COMPLAINT",
                    complaint.complaintId,
                    f"/citizen/complaints/{complaint.complaintId}",
                )

    def notify_intelligence(self, event):
        repo, kind, identity = self.repository, event.eventType, str(event.aggregateId)
        if kind == "FairnessReviewFlagged":
            for admin in repo.admins():
                repo.notify(
                    event,
                    admin,
                    "ADMIN_ACTION_REQUIRED",
                    "Geographic service review recorded",
                    "An internal descriptive service comparison was submitted "
                    "for administrative investigation.",
                    "AREA_REVIEW",
                    identity,
                    "/admin/fairness",
                )
            return
        incident = self.incidents.repository.load(identity)
        if not incident or incident.status in ("MERGED", "SUPERSEDED"):
            return
        recurrence = "Recurrence" in kind
        admin_url = "/admin/recurrences" if recurrence else "/admin/repair-verification"
        if kind not in ("RepairVerificationRequested", "IncidentVerifiedResolved"):
            for admin in repo.admins():
                repo.notify(
                    event,
                    admin,
                    "ADMIN_ACTION_REQUIRED",
                    "Civic intelligence review update",
                    "A repair, verification or recurrence record requires authorized review.",
                    "INCIDENT",
                    identity,
                    admin_url,
                )
        if recurrence:
            return
        # Feedback contents/identities never appear in notifications to other reporters.
        citizen_events = (
            "RepairVerificationRequested",
            "IncidentVerifiedResolved",
            "IncidentReopened",
            "RepairRejected",
            "RepairReworkRequested",
            "RepairInformationRequested",
        )
        if kind in citizen_events:
            for member in self.incidents.members(identity):
                if member.eligible_reporter:
                    repo.notify(
                        event,
                        member.complaint.citizenId,
                        "REPAIR_VERIFICATION_UPDATE",
                        "Repair verification update",
                        "View your eligible verification requests and current official decision.",
                        "INCIDENT",
                        identity,
                        "/citizen/verification",
                    )
        detail = self.work.detail(identity)
        officer = detail["assignment"]["officerId"]
        target = f"/officer/incidents/{identity}"
        if officer:
            try:
                self.work.detail(identity, officer)
            except IncidentError as error:
                if error.status != 404:
                    raise
                officer = None
        if (
            not officer
            and self.intelligence
            and event.payload.get("attemptId")
            and kind in ("IncidentVerifiedResolved", "IncidentReopened")
        ):
            officer = self.intelligence.repository.submitting_officer(
                str(event.payload["attemptId"]), identity
            )
            # Original participant gets a generic final decision, not historical evidence access.
            target = "/officer/dashboard"
        if officer:
            repo.notify(
                event,
                officer,
                "OFFICER_REPAIR_UPDATE",
                "Repair review update",
                (
                    "Review the current repair verification or rework decision "
                    "for your assigned incident."
                ),
                "INCIDENT",
                identity,
                target,
            )

    def priority_event(self, event, message):
        canonical = self.incidents.resolve(str(event.aggregateId))[0]
        if canonical.status == "OPEN" and self.priorities.detail(canonical.incidentId)["stale"]:
            self.priorities.calculate(canonical.incidentId)

    def process_one(self):
        message = self.repository.claim()
        if message is None:
            return False
        return self.consume(message)

    def consume(self, message):
        started = time.monotonic()
        event = None
        try:
            event = Event.parse(message["envelope"])
            name = consumer(event)
            if name != "triage" and message["attempts"] > message["max_attempts"]:
                raise RuntimeError("Consumer retry budget exhausted after expired leases")
            if message["consumer"] != name:
                raise ValueError("Incorrect consumer")
            if not self.repository.completed(event, name):
                self.registry.dispatch(event, message)
            self.observe_analytics(event)
            self.repository.ack(message, event)
        except Exception as error:
            permanent = (
                isinstance(error, (ValueError, TypeError, KeyError))
                or isinstance(error, IncidentError)
                and error.status in (400, 403, 404, 413, 422)
            )
            self.repository.fail(message, permanent=permanent)
        logger.info(
            "operation=domain_consumer eventId=%s correlationId=%s consumerName=%s durationMs=%d",
            message["event_id"],
            str(event.correlationId) if event else "invalid",
            message["consumer"],
            int((time.monotonic() - started) * 1000),
        )
        return True

    def observe_analytics(self, event):
        if self.analytics is not None:
            try:
                self.analytics.observe(event)
            except Exception:
                # Noncritical telemetry never prevents complaint/notification acknowledgement.
                # Local direct reads remain correct; cloud manifests also expire independently.
                logger.warning(
                    "operation=analytics_checkpoint error_category=RECONCILIATION_REQUIRED"
                )

    def batch(self, size=20):
        size = max(1, min(size, 100))
        dispatched = sum(self.repository.dispatch_one() for _ in range(size))
        processed = sum(self.process_one() for _ in range(size))
        return {"dispatched": dispatched, "processed": processed}


def build_workflow_service(settings, matching, incidents, priorities, work):
    if settings.complaint_provider == "sqlite":
        from app.repositories.event_repository import SQLiteEvents

        repository = SQLiteEvents(incidents.repository.store)
    else:
        from app.integrations.database.dynamodb_events import DynamoEvents

        repository = DynamoEvents(settings, incidents)
    return WorkflowService(repository, matching, incidents, priorities, work)
