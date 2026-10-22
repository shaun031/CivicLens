import asyncio
import logging
import time
from contextlib import suppress

from app.algorithms.duplicate_detection.candidate_selection import ACTIVE_STATUSES, select
from app.algorithms.duplicate_detection.config import MatchingConfig
from app.algorithms.duplicate_detection.image_similarity import compare, fingerprint
from app.algorithms.duplicate_detection.matching_engine import match, rank
from app.algorithms.duplicate_detection.text_similarity import TEXT_ENGINE
from app.integrations.storage.base import StorageUnavailable
from app.repositories.duplicate_candidate_repository import (
    DuplicateRepository,
    SQLiteDuplicateRepository,
    match_input,
)

logger = logging.getLogger(__name__)


class DuplicateDetectionService:
    def __init__(
        self, repository: DuplicateRepository, storage, config: MatchingConfig, seconds: float = 8
    ):
        self.repository, self.storage, self.config, self.seconds = (
            repository,
            storage,
            config,
            seconds,
        )

    def fingerprints(self, complaint):
        result = []
        for image in complaint.images[:2]:
            try:
                cached = self.repository.cached(image.imageId)
                if cached is None:
                    cached = fingerprint(self.storage.get(image.storageKey))
                    if cached is not None:
                        self.repository.cache(image.imageId, cached)
                if cached is not None:
                    result.append(cached)
            except (StorageUnavailable, OSError, ValueError):
                # Missing/corrupt evidence does not become a score of zero.
                continue
        return result

    def process_one(self, source_id: str | None = None) -> dict | None:
        claim = self.repository.claim(source_id)
        if claim is None:
            return None
        source_id, token = claim
        started = time.perf_counter()
        try:
            if hasattr(self, "incidents"):
                self.incidents.ensure_singleton(source_id)
            complaint = self.repository.load(source_id)
            if complaint is None:
                raise ValueError("Source unavailable")
            source = match_input(complaint)
            retrieval_start = time.perf_counter()
            nearby, truncated = (
                self.repository.nearby(source, self.config)
                if source.status in ACTIVE_STATUSES
                else ([], False)
            )
            retrieval_ms = (time.perf_counter() - retrieval_start) * 1000
            selection = select(source, [match_input(row) for row in nearby], self.config, truncated)
            by_id = {row.complaintId: row for row in nearby}
            image_start = time.perf_counter()
            source_images = self.fingerprints(complaint) if selection.items else []
            image_ms = (time.perf_counter() - image_start) * 1000
            results, deadline = [], False
            for item in selection.items:
                if time.perf_counter() - started >= self.seconds:
                    deadline = True
                    break
                image_start = time.perf_counter()
                images = compare(source_images, self.fingerprints(by_id[item.complaint_id]))
                image_ms += (time.perf_counter() - image_start) * 1000
                results.append(match(source, item, self.config, images))
            report = {
                "sourceComplaintId": source_id,
                "configVersion": self.config.version,
                "modelVersion": TEXT_ENGINE.version,
                "candidateIds": [result.candidateId for result in rank(results)],
                "compared": len(results),
                "retrieved": selection.retrieved,
                "queryTruncated": selection.truncated,
                "timeBudgetExceeded": deadline,
                "incomplete": selection.truncated or deadline,
                "historicalPolicy": "ACTIVE_ONLY; resolved and rejected excluded",
                "timings": {
                    "retrievalMs": retrieval_ms,
                    "imageMs": image_ms,
                    "geographicMs": sum(r.timings["geographicMs"] for r in results),
                    "textMs": sum(r.timings["textMs"] for r in results),
                    "fusionMs": sum(r.timings["fusionMs"] for r in results),
                    "totalMs": (time.perf_counter() - started) * 1000,
                },
            }
            self.repository.finish(source_id, token, rank(results), report)
            if hasattr(self, "incidents"):
                self.incidents.repository.enqueue(source_id)
            return report
        except Exception as error:
            # Never log descriptions, evidence bytes, keys, credentials or stack traces.
            logger.warning("operation=duplicate_check error_category=%s", type(error).__name__)
            self.repository.fail(source_id, token, type(error).__name__)
            return {"state": "RETRY", "errorCategory": type(error).__name__}

    async def worker(self, stopped: asyncio.Event) -> None:
        while not stopped.is_set():
            try:
                if hasattr(self, "workflows"):
                    await asyncio.to_thread(self.workflows.batch, 5)
                result = await asyncio.to_thread(self.process_one)
                if hasattr(self, "incidents"):
                    clustered = await asyncio.to_thread(self.incidents.process_one)
                    result = result or clustered
                if hasattr(self, "priorities"):
                    priority = await asyncio.to_thread(self.priorities.process_one)
                    result = result or priority
                if hasattr(self, "work"):
                    work = await asyncio.to_thread(self.work.process_one)
                    result = result or work
            except Exception as error:
                logger.warning("operation=matching_worker error_category=%s", type(error).__name__)
                result = None
            with suppress(TimeoutError):
                await asyncio.wait_for(stopped.wait(), timeout=0.1 if result else 2)


def build_duplicate_service(settings, complaints):
    if settings.complaint_provider == "sqlite":
        repository = SQLiteDuplicateRepository(complaints.repository)
    else:
        from app.integrations.database.dynamodb_duplicates import DynamoDuplicateRepository

        repository = DynamoDuplicateRepository(complaints.repository)
    return DuplicateDetectionService(
        repository,
        complaints.storage,
        MatchingConfig.from_settings(settings),
        settings.matching_job_seconds,
    )
