from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReportingWindow(BaseModel):
    startInclusive: datetime
    endExclusive: datetime


class DataFreshness(BaseModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)
    mode: Literal["DIRECT_SNAPSHOT", "PROJECTION"]
    sourceRevision: int = Field(ge=0)
    projectionVersion: Literal[1]
    stalePriorityCount: int = Field(ge=0)
    stale: bool
    projectionCalculatedAt: datetime | None = None


class AnalyticsResponse(BaseModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)
    calculatedAt: datetime
    reportingTimezone: str
    scope: str
    window: ReportingWindow
    dataFreshness: DataFreshness
    filters: dict
    limitations: list[str]


class ReportPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    title: str
    reportType: str
    generatedAt: datetime
    reportingTimezone: str
    filters: dict
    window: ReportingWindow
    dataFreshness: DataFreshness
    definitions: str
    sampleSize: int = Field(ge=0, le=2000)
    columns: list[str]
    rows: list[dict]
    nextCursor: str | None = None
    pageOnly: bool
