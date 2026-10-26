import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env", override=False)


def _cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def _storage_path(variable: str, default: Path) -> Path:
    configured = Path(os.getenv(variable, str(default)))
    return configured if configured.is_absolute() else BACKEND_DIR / configured


@dataclass(frozen=True)
class Settings:
    database_path: Path
    uploads_path: Path
    model_path: str | None
    model_threshold: float
    max_upload_bytes: int
    gps_max_skew_seconds: int
    cors_origins: list[str]
    model_name: str


def get_settings() -> Settings:
    return Settings(
        database_path=_storage_path("DATABASE_PATH", BACKEND_DIR / "data" / "detections.sqlite3"),
        uploads_path=_storage_path("UPLOADS_PATH", BACKEND_DIR / "uploads"),
        model_path=str(_storage_path("MODEL_PATH", BACKEND_DIR / "models" / "plantvillage-mobilenetv2")) if os.getenv("MODEL_PATH") else None,
        model_threshold=float(os.getenv("MODEL_SCORE_THRESHOLD", "0.55")),
        max_upload_bytes=int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))),
        gps_max_skew_seconds=int(os.getenv("GPS_MAX_SKEW_SECONDS", "30")),
        cors_origins=_cors_origins(),
        model_name=os.getenv("MODEL_NAME", "Local image classifier"),
    )
