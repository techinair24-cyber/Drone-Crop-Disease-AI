import json
import logging
from pathlib import Path
from typing import Any
from io import BytesIO

import numpy as np
import tensorflow as tf
from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)


class CropModel:
    def __init__(self, model_path: Path):
        self.model_path = Path(model_path)
        self.info_path = self.model_path.with_name(
            "crop_class_names.json"
        )
        self.model: Any = None
        self.classes: list[str] = []
        self.version = "1.0"
        self.load_error: str | None = None

    @property
    def available(self) -> bool:
        return self.model is not None

    def load(self) -> None:
        if not self.model_path.is_file() or not self.info_path.is_file():
            self.load_error = "Crop model files are missing."
            return

        try:
            classes = json.loads(
                self.info_path.read_text(encoding="utf-8")
            )

            if not isinstance(classes, list) or len(classes) != 10:
                raise ValueError("Expected exactly 10 crop classes.")

            self.model = tf.keras.models.load_model(
                self.model_path,
                compile=False
            )
            self.classes = classes

            logger.info("10-crop MobileNetV2 model loaded.")

        except (OSError, ValueError, RuntimeError, KeyError) as exc:
            self.load_error = "Crop model could not be loaded."
            logger.exception("Crop model loading failed: %s", exc)

    def status(self) -> dict:
        if self.available:
            return {
                "available": True,
                "status": "available",
                "name": "10-Crop MobileNetV2",
                "version": self.version,
                "message": "Crop classification model loaded."
            }

        return {
            "available": False,
            "status": "error" if self.load_error else "not_configured",
            "name": "10-Crop MobileNetV2",
            "version": None,
            "message": self.load_error or "Crop model is not configured."
        }

    def predict(self, image_bytes: bytes) -> dict:
        if not self.available:
            raise RuntimeError("Crop model is unavailable.")

        try:
            image = Image.open(BytesIO(image_bytes)).convert("RGB")
            image = image.resize((160, 160), Image.Resampling.BILINEAR)

            image_array = np.asarray(image, dtype=np.float32)
            image_array = tf.keras.applications.mobilenet_v2.preprocess_input(
                image_array
            )
            image_array = np.expand_dims(image_array, axis=0)

        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise ValueError("Invalid leaf image.") from exc

        probabilities = self.model.predict(image_array, verbose=0)[0]

        index = int(np.argmax(probabilities))
        confidence = float(probabilities[index])

        return {
            "crop_name": self.classes[index],
            "prediction_score": confidence,
            "top_predictions": [
                {
                    "label": self.classes[i],
                    "score": float(probabilities[i])
                }
                for i in np.argsort(probabilities)[::-1][:3]
            ],
            "model_name": "10-Crop MobileNetV2",
            "model_version": self.version
        }
