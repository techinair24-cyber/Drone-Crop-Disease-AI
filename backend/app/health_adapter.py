import json
import logging
from io import BytesIO
from pathlib import Path
from threading import Lock

import numpy as np
from ai_edge_litert.interpreter import Interpreter
from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)

HEALTH_CLASSES = ("Healthy", "Unhealthy")
SUPPORTED_CROPS = (
    "Apple",
    "Chilli",
    "Grape",
    "Hibiscus",
    "Maize",
    "Peach",
    "Potato",
    "Strawberry",
    "Tomato",
    "Wheat",
)


class HealthModel:
    def __init__(self, model_path: Path):
        self.model_path = Path(model_path)
        self.info_path = self.model_path.with_name("health_model_info.json")
        self.interpreter = None
        self.input_details = None
        self.output_details = None
        self.supported_crops: tuple[str, ...] = ()
        self.version = "1.0"
        self.load_error: str | None = None
        self._inference_lock = Lock()

    @property
    def available(self) -> bool:
        return self.interpreter is not None

    def load(self) -> None:
        if not self.model_path.is_file() or not self.info_path.is_file():
            self.load_error = "Shared health model files are missing."
            return

        try:
            info = json.loads(self.info_path.read_text(encoding="utf-8"))
            if info.get("classes") != list(HEALTH_CLASSES):
                raise ValueError("Unexpected health model class order.")
            if info.get("output") != "probability_of_Unhealthy":
                raise ValueError("Unexpected health model output mapping.")
            if info.get("input_size") != [160, 160]:
                raise ValueError("Unexpected health model input size.")

            supported_crops = info.get("supported_crops")
            if (
                not isinstance(supported_crops, list)
                or set(supported_crops) != set(SUPPORTED_CROPS)
                or len(supported_crops) != len(SUPPORTED_CROPS)
            ):
                raise ValueError("Unexpected health model crop coverage.")

            interpreter = Interpreter(
                model_path=str(self.model_path),
                num_threads=2,
            )
            interpreter.allocate_tensors()
            input_details = interpreter.get_input_details()
            output_details = interpreter.get_output_details()

            if (
                len(input_details) != 1
                or tuple(input_details[0]["shape"]) != (1, 160, 160, 3)
                or input_details[0]["dtype"] != np.float32
            ):
                raise ValueError("Unsupported health model input tensor.")
            if (
                len(output_details) != 1
                or tuple(output_details[0]["shape"]) != (1, 1)
                or output_details[0]["dtype"] != np.float32
            ):
                raise ValueError("Unsupported health model output tensor.")

            self.interpreter = interpreter
            self.input_details = input_details
            self.output_details = output_details
            self.supported_crops = tuple(supported_crops)
            logger.info("Shared 10-crop health LiteRT model loaded.")
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
            self.load_error = "Shared health model could not be loaded."
            logger.exception("Shared health model loading failed: %s", exc)

    def status(self) -> dict:
        if self.available:
            return {
                "available": True,
                "status": "available",
                "name": "Shared 10-Crop Healthy/Unhealthy LiteRT",
                "version": self.version,
                "message": "Shared health classification model loaded.",
            }

        return {
            "available": False,
            "status": "error" if self.load_error else "not_configured",
            "name": "Shared 10-Crop Healthy/Unhealthy LiteRT",
            "version": None,
            "message": self.load_error or "Shared health model is not configured.",
        }

    def predict(self, image_bytes: bytes, crop_name: str) -> dict:
        if not self.available:
            raise RuntimeError("Shared health model is unavailable.")
        if crop_name not in self.supported_crops:
            raise ValueError(
                f"The shared health model does not support crop {crop_name!r}."
            )

        try:
            with Image.open(BytesIO(image_bytes)) as source:
                image = source.convert("RGB").resize(
                    (160, 160), Image.Resampling.BILINEAR
                )
            image_array = np.asarray(image, dtype=np.float32)
            image_array = (image_array / 127.5) - 1.0
            image_array = np.expand_dims(image_array, axis=0)
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise ValueError("Invalid leaf image.") from exc

        input_index = self.input_details[0]["index"]
        output_index = self.output_details[0]["index"]
        with self._inference_lock:
            self.interpreter.set_tensor(input_index, image_array)
            self.interpreter.invoke()
            unhealthy_probability = float(
                self.interpreter.get_tensor(output_index)[0, 0]
            )

        if (
            not np.isfinite(unhealthy_probability)
            or not 0.0 <= unhealthy_probability <= 1.0
        ):
            raise RuntimeError("Health model returned an invalid probability.")

        health_probabilities = {
            "Healthy": 1.0 - unhealthy_probability,
            "Unhealthy": unhealthy_probability,
        }
        health_status = (
            "Unhealthy" if unhealthy_probability > 0.5 else "Healthy"
        )
        health_confidence = health_probabilities[health_status]

        return {
            "health_status": health_status,
            "health_confidence": health_confidence,
            "health_probabilities": health_probabilities,
            "message": f"{crop_name} classified as {health_status}.",
        }
