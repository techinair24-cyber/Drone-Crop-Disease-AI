import logging
import os
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Inference:
    crop_name: str | None
    disease_name: str
    classification: str
    prediction_score: float | None
    top_predictions: list[dict[str, Any]]
    model_name: str
    model_version: str | None


class ModelUnavailableError(RuntimeError):
    pass


class InvalidImageError(ValueError):
    pass


class DiseaseModel:
    def __init__(self, model_path: str | None, score_threshold: float, model_name: str):
        if not 0 <= score_threshold <= 1:
            raise ValueError("MODEL_SCORE_THRESHOLD must be between 0 and 1.")
        self.model_path = model_path
        self.score_threshold = score_threshold
        self.model_name = model_name
        self.model: Any = None
        self.processor: Any = None
        self.labels: dict[int, str] = {}
        self.version: str | None = None
        self.load_error: str | None = None

    @property
    def available(self) -> bool:
        return self.model is not None and self.processor is not None

    def load(self) -> None:
        if not self.model_path:
            return
        path = Path(self.model_path)
        if not path.exists():
            self.load_error = "Configured model directory does not exist."
            return
        try:
            from transformers import AutoImageProcessor, AutoModelForImageClassification

            processor = AutoImageProcessor.from_pretrained(str(path), local_files_only=True)
            model = AutoModelForImageClassification.from_pretrained(str(path), local_files_only=True)
            raw_labels = model.config.id2label
            labels = {int(index): str(label) for index, label in raw_labels.items()}
            if not labels or any(
                label.casefold().startswith(("label_", "class ")) or label.casefold().startswith("class_")
                for label in labels.values()
            ):
                raise ValueError("The model config must provide verified class names.")
            model.eval()
            self.processor = processor
            self.model = model
            self.labels = labels
            self.version = os.getenv("MODEL_VERSION") or getattr(model.config, "_commit_hash", None) or "local"
            logger.info("Loaded local image classifier with %d labels.", len(self.labels))
        except (ImportError, OSError, ValueError, RuntimeError, KeyError):
            self.load_error = "The configured model could not be loaded. Check model files and inference dependencies."
            logger.exception("Configured image classifier failed to load.")

    def status(self) -> dict[str, Any]:
        if self.available:
            return {
                "available": True, "status": "available", "name": self.model_name,
                "version": self.version, "message": "Model loaded and ready.",
            }
        if self.load_error:
            return {
                "available": False, "status": "error", "name": self.model_name,
                "version": None, "message": self.load_error,
            }
        return {
            "available": False, "status": "not_configured", "name": None,
            "version": None, "message": "No model is configured.",
        }

    def infer(self, image_bytes: bytes) -> Inference:
        if not self.available:
            raise ModelUnavailableError("Model inference is unavailable. Configure a valid local model first.")
        try:
            image = Image.open(BytesIO(image_bytes)).convert("RGB")
            inputs = self.processor(images=image, return_tensors="pt")
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise InvalidImageError("The uploaded image could not be processed.") from exc

        import torch

        with torch.inference_mode():
            logits = self.model(**inputs).logits[0]
            probabilities = torch.softmax(logits, dim=-1)
            scores, indices = torch.topk(probabilities, k=min(3, probabilities.shape[-1]))
        top_predictions = [
            {"label": self.labels.get(int(index), f"Class {int(index)}"), "score": float(value)}
            for value, index in zip(scores.tolist(), indices.tolist(), strict=True)
        ]
        predicted_label = top_predictions[0]["label"]
        top_score = top_predictions[0]["score"]
        crop = _crop_from_label(predicted_label)
        if top_score < self.score_threshold or crop is None:
            disease = "Inconclusive"
            classification = "inconclusive"
            crop = None
        else:
            disease = _disease_from_label(predicted_label)
            classification = "healthy" if predicted_label.lower().startswith("healthy ") else "diseased"
        return Inference(
            crop_name=crop,
            disease_name=disease,
            classification=classification,
            prediction_score=top_score,
            top_predictions=top_predictions,
            model_name=self.model_name,
            model_version=self.version,
        )


def _crop_from_label(label: str) -> str | None:
    if label.casefold().startswith("healthy "):
        crop = re.sub(r"\s+plant$", "", label[8:], flags=re.IGNORECASE).strip()
        return crop or None
    if " with " in label.casefold():
        return label[:label.casefold().index(" with ")].strip() or None
    candidates = (
        "Apple", "Blueberry", "Cherry", "Corn", "Grape", "Orange", "Peach",
        "Bell Pepper", "Potato", "Raspberry", "Soybean", "Squash", "Strawberry", "Tomato",
    )
    lowered = label.casefold()
    for candidate in candidates:
        if candidate.casefold() in lowered:
            return candidate
    return None


def _disease_from_label(label: str) -> str:
    if label.lower().startswith("healthy "):
        crop = _crop_from_label(label)
        return f"Healthy {crop}" if crop else label
    if " with " in label:
        return label.split(" with ", 1)[1]
    return label
