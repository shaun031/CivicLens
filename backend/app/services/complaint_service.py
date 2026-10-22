import hashlib
import logging
import time
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException

from app.integrations.storage.base import EvidenceStorage, StorageCollision, StorageUnavailable
from app.models.complaint import Complaint, ComplaintImage, ComplaintInput
from app.repositories.complaint_repository import (
    ComplaintRepository,
    RepositoryUnavailable,
    RepositoryUncertain,
)
from app.services.evidence_service import EvidenceService, Upload

logger = logging.getLogger(__name__)


class ComplaintService:
    def __init__(
        self, repository: ComplaintRepository, storage: EvidenceStorage, evidence: EvidenceService
    ):
        self.repository, self.storage, self.evidence = repository, storage, evidence

    def cleanup(self, keys: list[str], complaint_id: str) -> None:
        for key in keys:
            try:
                self.storage.delete(key)
            except StorageUnavailable:
                logger.error(
                    "evidence_cleanup_failed complaint_id=%s error_category=storage", complaint_id
                )

    def create(
        self, citizen: str, data: ComplaintInput, uploads: list[Upload], key: str, request_id: str
    ) -> Complaint:
        start = time.monotonic()
        if len(uploads) > 2:
            raise HTTPException(422, "A complaint accepts at most two images.")
        fingerprint = hashlib.sha256(
            data.model_dump_json().encode()
            + b"".join(
                hashlib.sha256(item.content).digest() + item.content_type.encode()
                for item in uploads
            )
        ).hexdigest()
        staged: list[str] = []
        complaint_id = str(uuid4())
        try:
            existing = self.repository.request(citizen, key, fingerprint)
            if existing:
                return existing
            sanitized = [self.evidence.sanitize(upload) for upload in uploads]
            timestamp = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            images: list[ComplaintImage] = []
            for content in sanitized:
                image_id = str(uuid4())
                storage_key = f"complaints/{complaint_id}/{image_id}.jpg"
                # Track before put: S3 may commit an object even when its response is lost.
                staged.append(storage_key)
                try:
                    self.storage.put(storage_key, content)
                except StorageCollision:
                    staged.pop()
                    raise
                images.append(
                    ComplaintImage(
                        imageId=image_id,
                        storageKey=storage_key,
                        fileSize=len(content),
                        createdAt=timestamp,
                        url=f"/complaints/{complaint_id}/images/{image_id}",
                    )
                )
            images.sort(key=lambda image: image.imageId)
            complaint = Complaint(
                **data.model_dump(),
                complaintId=complaint_id,
                citizenId=citizen,
                createdAt=timestamp,
                updatedAt=timestamp,
                images=images,
            )
            result, created = self.repository.create(complaint, key, fingerprint)
            if not created:
                self.cleanup(staged, complaint_id)
            logger.info(
                "request_id=%s operation=complaint_create complaint_id=%s duration_ms=%d",
                request_id,
                result.complaintId,
                int((time.monotonic() - start) * 1000),
            )
            return result
        except RepositoryUncertain as error:
            logger.error(
                "request_id=%s operation=complaint_create "
                "error_category=commit_uncertain complaint_id=%s",
                request_id,
                complaint_id,
            )
            raise HTTPException(
                503,
                "Submission outcome is uncertain. Retry the same request without editing it.",
            ) from error
        except (RepositoryUnavailable, StorageUnavailable) as error:
            self.cleanup(staged, complaint_id)
            logger.warning(
                "request_id=%s operation=complaint_create "
                "error_category=storage_or_database complaint_id=%s",
                request_id,
                complaint_id,
            )
            raise HTTPException(
                503, "Complaint could not be saved. Your draft is safe to retry."
            ) from error
        except HTTPException:
            self.cleanup(staged, complaint_id)
            raise

    def get(self, complaint_id: str, citizen: str) -> Complaint:
        try:
            complaint = self.repository.get(complaint_id, citizen)
        except RepositoryUnavailable as error:
            raise HTTPException(503, "Complaint database is unavailable.") from error
        if complaint is None:
            raise HTTPException(404, "Complaint not found.")
        return complaint

    def image(self, complaint_id: str, image_id: str, citizen: str) -> bytes:
        complaint = self.get(complaint_id, citizen)
        image = next((item for item in complaint.images if item.imageId == image_id), None)
        if image is None:
            raise HTTPException(404, "Image not found.")
        try:
            return self.storage.get(image.storageKey)
        except StorageUnavailable as error:
            raise HTTPException(503, "Photo evidence is temporarily unavailable.") from error
