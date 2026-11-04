from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PredictionItem(BaseModel):
    label: str
    score: float = Field(ge=0, le=1)


class GeminiDiseaseAnalysis(BaseModel):
    assessment: Literal["likely_disease", "possible_causes", "inconclusive"]
    likely_disease: str | None = None
    possible_causes: list[str] = Field(default_factory=list)
    explanation: str
    visible_symptoms: list[str] = Field(default_factory=list)
    immediate_actions: list[str] = Field(default_factory=list)
    treatment_management: list[str] = Field(default_factory=list)
    organic_options: list[str] = Field(default_factory=list)
    prevention: list[str] = Field(default_factory=list)
    follow_up: list[str] = Field(default_factory=list)
    expert_guidance: str


class Detection(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    image_url: str
    crop_name: str | None = None
    crop_confidence: float | None = Field(default=None, ge=0, le=1)
    health_status: Literal["Healthy", "Unhealthy"] | None = None
    health_confidence: float | None = Field(default=None, ge=0, le=1)
    health_probabilities: dict[str, float] | None = None
    message: str | None = None
    recommendation_reviewed: bool = False
    source: Literal["analysis", "live_monitoring"] | None = None
    gemini_analysis: GeminiDiseaseAnalysis | None = None
    gemini_status: Literal[
        "pending",
        "running",
        "completed",
        "failed",
        "not_configured",
        "not_applicable",
    ] | None = None
    gemini_error: str | None = None
    disease_name: str
    classification: Literal["healthy", "diseased", "inconclusive"]
    prediction_score: float | None = Field(default=None, ge=0, le=1)
    created_at: datetime
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    gps_fix_valid: bool | None = None
    gps_timestamp: datetime | None = None
    captured_at: datetime | None = None
    model_name: str | None = None
    model_version: str | None = None
    top_predictions: list[PredictionItem] = Field(default_factory=list)


class DetectionPage(BaseModel):
    items: list[Detection]
    page: int
    page_size: int
    total: int
    pages: int


class RecommendationSummary(BaseModel):
    total_unhealthy: int
    pending: int
    reviewed: int
    crop_counts: dict[str, int]


class RecommendationPage(BaseModel):
    items: list[Detection]
    page: int
    page_size: int
    total: int
    pages: int
    summary: RecommendationSummary


class ModelStatus(BaseModel):
    available: bool
    status: Literal["available", "unavailable", "not_configured", "error"]
    name: str | None = None
    version: str | None = None
    message: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    backend: Literal["available"]
    model: ModelStatus


class DeviceStatus(BaseModel):
    available: bool = False
    status: Literal["available", "unavailable"] = "unavailable"


class SystemStatus(BaseModel):
    camera: DeviceStatus
    gps: DeviceStatus
    model: ModelStatus
    telemetry: DeviceStatus


class CropCount(BaseModel):
    crop_name: str
    count: int
    percentage: float


class CropDiseaseCount(BaseModel):
    crop_name: str
    disease_name: str
    count: int


class ActivityCount(BaseModel):
    date: str
    count: int


class StatsResponse(BaseModel):
    total_images: int
    diseased_images: int
    healthy_images: int
    inconclusive_images: int
    geolocated_images: int
    crop_distribution: list[CropCount]
    disease_distribution: list[CropDiseaseCount]
    activity: list[ActivityCount]
