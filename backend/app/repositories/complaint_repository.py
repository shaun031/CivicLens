from typing import Protocol

from app.models.complaint import Complaint, ComplaintPage, ComplaintSummary
from app.models.discovery import SearchFilters


class RepositoryUnavailable(Exception):
    """A definite, rolled-back failure; staged evidence may be cleaned up."""


class RepositoryUncertain(RepositoryUnavailable):
    """Commit outcome is unknown; preserve staged evidence for reconciliation."""


class ComplaintRepository(Protocol):
    def request(self, citizen: str, key: str, fingerprint: str) -> Complaint | None: ...
    def create(
        self, complaint: Complaint, key: str, fingerprint: str
    ) -> tuple[Complaint, bool]: ...
    def get(self, complaint_id: str, citizen: str) -> Complaint | None: ...
    def list(
        self, citizen: str, limit: int, cursor: str | None, filters: SearchFilters | None = None
    ) -> ComplaintPage: ...
    def summary(self, citizen: str, days: int = 30) -> ComplaintSummary: ...
