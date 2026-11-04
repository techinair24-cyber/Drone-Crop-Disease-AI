
import sqlite3
from dataclasses import replace
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.app import main
from backend.app.crop_adapter import SUPPORTED_CROPS
from backend.app.storage import DetectionStore


def make_image(image_format="PNG", color="green"):
    image = BytesIO()
    Image.new("RGB", (32, 32), color).save(image, format=image_format)
    return image.getvalue()


class ReadyCropModel:
    available = True

    def __init__(self, crop_name="Hibiscus"):
        self.crop_name = crop_name
        self.version = "test"

    def load(self):
        pass

    def status(self):
        return {
            "available": True,
            "status": "available",
            "name": "Crop Test Model",
            "version": "test",
            "message": "ready",
        }

    def predict(self, image_bytes):
        assert image_bytes
        return {
            "crop_name": self.crop_name,
            "prediction_score": 0.97,
        }


class ReadyHealthModel:
    available = True
    version = "test"
    supported_crops = SUPPORTED_CROPS

    def load(self):
        pass

    def status(self):
        return {
            "available": True,
            "status": "available",
            "name": "Shared Health Test Model",
            "version": "test",
            "message": "ready",
        }

    def predict(self, image_bytes, crop_name):
        assert image_bytes
        assert crop_name in SUPPORTED_CROPS
        return {
            "health_status": "Unhealthy",
            "health_confidence": 0.84,
            "health_probabilities": {"Healthy": 0.16, "Unhealthy": 0.84},
            "message": f"{crop_name} classified as Unhealthy.",
        }


class UnavailableModel:
    available = False

    def load(self):
        pass

    def status(self):
        return {
            "available": False,
            "status": "not_configured",
            "name": "Test Model",
            "version": None,
            "message": "Test model is not configured.",
        }


def install_ready_models(monkeypatch, crop_name="Hibiscus"):
    monkeypatch.setattr(main, "crop_model", ReadyCropModel(crop_name))
    monkeypatch.setattr(main, "health_model", ReadyHealthModel())


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_settings = replace(
        main.settings,
        database_path=tmp_path / "test.sqlite3",
        uploads_path=tmp_path / "uploads",
    )

    monkeypatch.setattr(main, "settings", test_settings)
    monkeypatch.setattr(
        main,
        "store",
        DetectionStore(test_settings.database_path, test_settings.uploads_path),
    )
    monkeypatch.setattr(main, "crop_model", UnavailableModel())
    monkeypatch.setattr(main, "health_model", UnavailableModel())

    with TestClient(main.app) as test_client:
        yield test_client


def test_health_reports_backend_and_missing_model(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["backend"] == "available"
    assert body["model"]["available"] is False
    assert body["model"]["status"] == "not_configured"


def test_status_never_fabricates_hardware_connections(client):
    response = client.get("/api/status")
    assert response.status_code == 200
    body = response.json()
    assert body["camera"]["available"] is False
    assert body["gps"]["available"] is False
    assert body["telemetry"]["available"] is False


def test_empty_history_and_stats(client):
    assert client.get("/api/detections").json() == {
        "items": [],
        "page": 1,
        "page_size": 20,
        "total": 0,
        "pages": 0,
    }

    stats = client.get("/api/stats").json()
    assert stats["total_images"] == 0
    assert stats["diseased_images"] == 0
    assert len(stats["activity"]) == 14


def test_existing_history_schema_migrates_without_losing_records(tmp_path):
    database_path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE detections (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                crop_name TEXT,
                disease_name TEXT NOT NULL,
                classification TEXT NOT NULL,
                prediction_score REAL,
                created_at TEXT NOT NULL,
                latitude REAL,
                longitude REAL,
                model_name TEXT,
                model_version TEXT,
                top_predictions TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO detections (
                id, filename, crop_name, disease_name, classification,
                prediction_score, created_at, latitude, longitude,
                model_name, model_version, top_predictions
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-record",
                "legacy.png",
                "Hibiscus",
                "Healthy",
                "healthy",
                0.91,
                "2026-01-01T10:00:00+00:00",
                12.4,
                76.2,
                "Hibiscus Prototype",
                "prototype",
                "[]",
            ),
        )

    store = DetectionStore(database_path, tmp_path / "uploads")
    store.initialize()
    result = store.get("legacy-record")

    assert result["crop_name"] == "Hibiscus"
    assert result["disease_name"] == "Healthy"
    assert result["classification"] == "healthy"
    assert result["latitude"] == 12.4
    assert result["health_status"] is None
    assert result["health_probabilities"] is None


def test_missing_detection_returns_404(client):
    response = client.get("/api/detections/not-a-record")
    assert response.status_code == 404
    assert response.json()["detail"] == "Detection record not found."


def test_latest_uploaded_image_is_retrievable(client, monkeypatch):
    install_ready_models(monkeypatch)

    uploaded_images = []

    for color in ("green", "red"):
        image_bytes = make_image("JPEG", color)
        uploaded_images.append(image_bytes)

        response = client.post(
            "/api/predict",
            files={"file": (f"{color}.jpg", image_bytes, "image/jpeg")},
        )
        assert response.status_code == 201

    latest = client.get(
        "/api/detections",
        params={"page": 1, "page_size": 1},
    ).json()["items"][0]

    assert latest["image_url"]

    image_response = client.get(latest["image_url"])
    assert image_response.status_code == 200
    assert image_response.content == uploaded_images[-1]


def test_missing_uploaded_image_returns_404(client):
    response = client.get(
        "/api/images/00000000000000000000000000000000.jpg"
    )
    assert response.status_code == 404


def test_predict_refuses_when_model_is_not_configured(client):
    response = client.post(
        "/api/predict",
        files={
            "file": (
                "leaf.png",
                make_image(),
                "image/png",
            )
        },
    )

    assert response.status_code == 503
    assert "model is not configured" in response.json()["detail"]


def test_predict_refuses_when_either_model_is_unavailable(client, monkeypatch):
    monkeypatch.setattr(main, "crop_model", ReadyCropModel())
    monkeypatch.setattr(main, "health_model", UnavailableModel())

    response = client.post(
        "/api/predict",
        files={"file": ("leaf.png", make_image(), "image/png")},
    )

    assert response.status_code == 503
    assert "Test model is not configured." in response.json()["detail"]


def test_predict_requires_gps_coordinates_as_a_pair(client):
    response = client.post(
        "/api/predict",
        files={
            "file": (
                "leaf.png",
                make_image(),
                "image/png",
            )
        },
        data={"latitude": "12.4"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Latitude and longitude must be supplied together."
    )


def test_invalid_image_is_rejected_before_model_check(client):
    response = client.post(
        "/api/predict",
        files={"file": ("leaf.png", b"not an image", "image/png")},
    )

    assert response.status_code == 415
    assert response.json()["detail"] == "Upload a valid JPG or PNG image."


def test_prediction_is_persisted_and_returned_with_location(
    client, monkeypatch
):
    install_ready_models(monkeypatch)

    response = client.post(
        "/api/predict",
        files={
            "file": (
                "leaf.png",
                make_image(),
                "image/png",
            )
        },
        data={
            "latitude": "12.4",
            "longitude": "76.2",
            "gps_fix_valid": "true",
            "gps_timestamp": "2026-01-01T10:00:00+00:00",
            "captured_at": "2026-01-01T10:00:20+00:00",
        },
    )

    assert response.status_code == 201

    detection = response.json()
    assert detection["crop_name"] == "Hibiscus"
    assert detection["crop_confidence"] == 0.97
    assert detection["health_status"] == "Unhealthy"
    assert detection["health_confidence"] == 0.84
    assert detection["health_probabilities"] == {
        "Healthy": 0.16,
        "Unhealthy": 0.84,
    }
    assert detection["classification"] == "diseased"
    assert detection["latitude"] == 12.4
    assert detection["gps_fix_valid"] is True

    assert (
        client.get(f"/api/detections/{detection['id']}").json()["id"]
        == detection["id"]
    )
    saved_detection = client.get(
        f"/api/detections/{detection['id']}"
    ).json()
    assert saved_detection["health_probabilities"] == {
        "Healthy": 0.16,
        "Unhealthy": 0.84,
    }

    locations = client.get("/api/locations").json()
    assert locations["total"] == 1
    assert locations["items"][0]["id"] == detection["id"]
    assert locations["items"][0]["latitude"] == 12.4
    assert locations["items"][0]["longitude"] == 76.2

    assert client.get("/api/stats").json()["diseased_images"] == 1

    image_response = client.get(detection["image_url"])
    assert image_response.status_code == 200
    assert image_response.headers["content-type"] == "image/png"


def test_prediction_saves_coordinate_pair_without_gps_metadata(
    client, monkeypatch
):
    install_ready_models(monkeypatch)

    response = client.post(
        "/api/predict",
        files={
            "file": (
                "leaf.png",
                make_image(),
                "image/png",
            )
        },
        data={
            "latitude": "12.4",
            "longitude": "76.2",
        },
    )

    assert response.status_code == 201
    detection = response.json()
    assert detection["latitude"] == 12.4
    assert detection["longitude"] == 76.2
    assert detection["gps_fix_valid"] is None

    locations = client.get("/api/locations").json()
    assert locations["total"] == 1
    assert locations["items"][0]["id"] == detection["id"]
    assert locations["items"][0]["latitude"] == 12.4
    assert locations["items"][0]["longitude"] == 76.2


def test_predict_rejects_out_of_range_coordinates(client, monkeypatch):
    install_ready_models(monkeypatch)

    response = client.post(
        "/api/predict",
        files={
            "file": (
                "leaf.png",
                make_image(),
                "image/png",
            )
        },
        data={
            "latitude": "91",
            "longitude": "76.2",
        },
    )

    assert response.status_code == 422


def test_predict_classifies_all_supported_crops_and_lists_history(
    client, monkeypatch
):
    detections = []
    for crop in SUPPORTED_CROPS:
        install_ready_models(monkeypatch, crop_name=crop)
        response = client.post(
            "/api/predict",
            files={"file": (f"{crop}.png", make_image(), "image/png")},
            data={"crop_name": crop},
        )

        assert response.status_code == 201
        detection = response.json()
        assert detection["crop_name"] == crop
        assert detection["health_status"] == "Unhealthy"
        assert detection["crop_confidence"] == 0.97
        assert detection["health_confidence"] == 0.84
        assert detection["health_probabilities"] == {
            "Healthy": 0.16,
            "Unhealthy": 0.84,
        }
        detections.append(detection)

    history = client.get("/api/detections").json()
    assert history["total"] == len(SUPPORTED_CROPS)
    assert {row["crop_name"] for row in history["items"]} == set(SUPPORTED_CROPS)

    hibiscus_history = client.get(
        "/api/detections", params={"crop": "Hibiscus"}
    ).json()
    assert hibiscus_history["total"] == 1
    assert hibiscus_history["items"][0]["crop_name"] == "Hibiscus"
    assert client.get("/api/stats").json()["total_images"] == len(SUPPORTED_CROPS)


def test_predict_rejects_unsupported_crop_selection(client):
    response = client.post(
        "/api/predict",
        files={
            "file": (
                "leaf.png",
                make_image(),
                "image/png",
            )
        },
        data={"crop_name": "Unknown Crop"},
    )

    assert response.status_code == 422
    assert "Unsupported crop" in response.json()["detail"]


def test_predict_rejects_manual_crop_that_conflicts_with_model(
    client, monkeypatch
):
    install_ready_models(monkeypatch, crop_name="Apple")

    response = client.post(
        "/api/predict",
        files={"file": ("leaf.png", make_image(), "image/png")},
        data={"crop_name": "Tomato"},
    )

    assert response.status_code == 422
    assert "does not match the detected crop Apple" in response.json()["detail"]


def test_stale_gps_fix_is_not_associated_with_image(client):
    response = client.post(
        "/api/predict",
        files={
            "file": (
                "leaf.png",
                make_image(),
                "image/png",
            )
        },
        data={
            "latitude": "12.4",
            "longitude": "76.2",
            "gps_fix_valid": "true",
            "gps_timestamp": "2026-01-01T10:00:00+00:00",
            "captured_at": "2026-01-01T10:01:00+00:00",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "GPS fix and image capture must be within 30 seconds."
    )
