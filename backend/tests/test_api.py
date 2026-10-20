from dataclasses import replace
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.app import main
from backend.app.model_adapter import DiseaseModel, Inference
from backend.app.storage import DetectionStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_settings = replace(main.settings, database_path=tmp_path / "test.sqlite3", uploads_path=tmp_path / "uploads")
    monkeypatch.setattr(main, "settings", test_settings)
    monkeypatch.setattr(main, "store", DetectionStore(test_settings.database_path, test_settings.uploads_path))
    monkeypatch.setattr(main, "model", DiseaseModel(None, 0.55, test_settings.model_name))
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
        "items": [], "page": 1, "page_size": 20, "total": 0, "pages": 0,
    }
    stats = client.get("/api/stats").json()
    assert stats["total_images"] == 0
    assert stats["diseased_images"] == 0
    assert len(stats["activity"]) == 14


def test_missing_detection_returns_404(client):
    response = client.get("/api/detections/not-a-record")
    assert response.status_code == 404
    assert response.json()["detail"] == "Detection record not found."


def test_predict_refuses_when_model_is_not_configured(client):
    image = BytesIO()
    Image.new("RGB", (32, 32), "green").save(image, format="PNG")
    response = client.post("/api/predict", files={"file": ("leaf.png", image.getvalue(), "image/png")})
    assert response.status_code == 503
    assert "No model is configured" in response.json()["detail"]


def test_predict_requires_gps_coordinates_as_a_pair(client):
    image = BytesIO()
    Image.new("RGB", (32, 32), "green").save(image, format="PNG")
    response = client.post(
        "/api/predict",
        files={"file": ("leaf.png", image.getvalue(), "image/png")},
        data={"latitude": "12.4"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Latitude and longitude must be supplied together."


def test_invalid_image_is_rejected_before_model_check(client):
    response = client.post(
        "/api/predict",
        files={"file": ("leaf.png", b"not an image", "image/png")},
    )
    assert response.status_code == 415
    assert response.json()["detail"] == "Upload a valid JPG or PNG image."


def test_prediction_is_persisted_and_returned_with_location(client, monkeypatch):
    class ReadyModel:
        available = True

        def status(self):
            return {"available": True, "status": "available", "name": "Test model", "version": "test", "message": "ready"}

        def infer(self, image_bytes):
            assert image_bytes
            return Inference(
                crop_name="Tomato",
                disease_name="Early Blight",
                classification="diseased",
                prediction_score=0.84,
                top_predictions=[{"label": "Tomato with Early Blight", "score": 0.84}],
                model_name="Test model",
                model_version="test",
            )

    monkeypatch.setattr(main, "model", ReadyModel())
    image = BytesIO()
    Image.new("RGB", (32, 32), "green").save(image, format="PNG")
    response = client.post(
        "/api/predict",
        files={"file": ("leaf.png", image.getvalue(), "image/png")},
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
    assert detection["crop_name"] == "Tomato"
    assert detection["classification"] == "diseased"
    assert detection["latitude"] == 12.4
    assert detection["gps_fix_valid"] is True
    assert client.get(f"/api/detections/{detection['id']}").json()["id"] == detection["id"]
    locations = client.get("/api/locations").json()
    assert locations["total"] == 1
    assert locations["items"][0]["id"] == detection["id"]
    assert client.get("/api/stats").json()["diseased_images"] == 1
    image_response = client.get(detection["image_url"])
    assert image_response.status_code == 200
    assert image_response.headers["content-type"] == "image/png"


def test_stale_gps_fix_is_not_associated_with_image(client):
    image = BytesIO()
    Image.new("RGB", (32, 32), "green").save(image, format="PNG")
    response = client.post(
        "/api/predict",
        files={"file": ("leaf.png", image.getvalue(), "image/png")},
        data={
            "latitude": "12.4",
            "longitude": "76.2",
            "gps_fix_valid": "true",
            "gps_timestamp": "2026-01-01T10:00:00+00:00",
            "captured_at": "2026-01-01T10:01:00+00:00",
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "GPS fix and image capture must be within 30 seconds."
