from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PredictionItem(BaseModel):
    label: str
    score: float = Field(ge=0, le=1)


class Detection(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    image_url: str
    crop_name: str | None = None
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
