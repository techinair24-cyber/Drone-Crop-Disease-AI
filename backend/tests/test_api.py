
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

    def __init__(self, health_status="Unhealthy"):
        self.health_status = health_status

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
        healthy_probability = 0.91 if self.health_status == "Healthy" else 0.16
        unhealthy_probability = 1 - healthy_probability
        return {
            "health_status": self.health_status,
            "health_confidence": max(healthy_probability, unhealthy_probability),
            "health_probabilities": {
                "Healthy": healthy_probability,
                "Unhealthy": unhealthy_probability,
            },
            "message": f"{crop_name} classified as {self.health_status}.",
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


def install_ready_models(
    monkeypatch, crop_name="Hibiscus", health_status="Unhealthy"
):
    monkeypatch.setattr(main, "crop_model", ReadyCropModel(crop_name))
    monkeypatch.setattr(main, "health_model", ReadyHealthModel(health_status))


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


def test_empty_recommendations_return_successful_empty_page(client):
    response = client.get("/api/recommendations")

    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "page": 1,
        "page_size": 100,
        "total": 0,
        "pages": 0,
        "summary": {
            "total_unhealthy": 0,
            "pending": 0,
            "reviewed": 0,
            "crop_counts": {},
        },
    }


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
    assert result["recommendation_reviewed"] is False
    assert result["source"] is None


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
        assert detection["recommendation_reviewed"] is False
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


def test_recommendations_only_include_real_sourced_unhealthy_images(
    client, monkeypatch
):
    install_ready_models(monkeypatch, crop_name="Apple")
    apple = client.post(
        "/api/predict",
        files={"file": ("apple.png", make_image(), "image/png")},
        data={"source": "analysis"},
    )
    assert apple.status_code == 201
    assert apple.json()["source"] == "analysis"

    install_ready_models(monkeypatch, crop_name="Chilli")
    chilli = client.post(
        "/api/predict",
        files={"file": ("chilli.png", make_image("PNG", "red"), "image/png")},
        data={"source": "live_monitoring"},
    )
    assert chilli.status_code == 201
    assert chilli.json()["source"] == "live_monitoring"

    install_ready_models(
        monkeypatch, crop_name="Tomato", health_status="Healthy"
    )
    healthy = client.post(
        "/api/predict",
        files={"file": ("tomato.png", make_image("PNG", "yellow"), "image/png")},
        data={"source": "analysis"},
    )
    assert healthy.status_code == 201

    # Legacy rows without provenance and records without a stored image remain
    # in history but must not be presented as user recommendations.
    main.settings.uploads_path.mkdir(parents=True, exist_ok=True)
    (main.settings.uploads_path / "legacy-unverified.png").write_bytes(
        make_image()
    )
    for detection_id, filename, source in (
        ("unverified-legacy", "legacy-unverified.png", None),
        ("missing-saved-image", "missing-image.png", "analysis"),
    ):
        main.store.create({
            "id": detection_id,
            "filename": filename,
            "crop_name": "Wheat",
            "crop_confidence": 0.9,
            "health_status": "Unhealthy",
            "health_confidence": 0.9,
            "health_probabilities": {"Healthy": 0.1, "Unhealthy": 0.9},
            "message": "test record",
            "source": source,
            "disease_name": "Unhealthy",
            "classification": "diseased",
            "prediction_score": 0.9,
            "latitude": None,
            "longitude": None,
            "gps_fix_valid": None,
            "gps_timestamp": None,
            "captured_at": None,
            "model_name": "test",
            "model_version": "test",
            "top_predictions": [],
        })

    recommendations = client.get("/api/recommendations").json()
    assert recommendations["total"] == 2
    assert recommendations["summary"] == {
        "total_unhealthy": 2,
        "pending": 2,
        "reviewed": 0,
        "crop_counts": {"Apple": 1, "Chilli": 1},
    }
    assert {item["source"] for item in recommendations["items"]} == {
        "analysis",
        "live_monitoring",
    }
    assert all(item["image_url"] and item["id"] for item in recommendations["items"])
    for item in recommendations["items"]:
        image_response = client.get(item["image_url"])
        assert image_response.status_code == 200

    reviewed = client.post(
        f"/api/detections/{apple.json()['id']}/recommendation-review"
    )
    assert reviewed.status_code == 200
    summary = client.get("/api/recommendations").json()["summary"]
    assert summary["pending"] == 1
    assert summary["reviewed"] == 1


def test_predict_rejects_unknown_detection_source(client, monkeypatch):
    install_ready_models(monkeypatch)
    response = client.post(
        "/api/predict",
        files={"file": ("leaf.png", make_image(), "image/png")},
        data={"source": "seed"},
    )
    assert response.status_code == 422


def test_unhealthy_recommendation_review_is_persisted(client, monkeypatch):
    install_ready_models(monkeypatch, crop_name="Apple")
    prediction = client.post(
        "/api/predict",
        files={"file": ("apple.png", make_image(), "image/png")},
    )
    assert prediction.status_code == 201
    detection = prediction.json()
    assert detection["recommendation_reviewed"] is False

    reviewed = client.post(
        f"/api/detections/{detection['id']}/recommendation-review"
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["recommendation_reviewed"] is True
    assert client.get(
        f"/api/detections/{detection['id']}"
    ).json()["recommendation_reviewed"] is True
    assert client.get("/api/detections").json()["items"][0][
        "recommendation_reviewed"
    ] is True


def test_healthy_detection_cannot_be_marked_as_treatment_reviewed(
    client, monkeypatch
):
    install_ready_models(
        monkeypatch, crop_name="Tomato", health_status="Healthy"
    )
    prediction = client.post(
        "/api/predict",
        files={"file": ("tomato.png", make_image(), "image/png")},
    )
    assert prediction.status_code == 201
    assert prediction.json()["recommendation_reviewed"] is False

    response = client.post(
        f"/api/detections/{prediction.json()['id']}/recommendation-review"
    )
    assert response.status_code == 422
    assert "Only unhealthy detections" in response.json()["detail"]


def test_unverified_legacy_unhealthy_hibiscus_cannot_be_reviewed(client):
    main.store.create({
        "id": "legacy-hibiscus",
        "filename": "legacy-hibiscus.jpg",
        "crop_name": "Hibiscus",
        "crop_confidence": None,
        "health_status": None,
        "health_confidence": None,
        "health_probabilities": None,
        "message": None,
        "disease_name": "Legacy result",
        "classification": "diseased",
        "prediction_score": 0.75,
        "latitude": None,
        "longitude": None,
        "gps_fix_valid": None,
        "gps_timestamp": None,
        "captured_at": None,
        "model_name": "Legacy Hibiscus model",
        "model_version": "legacy",
        "top_predictions": [],
    })

    response = client.post(
        "/api/detections/legacy-hibiscus/recommendation-review"
    )

    assert response.status_code == 422
    assert "verified user detections" in response.json()["detail"]


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
