
from dataclasses import replace
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.app import main
from backend.app.storage import DetectionStore


def make_image(image_format="PNG", color="green"):
    image = BytesIO()
    Image.new("RGB", (32, 32), color).save(image, format=image_format)
    return image.getvalue()


class ReadyModel:
    available = True

    def status(self):
        return {
            "available": True,
            "status": "available",
            "name": "Hibiscus Test Model",
            "version": "test",
            "message": "ready",
        }

    def predict(self, image_bytes):
        assert image_bytes
        return {
            "crop_name": "Hibiscus",
            "disease_name": "Unhealthy",
            "classification": "diseased",
            "prediction_score": 0.84,
            "top_predictions": [
                {"label": "Unhealthy", "score": 0.84},
                {"label": "Healthy", "score": 0.16},
            ],
            "model_name": "Hibiscus Test Model",
            "model_version": "test",
        }


class UnavailableModel:
    available = False

    def load(self):
        pass

    def status(self):
        return {
            "available": False,
            "status": "not_configured",
            "name": "Hibiscus Test Model",
            "version": None,
            "message": "Hibiscus model is not configured.",
        }


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
    monkeypatch.setattr(main, "model", UnavailableModel())

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


def test_missing_detection_returns_404(client):
    response = client.get("/api/detections/not-a-record")
    assert response.status_code == 404
    assert response.json()["detail"] == "Detection record not found."


def test_latest_uploaded_image_is_retrievable(client, monkeypatch):
    monkeypatch.setattr(main, "model", ReadyModel())

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
    assert response.json()["detail"] == "Hibiscus model is not configured."


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
    monkeypatch.setattr(main, "model", ReadyModel())

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
    assert detection["classification"] == "diseased"
    assert detection["latitude"] == 12.4
    assert detection["gps_fix_valid"] is True

    assert (
        client.get(f"/api/detections/{detection['id']}").json()["id"]
        == detection["id"]
    )

    locations = client.get("/api/locations").json()
    assert locations["total"] == 1
    assert locations["items"][0]["id"] == detection["id"]

    assert client.get("/api/stats").json()["diseased_images"] == 1

    image_response = client.get(detection["image_url"])
    assert image_response.status_code == 200
    assert image_response.headers["content-type"] == "image/png"


def test_predict_accepts_hibiscus_selection(client, monkeypatch):
    monkeypatch.setattr(main, "model", ReadyModel())

    response = client.post(
        "/api/predict",
        files={
            "file": (
                "hibiscus.png",
                make_image(),
                "image/png",
            )
        },
        data={"crop_name": "Hibiscus"},
    )

    assert response.status_code == 201
    assert response.json()["crop_name"] == "Hibiscus"


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
        data={"crop_name": "Tomato"},
    )

    assert response.status_code == 422
    assert "Unsupported crop" in response.json()["detail"]


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
