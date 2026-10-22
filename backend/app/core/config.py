import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Validated application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="CivicLens", min_length=1)
    app_env: Literal["local", "test", "aws", "demo", "production"] = "local"
    auth_provider: Literal["local", "cognito"] | None = None
    local_db_path: Path = Path(__file__).resolve().parents[2] / "data" / "civiclens_local.db"
    session_ttl_seconds: int = Field(default=28800, ge=60, le=86400)
    reset_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    cookie_secure: bool = False
    cognito_issuer: str | None = None
    cognito_client_id: str | None = None
    cognito_domain: str | None = None
    cognito_api_scope: str = "civiclens/access"
    debug: bool = True
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    log_level: Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"] = "INFO"
    complaints_table_name: str | None = Field(default=None, min_length=3)
    incidents_table_name: str | None = Field(default=None, min_length=3)
    audit_events_table_name: str | None = Field(default=None, min_length=3)
    evidence_bucket_name: str | None = Field(default=None, min_length=3)
    complaint_provider: Literal["sqlite", "dynamodb"] | None = None
    evidence_provider: Literal["local", "s3"] | None = None
    local_evidence_root: Path | None = None
    complaint_description_max: int = Field(default=2000, ge=20, le=2000)
    complaint_rate_limit: int = Field(default=10, ge=1, le=100)
    complaint_rate_window: int = Field(default=900, ge=60, le=86400)
    max_upload_bytes: int = Field(default=1572864, ge=1024, le=1572864)
    max_complaint_request_bytes: int = Field(default=3407872, ge=3276800, le=3670016)
    max_api_request_bytes: int = Field(default=65536, ge=16384, le=1048576)
    max_image_pixels: int = Field(default=4000000, ge=1, le=4000000)
    max_image_dimension: int = Field(default=4096, ge=1, le=4096)
    public_query_rate_limit: int = Field(default=120, ge=1, le=600)
    discovery_candidate_limit: int = Field(default=2000, ge=100, le=5000)
    nearby_max_radius_meters: int = Field(default=200000, ge=50, le=200000)
    cloud_discovery_regions_ready: bool = False
    cloud_owner_query_limit: int = Field(default=5000, ge=100, le=10000)
    matching_candidate_limit: int = Field(default=100, ge=1, le=500)
    matching_radius_meters: float = Field(default=50, ge=5, le=500)
    matching_streetlight_radius: float = Field(default=30, ge=5, le=500)
    matching_pothole_radius: float = Field(default=50, ge=5, le=500)
    matching_road_radius: float = Field(default=75, ge=5, le=500)
    matching_drainage_radius: float = Field(default=75, ge=5, le=500)
    matching_strong_threshold: float = Field(default=0.80, ge=0.60, le=1)
    matching_review_threshold: float = Field(default=0.60, ge=0, le=0.80)
    matching_worker_enabled: bool = True
    matching_job_seconds: float = Field(default=8, ge=1, le=10)
    clustering_mode: Literal["REVIEW_ONLY", "CONSERVATIVE_AUTO_LINK"] = "REVIEW_ONLY"
    clustering_auto_threshold: float = Field(default=0.90, ge=0.90, le=1)
    clustering_auto_span_meters: float = Field(default=10, ge=1, le=10)
    clustering_manual_span_meters: float = Field(default=75, ge=10, le=100)
    clustering_max_members: int = Field(default=30, ge=2, le=30)
    clustering_target_limit: int = Field(default=5, ge=1, le=10)
    clustering_require_images: bool = True
    priority_weights: list[float] = [0.40, 0.25, 0.20, 0.15]
    priority_bands: list[float] = [40, 60, 80]
    priority_reporter_saturation: int = Field(default=30, ge=1, le=1000000)
    priority_aging_days: float = Field(default=30, ge=1, le=3650)
    priority_refresh_seconds: int = Field(default=3600, ge=60, le=86400)
    assignment_mode: Literal["MANUAL_APPROVAL", "CONSERVATIVE_AUTO_ASSIGN"] = "MANUAL_APPROVAL"
    workload_weights: list[float] = [1, 2, 3, 4]
    workflow_table_name: str | None = Field(default=None, min_length=3)
    event_bus_name: str | None = None
    triage_state_machine_arn: str | None = None
    operational_alert_topic_arn: str | None = None
    operational_alerts_enabled: bool = False
    analytics_timezone: str = "UTC"
    analytics_scope: str = Field(default="municipality", pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    analytics_max_incidents: int = Field(default=5000, ge=500, le=10000)
    analytics_max_complaints: int = Field(default=10000, ge=1000, le=20000)
    analytics_service_areas: dict[str, list[float]] = {}
    recurrence_radius_meters: float = Field(default=150, ge=10, le=500, allow_inf_nan=False)
    recurrence_horizon_days: int = Field(default=730, ge=1, le=3650)
    recurrence_review_threshold: float = Field(default=0.65, ge=0.1, le=1, allow_inf_nan=False)
    fairness_minimum_sample: int = Field(default=10, ge=3, le=100)
    fairness_response_ratio: float = Field(default=2, gt=1, le=10, allow_inf_nan=False)
    fairness_rate_gap: float = Field(default=0.2, gt=0, le=1, allow_inf_nan=False)

    @field_validator("analytics_timezone")
    @classmethod
    def reporting_timezone(cls, value):
        from app.analytics.filters import validate_timezone

        return validate_timezone(value)

    @field_validator("analytics_service_areas")
    @classmethod
    def reporting_areas(cls, value):
        import math

        for name, bounds in value.items():
            if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", name) or len(bounds) != 4:
                raise ValueError("Named service areas require south,west,north,east")
            if not all(math.isfinite(v) for v in bounds):
                raise ValueError("Finite service-area coordinates required")
            s, w, n, e = bounds
            if not (-90 <= s < n <= 90 and -180 <= w < e <= 180):
                raise ValueError("Invalid non-wrapping service area")
        return value

    @field_validator("workload_weights")
    @classmethod
    def valid_workload(cls, value):
        from app.algorithms.department_assignment.officer_allocator import validate_weights

        validate_weights(value)
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        """Accept a JSON array or comma-separated list for shell convenience."""
        if not isinstance(value, str):
            return value
        value = value.strip()
        if value.startswith("["):
            return json.loads(value)
        return [origin.strip() for origin in value.split(",") if origin.strip()]

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, origins: list[str]) -> list[str]:
        for origin in origins:
            if origin == "*":
                continue
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in ("http", "https")
                or not parsed.hostname
                or origin != f"{parsed.scheme}://{parsed.netloc}"
                or parsed.username is not None
                or parsed.password is not None
                or "*" in origin
            ):
                raise ValueError("CORS origins must be exact HTTP(S) origins or '*'")
        return origins

    @model_validator(mode="after")
    def prevent_unsafe_production_settings(self) -> "Settings":
        from app.algorithms.priority_scoring.config import PriorityConfig

        PriorityConfig.from_settings(self)
        if self.matching_review_threshold >= self.matching_strong_threshold:
            raise ValueError("Matching review threshold must be below strong threshold")
        cloud = self.app_env in ("aws", "demo", "production")
        self.complaint_provider = self.complaint_provider or ("dynamodb" if cloud else "sqlite")
        self.evidence_provider = self.evidence_provider or ("s3" if cloud else "local")
        if (self.complaint_provider, self.evidence_provider) != (
            ("dynamodb", "s3") if cloud else ("sqlite", "local")
        ):
            raise ValueError("Complaint/evidence providers must match the application environment")
        if not cloud and self.local_evidence_root is None:
            self.local_evidence_root = self.local_db_path.parent / "evidence"
        if not cloud and self.local_evidence_root is not None:
            root = self.local_evidence_root.resolve()
            project = Path(__file__).resolve().parents[3]
            for public in (project / "frontend" / "public", project / "frontend" / "dist"):
                if root == public or public in root.parents:
                    raise ValueError("Evidence storage cannot be inside public frontend assets")
        if self.auth_provider is None:
            self.auth_provider = "cognito" if cloud else "local"
        if cloud and self.auth_provider != "cognito":
            raise ValueError("Local authentication is forbidden in AWS environments")
        if not cloud and self.auth_provider != "local":
            raise ValueError("Use APP_ENV=aws for Cognito authentication")
        if cloud and self.debug:
            raise ValueError("DEBUG must be false in demo and production")
        if "*" in self.cors_origins:
            raise ValueError("Wildcard CORS is not allowed in demo or production")
        if cloud:
            if not self.cognito_issuer or not re.fullmatch(
                r"https://cognito-idp\.[a-z0-9-]+\.amazonaws\.com(?:\.cn)?/[a-z0-9-]+_[A-Za-z0-9]+",
                self.cognito_issuer,
            ):
                raise ValueError("A valid Cognito issuer is required in AWS mode")
            if not self.cognito_client_id or not re.fullmatch(r"[a-z0-9]+", self.cognito_client_id):
                raise ValueError("A valid Cognito app client ID is required in AWS mode")
            if not self.cognito_domain or not re.fullmatch(
                r"https://[a-z0-9-]+\.auth\.[a-z0-9-]+\.amazoncognito\.com(?:\.cn)?",
                self.cognito_domain,
            ):
                raise ValueError("A Cognito login domain is required in AWS mode")
        if self.app_env == "production":
            for origin in self.cors_origins:
                parsed = urlsplit(origin)
                if parsed.scheme != "https" or parsed.hostname in ("localhost", "127.0.0.1", "::1"):
                    raise ValueError(
                        "Production CORS origins must use HTTPS without loopback hosts"
                    )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the process configuration without mutable shared state."""
    return Settings()
