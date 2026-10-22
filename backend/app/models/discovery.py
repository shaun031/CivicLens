"""Separate private search/public contracts. Never serialize a Complaint as a public issue."""

import re
import unicodedata
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from app.models.complaint import Category, Severity

Status = Literal["SUBMITTED", "UNDER_REVIEW", "ASSIGNED", "IN_PROGRESS", "RESOLVED", "REJECTED"]
PublicationStatus = Literal["PRIVATE", "PENDING_REVIEW", "PUBLISHED", "REJECTED"]


def search_terms(value: str) -> list[str]:
    value = "".join(
        c for c in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(c)
    )
    return re.findall(r"[^\W_]+", value, re.UNICODE)


def search_normalize(value: str) -> str:
    return " ".join(search_terms(value))


def search_matches(text: str, query: str) -> bool:
    words = search_terms(text)
    return all(any(word.startswith(term) for word in words) for term in search_terms(query))


class SearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    q: str = Field(default="", max_length=160)
    category: Category | None = None
    status: Status | None = None
    reportedSeverity: Severity | None = None
    dateFrom: date | None = None
    dateTo: date | None = None
    sortBy: Literal["createdAt", "category", "status"] = "createdAt"
    sortOrder: Literal["asc", "desc"] = "desc"

    @field_validator("q")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        if any(ord(c) < 32 for c in value):
            raise ValueError("Search cannot contain control characters")
        return search_normalize(value)

    @model_validator(mode="after")
    def valid_dates(self):
        if self.dateFrom and self.dateTo and self.dateFrom > self.dateTo:
            raise ValueError("dateFrom must not be after dateTo")
        return self


class PublicationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    requested: bool


class SearchQuery(SearchFilters):
    limit: int = Field(default=20, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=2048)


class PublicationReview(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)
    decision: Literal["APPROVE", "REJECT", "UNPUBLISH"]
    publicSummary: str | None = Field(default=None, min_length=15, max_length=300)
    publicLatitude: float | None = Field(default=None, ge=-90, le=90)
    publicLongitude: float | None = Field(default=None, ge=-180, le=180)
    reviewedForPrivacy: StrictBool = False

    @model_validator(mode="after")
    def privacy_review(self):
        if self.decision == "APPROVE":
            if (
                not self.reviewedForPrivacy
                or self.publicSummary is None
                or self.publicLatitude is None
                or self.publicLongitude is None
            ):
                raise ValueError(
                    "Approval requires reviewed summary, coordinates "
                    "and explicit privacy confirmation"
                )
            # Human review is mandatory. Conservative checks are not a complete PII detector.
            if re.search(r"[<>@]|https?://|(?:\+?\d[\s().-]*){7,}", self.publicSummary) or any(
                ord(c) < 32 for c in self.publicSummary
            ):
                raise ValueError("Public summary must exclude contact details, links and markup")
        return self


class Publication(BaseModel):
    citizenRequestedPublication: bool = False
    publicationStatus: PublicationStatus = "PRIVATE"
    publicIssueId: str | None = None
    publicSummary: str | None = None
    publicLatitude: float | None = None
    publicLongitude: float | None = None
    publishedAt: str | None = None


class PublicIssue(BaseModel):
    model_config = ConfigDict(extra="ignore")
    publicIssueId: str
    category: Category
    status: Status
    summary: str
    latitude: float
    longitude: float
    publishedAt: str
    distanceMeters: float | None = None


class PublicIssuePage(BaseModel):
    items: list[PublicIssue]
    nextCursor: str | None = None


class GeographicBounds(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    minLatitude: float = Field(ge=-90, le=90)
    maxLatitude: float = Field(ge=-90, le=90)
    minLongitude: float = Field(ge=-180, le=180)
    maxLongitude: float = Field(ge=-180, le=180)


class Bounds(GeographicBounds):
    @model_validator(mode="after")
    def valid_box(self):
        width = (self.maxLongitude - self.minLongitude) % 360
        if self.minLatitude >= self.maxLatitude or width == 0:
            raise ValueError("Bounds must enclose a nonempty region")
        if self.maxLatitude - self.minLatitude > 0.25 or width > 0.25:
            raise ValueError("Map area is too large. Zoom in (maximum 0.25 degrees per side).")
        return self


class Nearby(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radiusMeters: int = Field(default=1000, ge=50, le=200000)


class CitizenNearby(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radiusKm: int = Field(default=10, ge=1, le=200)
    category: Category | None = None
    status: Status | None = None
    limit: int = Field(default=50, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=2048)

    def meters(self) -> Nearby:
        return Nearby(
            latitude=self.latitude, longitude=self.longitude, radiusMeters=self.radiusKm * 1000
        )


class NearbyIssue(BaseModel):
    """Public-safe projection, or a minimal owner-only projection; never a full Complaint."""

    issueId: str
    title: str
    category: Category
    status: Status
    latitude: float
    longitude: float
    distanceMeters: float
    createdAt: str
    dateLabel: Literal["Reported", "Published"]
    isOwn: bool
    isPublic: bool
    detailsUrl: str


class NearbyIssuePage(BaseModel):
    items: list[NearbyIssue]
    nextCursor: str | None = None
    countPolicy: str = (
        "Individual visible reports, not unique incidents. Map clusters are visual only."
    )
