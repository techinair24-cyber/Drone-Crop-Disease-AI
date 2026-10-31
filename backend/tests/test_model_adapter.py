from io import BytesIO
from types import SimpleNamespace

import pytest
import torch
from PIL import Image

from backend.app.model_adapter import SUPPORTED_CROPS, DiseaseModel


class FakeProcessor:
    def __call__(self, *, images, return_tensors):
        return {}


class FakeModel:
    def __call__(self, **inputs):
        return SimpleNamespace(logits=torch.tensor([self.logits]))

    def __init__(self, logits=None):
        self.logits = logits or [1.0]


@pytest.mark.parametrize(
    ("label", "crop_name", "disease_name", "classification"),
    [
        ("Apple___Apple_scab", "Apple", "Apple scab", "diseased"),
        ("Cherry_(including_sour)___Powdery_mildew", "Cherry", "Powdery mildew", "diseased"),
        ("Corn_(maize)___Common_rust_", "Corn", "Common rust", "diseased"),
        ("Grape___Black_rot", "Grape", "Black rot", "diseased"),
        ("Peach___Bacterial_spot", "Peach", "Bacterial spot", "diseased"),
        ("Pepper,_bell___Bacterial_spot", "Bell Pepper", "Bacterial spot", "diseased"),
        ("Potato___Early_blight", "Potato", "Early blight", "diseased"),
        ("Strawberry___Leaf_scorch", "Strawberry", "Leaf scorch", "diseased"),
        ("Tomato___Early_blight", "Tomato", "Early blight", "diseased"),
        ("Tomato___healthy", "Tomato", "Healthy Tomato", "healthy"),
    ],
)
def test_infer_decodes_model_labels(label, crop_name, disease_name, classification):
    model = DiseaseModel(None, 0.55, "Test model")
    model.model = FakeModel()
    model.processor = FakeProcessor()
    model.labels = {0: label}
    image = BytesIO()
    Image.new("RGB", (8, 8), "green").save(image, format="PNG")

    result = model.infer(image.getvalue())

    assert result.crop_name == crop_name
    assert result.disease_name == disease_name
    assert result.classification == classification


def test_supported_crop_allowlist_is_limited_to_crops_with_healthy_and_diseased_labels():
    assert SUPPORTED_CROPS == (
        "Apple",
        "Bell Pepper",
        "Cherry",
        "Corn",
        "Grape",
        "Peach",
        "Potato",
        "Strawberry",
        "Tomato",
    )
    assert len(SUPPORTED_CROPS) <= 10


@pytest.mark.parametrize(
    "label",
    [
        "Blueberry___healthy",
        "Orange___Haunglongbing_(Citrus_greening)",
        "Raspberry___healthy",
        "Soybean___healthy",
        "Squash___Powdery_mildew",
    ],
)
def test_infer_rejects_unsupported_crop_label(label):
    model = DiseaseModel(None, 0.55, "Test model")
    model.model = FakeModel()
    model.processor = FakeProcessor()
    model.labels = {0: label}
    image = BytesIO()
    Image.new("RGB", (8, 8), "green").save(image, format="PNG")

    result = model.infer(image.getvalue())

    assert result.crop_name is None
    assert result.disease_name == "Inconclusive"
    assert result.classification == "inconclusive"
    assert result.top_predictions == []


def test_infer_rejects_prediction_that_conflicts_with_selected_crop():
    model = DiseaseModel(None, 0.55, "Test model")
    model.model = FakeModel()
    model.processor = FakeProcessor()
    model.labels = {0: "Tomato___Early_blight"}
    image = BytesIO()
    Image.new("RGB", (8, 8), "green").save(image, format="PNG")

    result = model.infer(image.getvalue(), expected_crop="Potato")

    assert result.crop_name is None
    assert result.disease_name == "Inconclusive"
    assert result.classification == "inconclusive"


def test_low_confidence_non_leaf_image_is_inconclusive():
    model = DiseaseModel(None, 0.55, "Test model")
    model.model = FakeModel([0.0] * 38)
    model.processor = FakeProcessor()
    model.labels = {index: f"Tomato___class_{index}" for index in range(38)}
    image = BytesIO()
    Image.new("RGB", (8, 8), "white").save(image, format="PNG")

    result = model.infer(image.getvalue())

    assert result.crop_name is None
    assert result.disease_name == "Inconclusive"
    assert result.classification == "inconclusive"
