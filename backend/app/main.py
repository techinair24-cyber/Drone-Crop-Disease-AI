import logging
import os
import re
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from io import BytesIO
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image, UnidentifiedImageError

from .config import get_settings
from .model_adapter import DiseaseModel, InvalidImageError, ModelUnavailableError
from .schemas import Detection, DetectionPage, HealthResponse, StatsResponse, SystemStatus
from .storage import DetectionStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)
settings = get_settings()
store = DetectionStore(settings.database_path, settings.uploads_path)
model = DiseaseModel(settings.model_path, settings.model_threshold, settings.model_name)
if settings.model_path and not 0 <= settings.model_threshold <= 1:
    raise ValueError("MODEL_SCORE_THRESHOLD must be between 0 and 1.")
if not settings.cors_origins:
    raise ValueError("CORS_ORIGINS must contain at least one allowed origin.")
if os.getenv("ENVIRONMENT", "development").lower() == "production" and "*" in settings.cors_origins:
    raise ValueError("Wildcard CORS origins are not allowed in production.")
if settings.max_upload_bytes <= 0:
    raise ValueError("MAX_UPLOAD_BYTES must be a positive integer.")
if settings.gps_max_skew_seconds < 0:
    raise ValueError("GPS_MAX_SKEW_SECONDS must not be negative.")


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.initialize()
    model.load()
    yield


app = FastAPI(
    title="DroneCrop AI API",
    version="1.0.0",
    description="Image inference and detection records for DroneCrop AI.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(HTTPException)
async def http_error_handler(_: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": detail})


@app.exception_handler(Exception)
async def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled request error: %s", type(exc).__name__)
    return JSONResponse(status_code=500, content={"detail": "The request could not be completed."})


@app.middleware("http")
async def log_requests(request: Request, call_next):
    response = await call_next(request)
    logger.info("request method=%s path=%s status=%s", request.method, request.url.path, response.status_code)
    return response


@app.get("/health", response_model=HealthResponse)
def health() -> dict:
    model_status = model.status()
    return {
        "status": "ok" if model_status["available"] else "degraded",
        "backend": "available",
        "model": model_status,
    }


@app.get("/api/status", response_model=SystemStatus)
def system_status() -> dict:
    return {
        "camera": {"available": False, "status": "unavailable"},
        "gps": {"available": False, "status": "unavailable"},
        "model": model.status(),
        "telemetry": {"available": False, "status": "unavailable"},
    }


def _filters(
    crop: str | None,
    disease: str | None,
    search: str | None,
    from_date: date | None,
    to_date: date | None,
) -> None:
    if from_date and to_date and from_date > to_date:
        raise HTTPException(status_code=422, detail="from_date must not be after to_date.")
    if any(value is not None and len(value) > 100 for value in (crop, disease, search)):
        raise HTTPException(status_code=422, detail="Filter values must be 100 characters or fewer.")


@app.get("/api/detections", response_model=DetectionPage)
def list_detections(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    crop: str | None = None,
    disease: str | None = None,
    search: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    _filters(crop, disease, search, from_date, to_date)
    return store.list(page, page_size, crop, disease, search, from_date, to_date)


@app.get("/api/detections/{detection_id}", response_model=Detection)
def get_detection(detection_id: str) -> dict:
    detection = store.get(detection_id)
    if detection is None:
        raise HTTPException(status_code=404, detail="Detection record not found.")
    return detection


@app.get("/api/locations", response_model=DetectionPage)
def list_locations(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 500,
    crop: str | None = None,
    disease: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    _filters(crop, disease, None, from_date, to_date)
    return store.list(page, page_size, crop, disease, None, from_date, to_date, locations_only=True)


@app.get("/api/stats", response_model=StatsResponse)
def stats() -> dict:
    return store.stats()


@app.post("/api/predict", response_model=Detection, status_code=201)
async def predict(
    file: Annotated[UploadFile, File()],
    latitude: Annotated[float | None, Form(ge=-90, le=90)] = None,
    longitude: Annotated[float | None, Form(ge=-180, le=180)] = None,
    gps_fix_valid: bool | None = Form(default=None),
    gps_timestamp: datetime | None = Form(default=None),
    captured_at: datetime | None = Form(default=None),
) -> dict:
    if (latitude is None) != (longitude is None):
        raise HTTPException(status_code=422, detail="Latitude and longitude must be supplied together.")
    gps_metadata = (gps_fix_valid, gps_timestamp, captured_at)
    if latitude is None and any(value is not None for value in gps_metadata):
        raise HTTPException(status_code=422, detail="GPS metadata requires latitude and longitude.")
    if latitude is not None:
        if gps_fix_valid is not True or gps_timestamp is None or captured_at is None:
            raise HTTPException(
                status_code=422,
                detail="GPS coordinates require a valid fix and both GPS and image capture timestamps.",
            )
        if gps_timestamp.tzinfo is None or captured_at.tzinfo is None:
            raise HTTPException(status_code=422, detail="GPS and capture timestamps must include a timezone.")
        if abs((gps_timestamp - captured_at).total_seconds()) > settings.gps_max_skew_seconds:
            raise HTTPException(
                status_code=422,
                detail=f"GPS fix and image capture must be within {settings.gps_max_skew_seconds} seconds.",
            )
    image_bytes = await file.read(settings.max_upload_bytes + 1)
    if len(image_bytes) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail=f"Image exceeds the {settings.max_upload_bytes // (1024 * 1024)} MB upload limit.")
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image_format = image.format
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise HTTPException(status_code=415, detail="Upload a valid JPG or PNG image.") from exc
    if image_format not in {"JPEG", "PNG"}:
        raise HTTPException(status_code=415, detail="Only JPG, JPEG, and PNG images are supported.")
    if not model.available:
        raise HTTPException(status_code=503, detail=model.status()["message"])
    try:
        result = model.infer(image_bytes)
    except ModelUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except InvalidImageError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Image inference failed.")
        raise HTTPException(status_code=500, detail="Image inference failed.") from exc

    extension = ".jpg" if image_format == "JPEG" else ".png"
    filename = f"{uuid.uuid4().hex}{extension}"
    image_path = settings.uploads_path / filename
    try:
        image_path.write_bytes(image_bytes)
        record = store.create({
            "id": str(uuid.uuid4()),
            "filename": filename,
            "crop_name": result.crop_name,
            "disease_name": result.disease_name,
            "classification": result.classification,
            "prediction_score": result.prediction_score,
            "latitude": latitude,
            "longitude": longitude,
            "gps_fix_valid": gps_fix_valid if latitude is not None else None,
            "gps_timestamp": gps_timestamp.astimezone(timezone.utc).isoformat() if gps_timestamp else None,
            "captured_at": captured_at.astimezone(timezone.utc).isoformat() if captured_at else None,
            "model_name": result.model_name,
            "model_version": result.model_version,
            "top_predictions": result.top_predictions,
        })
    except (OSError, sqlite3.Error):
        image_path.unlink(missing_ok=True)
        logger.exception("Could not persist an inference result.")
        raise HTTPException(status_code=500, detail="The inference result could not be saved.") from None
    logger.info("detection_saved id=%s classification=%s", record["id"], record["classification"])
    return record


@app.get("/api/images/{filename}")
def get_image(filename: str):
    if not re.fullmatch(r"[a-f0-9]{32}\.(?:jpg|png)", filename):
        raise HTTPException(status_code=404, detail="Image not found.")
    image_path = settings.uploads_path / filename
    if not image_path.is_file() or image_path.parent.resolve() != settings.uploads_path.resolve():
        raise HTTPException(status_code=404, detail="Image not found.")
    media_type = "image/jpeg" if image_path.suffix == ".jpg" else "image/png"
    return FileResponse(image_path, media_type=media_type)
