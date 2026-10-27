from io import BytesIO
from types import SimpleNamespace

import pytest
import torch
from PIL import Image

from backend.app.model_adapter import DiseaseModel


class FakeProcessor:
    def __call__(self, *, images, return_tensors):
        return {}


class FakeModel:
    def __call__(self, **inputs):
        return SimpleNamespace(logits=torch.tensor([[1.0]]))


@pytest.mark.parametrize(
    ("label", "crop_name", "disease_name", "classification"),
    [
        ("Tomato___healthy", "Tomato", "Healthy Tomato", "healthy"),
        ("Tomato___Early_blight", "Tomato", "Early blight", "diseased"),
        ("Pepper,_bell___Bacterial_spot", "Bell Pepper", "Bacterial spot", "diseased"),
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
