
import logging
import os
import re
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image, UnidentifiedImageError

from .config import get_settings
from .crop_adapter import CropModel, SUPPORTED_CROPS
from .gemini import GeminiAnalysisError, analyze_leaf_image
from .health_adapter import HealthModel
from .schemas import (
    Detection,
    DetectionPage,
    HealthResponse,
    RecommendationPage,
    StatsResponse,
    SystemStatus,
)
from .storage import DetectionStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()
store = DetectionStore(settings.database_path, settings.uploads_path)

models_path = Path(__file__).resolve().parents[1] / "models"
crop_model_path = models_path / "crop_classifier.tflite"
crop_model = CropModel(crop_model_path)
health_model_path = models_path / "health_classifier.tflite"
health_model = HealthModel(health_model_path)

if not settings.cors_origins:
    raise ValueError("CORS_ORIGINS must contain at least one allowed origin.")

if (
    os.getenv("ENVIRONMENT", "development").lower() == "production"
    and "*" in settings.cors_origins
):
    raise ValueError("Wildcard CORS origins are not allowed in production.")

if settings.max_upload_bytes <= 0:
    raise ValueError("MAX_UPLOAD_BYTES must be a positive integer.")

if settings.gps_max_skew_seconds < 0:
    raise ValueError("GPS_MAX_SKEW_SECONDS must not be negative.")


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.initialize()
    crop_model.load()
    health_model.load()
    yield


app = FastAPI(
    title="Leaf Disease Detection API",
    version="1.1.0",
    description="10-crop leaf identification and health classification API.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_error_handler(_: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": detail})


@app.exception_handler(Exception)
async def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled request error: %s", type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={"detail": "The request could not be completed."},
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    response = await call_next(request)
    logger.info(
        "request method=%s path=%s status=%s",
        request.method,
        request.url.path,
        response.status_code,
    )
    return response


@app.get("/health", response_model=HealthResponse)
def health() -> dict:
    model_status = _analysis_model_status()
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
        "model": _analysis_model_status(),
        "telemetry": {"available": False, "status": "unavailable"},
    }


def _analysis_model_status() -> dict:
    crop_status = crop_model.status()
    health_status = health_model.status()
    available = crop_status["available"] and health_status["available"]
    if available:
        status = "available"
        message = "Crop identification and health classification models loaded."
    else:
        component_statuses = (crop_status["status"], health_status["status"])
        status = (
            "error" if "error" in component_statuses else "not_configured"
        )
        message = "; ".join(
            component["message"]
            for component in (crop_status, health_status)
            if not component["available"]
        )

    return {
        "available": available,
        "status": status,
        "name": "10-Crop Identification + Shared Health Classifier",
        "version": (
            f"crop-{crop_status['version']}; health-{health_status['version']}"
            if available
            else None
        ),
        "message": message,
    }


def _filters(
    crop: str | None,
    disease: str | None,
    search: str | None,
    from_date: date | None,
    to_date: date | None,
) -> None:
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=422,
            detail="from_date must not be after to_date.",
        )

    if any(
        value is not None and len(value) > 100
        for value in (crop, disease, search)
    ):
        raise HTTPException(
            status_code=422,
            detail="Filter values must be 100 characters or fewer.",
        )

    if crop is not None and crop.casefold() not in {
        name.casefold() for name in SUPPORTED_CROPS
    }:
        raise HTTPException(
            status_code=422,
            detail="Unsupported crop.",
        )


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

    return store.list(
        page,
        page_size,
        crop,
        disease,
        search,
        from_date,
        to_date,
    )


@app.get("/api/recommendations", response_model=RecommendationPage)
def list_recommendations(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 100,
) -> dict:
    return store.list_recommendations(page, page_size)


@app.get("/api/detections/{detection_id}", response_model=Detection)
def get_detection(detection_id: str) -> dict:
    detection = store.get(detection_id)

    if detection is None:
        raise HTTPException(
            status_code=404,
            detail="Detection record not found.",
        )

    return detection


@app.post(
    "/api/detections/{detection_id}/recommendation-review",
    response_model=Detection,
)
def mark_recommendation_reviewed(detection_id: str) -> dict:
    detection = store.get(detection_id)
    if detection is None:
        raise HTTPException(
            status_code=404,
            detail="Detection record not found.",
        )
    if detection["source"] not in {"analysis", "live_monitoring"} or not store.has_saved_image(
        Path(detection["image_url"]).name
    ):
        raise HTTPException(
            status_code=422,
            detail="Only verified user detections with a saved image can be reviewed.",
        )
    if detection["health_status"] != "Unhealthy":
        raise HTTPException(
            status_code=422,
            detail="Only unhealthy detections have treatment recommendations.",
        )

    updated = store.mark_recommendation_reviewed(detection_id)
    if updated is None:
        raise HTTPException(
            status_code=404,
            detail="Detection record not found.",
        )
    return updated


async def _run_gemini_analysis(detection_id: str) -> dict:
    detection = store.get(detection_id)
    if detection is None:
        raise HTTPException(status_code=404, detail="Detection record not found.")
    if detection["health_status"] != "Unhealthy":
        raise HTTPException(
            status_code=422,
            detail="Gemini analysis is available only for unhealthy detections.",
        )
    if detection["source"] not in {"analysis", "live_monitoring"}:
        raise HTTPException(
            status_code=422,
            detail="Gemini analysis requires a verified user detection.",
        )
    filename = Path(detection["image_url"]).name
    if not store.has_saved_image(filename):
        raise HTTPException(
            status_code=422,
            detail="The saved detection image is unavailable for analysis.",
        )
    if detection["gemini_status"] == "completed":
        return detection
    if detection["gemini_status"] == "running":
        raise HTTPException(
            status_code=409,
            detail="Gemini analysis is already running for this detection.",
        )
    if not store.claim_gemini_analysis(detection_id):
        latest = store.get(detection_id)
        if latest and latest["gemini_status"] == "completed":
            return latest
        if latest and latest["gemini_status"] == "running":
            raise HTTPException(
                status_code=409,
                detail="Gemini analysis is already running for this detection.",
            )
        raise HTTPException(
            status_code=409,
            detail="Gemini analysis could not be started. Refresh and retry.",
        )

    image_path = settings.uploads_path / filename
    mime_type = "image/jpeg" if image_path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
    try:
        analysis = await analyze_leaf_image(
            image_path.read_bytes(),
            detection["crop_name"],
            mime_type,
            settings.gemini_api_key,
            settings.gemini_model,
        )
    except GeminiAnalysisError as exc:
        logger.warning(
            "Gemini analysis failed detection=%s status=%s",
            detection_id,
            exc.status,
        )
        updated = store.save_gemini_analysis(
            detection_id,
            exc.status,
            error=str(exc),
        )
    except Exception:
        logger.exception("Unexpected Gemini analysis failure detection=%s", detection_id)
        updated = store.save_gemini_analysis(
            detection_id,
            "failed",
            error="Gemini analysis failed unexpectedly. You can retry.",
        )
    else:
        updated = store.save_gemini_analysis(
            detection_id,
            "completed",
            analysis=analysis,
        )
    if updated is None:
        raise HTTPException(
            status_code=500,
            detail="Gemini analysis could not be saved.",
        )
    return updated


@app.post(
    "/api/detections/{detection_id}/gemini-analysis/retry",
    response_model=Detection,
)
async def retry_gemini_analysis(detection_id: str) -> dict:
    return await _run_gemini_analysis(detection_id)


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

    return store.list(
        page,
        page_size,
        crop,
        disease,
        None,
        from_date,
        to_date,
        locations_only=True,
    )


@app.get("/api/stats", response_model=StatsResponse)
def stats() -> dict:
    return store.stats()


@app.post("/api/crop-predict")
async def predict_crop(file: Annotated[UploadFile, File()]):
    image_bytes = await file.read(settings.max_upload_bytes + 1)

    if len(image_bytes) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail="Image exceeds the upload size limit.",
        )

    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image_format = image.format
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise HTTPException(
            status_code=415,
            detail="Upload a valid JPG or PNG image.",
        ) from exc

    if image_format not in {"JPEG", "PNG"}:
        raise HTTPException(
            status_code=415,
            detail="Only JPG, JPEG, and PNG images are supported.",
        )

    if not crop_model.available:
        raise HTTPException(
            status_code=503,
            detail=crop_model.status()["message"],
        )

    try:
        return crop_model.predict(image_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Crop prediction failed.")
        raise HTTPException(
            status_code=500,
            detail="Crop prediction failed.",
        ) from exc


@app.post("/api/predict", response_model=Detection, status_code=201)
async def predict(
    file: Annotated[UploadFile, File()],
    source: Annotated[Literal["analysis", "live_monitoring"], Form()] = "analysis",
    crop_name: Annotated[str | None, Form()] = None,
    latitude: Annotated[float | None, Form(ge=-90, le=90)] = None,
    longitude: Annotated[float | None, Form(ge=-180, le=180)] = None,
    gps_fix_valid: bool | None = Form(default=None),
    gps_timestamp: datetime | None = Form(default=None),
    captured_at: datetime | None = Form(default=None),
) -> dict:
    if crop_name is not None and crop_name.casefold() not in {
        name.casefold() for name in SUPPORTED_CROPS
    }:
        raise HTTPException(
            status_code=422,
            detail="Unsupported crop.",
        )

    if (latitude is None) != (longitude is None):
        raise HTTPException(
            status_code=422,
            detail="Latitude and longitude must be supplied together.",
        )

    if latitude is None:
        gps_fix_valid = None
        gps_timestamp = None
        captured_at = None
    elif any(
        value is not None
        for value in (gps_fix_valid, gps_timestamp, captured_at)
    ):
        if (
            gps_fix_valid is not True
            or gps_timestamp is None
            or captured_at is None
        ):
            raise HTTPException(
                status_code=422,
                detail="GPS coordinates require a valid fix and both GPS and image capture timestamps.",
            )

        if gps_timestamp.tzinfo is None or captured_at.tzinfo is None:
            raise HTTPException(
                status_code=422,
                detail="GPS and capture timestamps must include a timezone.",
            )

        if (
            abs((gps_timestamp - captured_at).total_seconds())
            > settings.gps_max_skew_seconds
        ):
            raise HTTPException(
                status_code=422,
                detail=f"GPS fix and image capture must be within {settings.gps_max_skew_seconds} seconds.",
            )

    image_bytes = await file.read(settings.max_upload_bytes + 1)

    if len(image_bytes) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail="Image exceeds the upload size limit.",
        )

    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image_format = image.format
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise HTTPException(
            status_code=415,
            detail="Upload a valid JPG or PNG image.",
        ) from exc

    if image_format not in {"JPEG", "PNG"}:
        raise HTTPException(
            status_code=415,
            detail="Only JPG, JPEG, and PNG images are supported.",
        )

    if not crop_model.available or not health_model.available:
        raise HTTPException(
            status_code=503,
            detail=_analysis_model_status()["message"],
        )

    try:
        crop_result = crop_model.predict(image_bytes)
        detected_crop = crop_result["crop_name"]
        if crop_name is not None and detected_crop.casefold() != crop_name.casefold():
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Selected crop {crop_name} does not match the detected "
                    f"crop {detected_crop}."
                ),
            )
        result = health_model.predict(image_bytes, detected_crop)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Crop and health inference failed.")
        raise HTTPException(
            status_code=500,
            detail="Crop and health inference failed.",
        ) from exc

    extension = ".jpg" if image_format == "JPEG" else ".png"
    filename = f"{uuid.uuid4().hex}{extension}"
    image_path = settings.uploads_path / filename

    try:
        image_path.write_bytes(image_bytes)

        record = store.create({
            "id": str(uuid.uuid4()),
            "filename": filename,
            "crop_name": detected_crop,
            "crop_confidence": crop_result["prediction_score"],
            "health_status": result["health_status"],
            "health_confidence": result["health_confidence"],
            "health_probabilities": result["health_probabilities"],
            "message": result["message"],
            "source": source,
            "disease_name": result["health_status"],
            "classification": (
                "healthy"
                if result["health_status"] == "Healthy"
                else "diseased"
            ),
            "prediction_score": result["health_confidence"],
            "latitude": latitude,
            "longitude": longitude,
            "gps_fix_valid": gps_fix_valid if latitude is not None else None,
            "gps_timestamp": (
                gps_timestamp.astimezone(timezone.utc).isoformat()
                if gps_timestamp else None
            ),
            "captured_at": (
                captured_at.astimezone(timezone.utc).isoformat()
                if captured_at else None
            ),
            "model_name": (
                "10-Crop MobileNetV2 Lite + Shared Health LiteRT"
            ),
            "model_version": (
                f"crop-{crop_model.version}; health-{health_model.version}"
            ),
            "top_predictions": [
                {"label": name, "score": confidence}
                for name, confidence in result["health_probabilities"].items()
            ],
        })

    except (OSError, sqlite3.Error):
        image_path.unlink(missing_ok=True)
        logger.exception("Could not persist a crop health inference result.")
        raise HTTPException(
            status_code=500,
            detail="The inference result could not be saved.",
        ) from None

    logger.info(
        "crop_health_detection_saved crop=%s id=%s classification=%s",
        record["crop_name"],
        record["id"],
        record["classification"],
    )

    if record["health_status"] == "Unhealthy":
        record = await _run_gemini_analysis(record["id"])

    return record


@app.get("/api/images/{filename}")
def get_image(filename: str):
    if not re.fullmatch(r"[a-f0-9]{32}\.(?:jpg|png)", filename):
        raise HTTPException(status_code=404, detail="Image not found.")

    image_path = settings.uploads_path / filename

    if (
        not image_path.is_file()
        or image_path.parent.resolve() != settings.uploads_path.resolve()
    ):
        raise HTTPException(status_code=404, detail="Image not found.")

    media_type = (
        "image/jpeg" if image_path.suffix == ".jpg" else "image/png"
    )

    return FileResponse(image_path, media_type=media_type)
