"""Transport-independent entry points; AWS mode never constructs a SQLite store."""

from app.models.incident import IncidentError


class WorkService:
    def __init__(self, repository, incidents):
        self.repository, self.incidents = repository, incidents

    def detail(self, identity, officer=None):
        if not officer:
            identity = self.incidents.resolve(identity)[0].incidentId
        result = self.repository.detail(identity, officer)
        if officer:
            result["evidence"] = [
                {"complaintId": member.complaint.complaintId, "imageId": photo.imageId}
                for member in self.incidents.members(identity)
                for photo in member.complaint.images
            ]
        return result

    def recommend(self, identity):
        return self.detail(identity)["recommendations"]

    def process_one(self):
        return self.repository.process_one()

    def route_event(self, event):
        """Trusted versioned future processing port, not an HTTP route or enabled scheduler.

        Producers retain the exact envelope/operation UUID on retry. No event bus is created here.
        """
        from uuid import UUID

        from app.models.incident import Actor
        from app.schemas.work import AssignmentAction

        try:
            if (
                set(event) != {"version", "incidentId", "action"}
                or type(event["version"]) is not int
                or event["version"] != 1
            ):
                raise ValueError
            identity = str(UUID(str(event["incidentId"])))
            data = AssignmentAction.model_validate(event["action"]).model_dump(mode="json")
        except (ValueError, TypeError, KeyError) as error:
            raise IncidentError(422, "Invalid version1 routing event") from error
        return self.repository.assign(
            identity, "ROUTE", data, Actor("department-event-port", "SYSTEM")
        )

    def evidence(self, identity, complaint_id, image_id, officer):
        # Recheck assignment, eligibility and authoritative complaint membership on every request.
        self.repository.detail(identity, officer)
        member = self.incidents.require_member(complaint_id)
        if member.complaint.incidentId != identity:
            raise IncidentError(404, "Supporting evidence not found")
        photo = next((p for p in member.complaint.images if p.imageId == image_id), None)
        if photo is None:
            raise IncidentError(404, "Supporting evidence not found")
        from app.integrations.storage.base import StorageUnavailable

        try:
            data = self.incidents.matching.storage.get(photo.storageKey)
        except StorageUnavailable as error:
            raise IncidentError(503, "Supporting evidence is temporarily unavailable") from error
        self.repository.detail(identity, officer)
        return data


def build_work_service(settings, incidents, priorities):
    if settings.complaint_provider == "sqlite":
        from app.repositories.work_repository import SQLiteWork

        repository = SQLiteWork(incidents.repository.store, priorities.config.version, settings)
    else:
        from app.integrations.database.dynamodb_work import DynamoWork

        repository = DynamoWork(incidents.repository, priorities.config.version, settings)
    return WorkService(repository, incidents)
