from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.complaint import Category


class AnalyticsFilters(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    start: date | None = None
    end: date | None = None
    category: Category | None = None
    department: UUID | None = None
    priority: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL", "UNAVAILABLE"] | None = None
    status: Literal["OPEN", "RESOLVED"] | None = None
    assignment: (
        Literal[
            "UNASSIGNED", "DEPARTMENT_ASSIGNED", "OFFICER_ASSIGNED", "IN_PROGRESS", "NEEDS_REVIEW"
        ]
        | None
    ) = None
    urgent: bool | None = None
    area: str | None = Field(default=None, max_length=64)
    south: float | None = Field(default=None, ge=-90, le=90)
    west: float | None = Field(default=None, ge=-180, le=180)
    north: float | None = Field(default=None, ge=-90, le=90)
    east: float | None = Field(default=None, ge=-180, le=180)
    grouping: Literal["daily", "weekly", "monthly"] = "daily"
    grid: float = Field(default=0.01, ge=0.001, le=0.1)
    availability: Literal["AVAILABLE", "BUSY", "UNAVAILABLE", "ON_LEAVE"] | None = None
    minWorkload: float | None = Field(default=None, ge=0, le=1000000)
    maxWorkload: float | None = Field(default=None, ge=0, le=1000000)
    limit: int = Field(default=25, ge=1, le=50)
    cursor: str | None = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def combinations(self):
        coords = (self.south, self.west, self.north, self.east)
        if any(v is not None for v in coords):
            if any(v is None for v in coords):
                raise ValueError("All four geographic bounds are required")
            if not self.south < self.north or not self.west < self.east:
                raise ValueError("Non-wrapping south<north and west<east bounds required")
            if self.north - self.south > 2 or self.east - self.west > 2:
                raise ValueError("Geographic region is limited to2 degrees on each axis")
            if ((self.north - self.south) / self.grid + 2) * (
                (self.east - self.west) / self.grid + 2
            ) > 10000:
                raise ValueError("Choose a coarser grid or smaller region (maximum10000 cells)")
        if (
            self.minWorkload is not None
            and self.maxWorkload is not None
            and self.minWorkload > self.maxWorkload
        ):
            raise ValueError("Minimum workload exceeds maximum")
        return self

    def window(self, timezone: str, now: datetime):
        zone = ZoneInfo(timezone)
        end = self.end or now.astimezone(zone).date()
        start = self.start or end - timedelta(days=29)
        if start < date(1970, 1, 1) or end > date(2100, 12, 31):
            raise ValueError("Reporting dates must be within1970–2100")
        if end < start or (end - start).days >= 366:
            raise ValueError("Date range must contain1–366 reporting days")
        return (
            datetime.combine(start, time.min, zone).astimezone(UTC),
            datetime.combine(end + timedelta(days=1), time.min, zone).astimezone(UTC),
        )


def validate_timezone(value):
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError("A valid installed IANA reporting time zone is required") from error
    return value
