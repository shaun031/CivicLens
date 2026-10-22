from app.core.config import Settings
from app.integrations.database.dynamodb_complaints import DynamoComplaints
from app.integrations.database.sqlite_complaints import SQLiteComplaints
from app.integrations.storage.local_evidence import LocalEvidence
from app.integrations.storage.s3_evidence import S3Evidence
from app.repositories.auth_store import AuthStore
from app.services.complaint_service import ComplaintService
from app.services.evidence_service import EvidenceService


def build_complaint_service(settings: Settings, store: AuthStore | None = None) -> ComplaintService:
    if settings.complaint_provider == "sqlite" and settings.evidence_provider == "local":
        if store is None or settings.local_evidence_root is None:
            raise ValueError(
                "Local complaint storage requires the shared authentication store and evidence root"
            )
        repository = SQLiteComplaints(store, settings)
        storage = LocalEvidence(settings.local_evidence_root, settings.max_upload_bytes)
    elif settings.complaint_provider == "dynamodb" and settings.evidence_provider == "s3":
        if not settings.complaints_table_name or not settings.evidence_bucket_name:
            raise ValueError(
                "AWS complaint storage requires COMPLAINTS_TABLE_NAME and EVIDENCE_BUCKET_NAME; "
                "no local fallback"
            )
        repository = DynamoComplaints(settings)
        storage = S3Evidence(settings.evidence_bucket_name, settings.max_upload_bytes)
    else:
        raise ValueError("Unsupported complaint/evidence provider selection")
    return ComplaintService(repository, storage, EvidenceService(settings))
