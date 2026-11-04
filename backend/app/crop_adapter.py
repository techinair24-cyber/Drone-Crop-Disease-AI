import json
import logging
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, UnidentifiedImageError
from ai_edge_litert.interpreter import Interpreter

logger = logging.getLogger(__name__)


class CropModel:
    def __init__(self, model_path: Path):
        self.model_path = Path(model_path)
        self.info_path = self.model_path.with_name("crop_class_names.json")
        self.interpreter = None
        self.input_details = None
        self.output_details = None
        self.classes = []
        self.version = "1.0"
        self.load_error = None

    @property
    def available(self):
        return self.interpreter is not None

    def load(self):
        if not self.model_path.is_file() or not self.info_path.is_file():
            self.load_error = "Crop model files are missing."
            return

        try:
            classes = json.loads(
                self.info_path.read_text(encoding="utf-8")
            )

            if not isinstance(classes, list) or len(classes) != 10:
                raise ValueError("Expected exactly 10 crop classes.")

            interpreter = Interpreter(
                model_path=str(self.model_path),
                num_threads=2
            )
            interpreter.allocate_tensors()

            self.interpreter = interpreter
            self.input_details = interpreter.get_input_details()
            self.output_details = interpreter.get_output_details()
            self.classes = classes

            logger.info("10-crop TensorFlow Lite model loaded.")

        except Exception as exc:
            self.load_error = "Crop model could not be loaded."
            logger.exception("Crop model loading failed: %s", exc)

    def status(self):
        if self.available:
            return {
                "available": True,
                "status": "available",
                "name": "10-Crop MobileNetV2 Lite",
                "version": self.version,
                "message": "Crop classification model loaded."
            }

        return {
            "available": False,
            "status": "error" if self.load_error else "not_configured",
            "name": "10-Crop MobileNetV2 Lite",
            "version": None,
            "message": self.load_error or "Crop model is not configured."
        }

    def predict(self, image_bytes: bytes):
        if not self.available:
            raise RuntimeError("Crop model is unavailable.")

        try:
            image = Image.open(BytesIO(image_bytes)).convert("RGB")
            image = image.resize((160, 160), Image.Resampling.BILINEAR)

            image_array = np.asarray(image, dtype=np.float32)
            image_array = (image_array / 127.5) - 1.0
            image_array = np.expand_dims(image_array, axis=0)

        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise ValueError("Invalid leaf image.") from exc

        input_index = self.input_details[0]["index"]
        output_index = self.output_details[0]["index"]

        self.interpreter.set_tensor(input_index, image_array)
        self.interpreter.invoke()

        probabilities = self.interpreter.get_tensor(output_index)[0]

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
            "model_name": "10-Crop MobileNetV2 Lite",
            "model_version": self.version
        }
