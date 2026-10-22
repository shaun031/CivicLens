from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Category(StrEnum):
    POTHOLE = "POTHOLE"
    DAMAGED_ROAD = "DAMAGED_ROAD"
    BROKEN_STREETLIGHT = "BROKEN_STREETLIGHT"
    GARBAGE = "GARBAGE"
    DRAINAGE = "DRAINAGE"
    PUBLIC_PROPERTY_DAMAGE = "PUBLIC_PROPERTY_DAMAGE"
    OTHER = "OTHER"


class Severity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ComplaintInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)
    title: str = Field(min_length=10, max_length=150)
    description: str = Field(min_length=20, max_length=2000)
    category: Category
    reportedSeverity: Severity
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    landmark: str | None = Field(default=None, max_length=200)
    addressLabel: str | None = Field(default=None, max_length=200)

    @field_validator("title", "description", "landmark", "addressLabel")
    @classmethod
    def reject_controls(cls, value: str | None) -> str | None:
        if value and any(ord(char) < 32 and char not in "\n\r\t" for char in value):
            raise ValueError("Control characters are not allowed")
        return value


class ComplaintImage(BaseModel):
    imageId: str
    storageKey: str = Field(exclude=True)
    contentType: str = "image/jpeg"
    fileSize: int
    createdAt: str
    url: str


class Complaint(ComplaintInput):
    complaintId: str
    citizenId: str
    status: str = "SUBMITTED"
    incidentId: str | None = None
    createdAt: str
    updatedAt: str
    images: list[ComplaintImage] = Field(default_factory=list)
    # Private owner-only publication metadata, separate from lifecycle status.
    publication: dict = Field(
        default_factory=lambda: {
            "citizenRequestedPublication": False,
            "publicationStatus": "PRIVATE",
            "publicIssueId": None,
            "publicSummary": None,
            "publicLatitude": None,
            "publicLongitude": None,
            "publishedAt": None,
        }
    )


class ComplaintPage(BaseModel):
    items: list[Complaint]
    nextCursor: str | None = None
    total: int | None = None


class ComplaintSummary(BaseModel):
    total: int
    counts: dict[str, int]
    recent: list[Complaint]
    byCategory: list[dict] = Field(default_factory=list)
    submissionTrend: list[dict] = Field(default_factory=list)
    recentActivity: list = Field(default_factory=list)
    trendDays: int = 30
