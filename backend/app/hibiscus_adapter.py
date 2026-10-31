
import json
import logging
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn
from PIL import Image, UnidentifiedImageError
from torchvision import models, transforms

logger = logging.getLogger(__name__)


class HibiscusModel:
    def __init__(self, model_path: Path):
        self.model_path = Path(model_path)
        self.info_path = self.model_path.with_name(
            "hibiscus_model_info.json"
        )
        self.model: Any = None
        self.classes: list[str] = []
        self.version = "prototype"
        self.load_error: str | None = None
        self.device = torch.device("cpu")

        self.transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(
                [0.485, 0.456, 0.406],
                [0.229, 0.224, 0.225]
            )
        ])

    @property
    def available(self) -> bool:
        return self.model is not None

    def load(self) -> None:
        if not self.model_path.is_file() or not self.info_path.is_file():
            self.load_error = "Hibiscus model files are missing."
            return

        try:
            info = json.loads(self.info_path.read_text(encoding="utf-8"))
            if info.get("plant") != "Hibiscus":
                raise ValueError("Model metadata is not for Hibiscus.")

            classes = info.get("classes")
            if classes != ["Healthy", "Unhealthy"]:
                raise ValueError("Unexpected Hibiscus class labels.")

            model = models.mobilenet_v2(weights=None)
            model.classifier[1] = nn.Linear(
                model.last_channel, len(classes)
            )

            state = torch.load(
                self.model_path,
                map_location=self.device,
                weights_only=True
            )
            model.load_state_dict(state)
            model.eval()

            self.classes = classes
            self.model = model
            logger.info("Hibiscus prototype model loaded.")

        except (OSError, ValueError, RuntimeError, KeyError) as exc:
            self.load_error = "Hibiscus model could not be loaded."
            logger.exception("Hibiscus model loading failed: %s", exc)

    def status(self) -> dict:
        if self.available:
            return {
                "available": True,
                "status": "available",
                "name": "Hibiscus MobileNetV2 Prototype",
                "version": self.version,
                "message": (
                    "Experimental Hibiscus model loaded. "
                    "Not validated for reliable diagnosis."
                )
            }

        return {
            "available": False,
            "status": "error" if self.load_error else "not_configured",
            "name": "Hibiscus MobileNetV2 Prototype",
            "version": None,
            "message": self.load_error or "Hibiscus model is not configured."
        }

    def predict(self, image_bytes: bytes) -> dict:
        if not self.available:
            raise RuntimeError("Hibiscus model is unavailable.")

        try:
            from io import BytesIO

            image = Image.open(BytesIO(image_bytes)).convert("RGB")
            tensor = self.transform(image).unsqueeze(0)

        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise ValueError("Invalid Hibiscus image.") from exc

        with torch.inference_mode():
            logits = self.model(tensor)
            probabilities = torch.softmax(logits, dim=1)[0]

        scores, indices = torch.sort(
            probabilities, descending=True
        )

        predicted_class = self.classes[indices[0].item()]
        confidence = float(scores[0].item())

        return {
            "crop_name": "Hibiscus",
            "disease_name": predicted_class,
            "classification": (
                "healthy" if predicted_class == "Healthy" else "diseased"
            ),
            "prediction_score": confidence,
            "top_predictions": [
                {
                    "label": self.classes[index.item()],
                    "score": float(score.item())
                }
                for score, index in zip(scores, indices)
            ],
            "model_name": "Hibiscus MobileNetV2 Prototype",
            "model_version": self.version
        }
