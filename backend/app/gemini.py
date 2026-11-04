import base64
import json
import logging
import re
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError, model_validator

logger = logging.getLogger(__name__)
API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
FALLBACK_MODEL_ID = "gemini-3.8-flash"
MODEL_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class GeminiAnalysisError(Exception):
    def __init__(
        self,
        message: str,
        status: Literal["failed", "not_configured"] = "failed",
        *,
        http_status: int | None = None,
        google_status: str | None = None,
        google_message: str | None = None,
    ):
        super().__init__(message)
        self.status = status
        self.http_status = http_status
        self.google_status = google_status
        self.google_message = google_message


def _safe_message(value: object, api_key: str) -> str:
    message = str(value).replace("\r", " ").replace("\n", " ").strip()
    if api_key:
        message = message.replace(api_key, "[REDACTED]")
    return message[:1000]


def _google_error(response: httpx.Response, api_key: str) -> tuple[str | None, str]:
    try:
        error = response.json().get("error", {})
    except (ValueError, AttributeError):
        error = {}
    if not isinstance(error, dict):
        error = {}
    status = error.get("status")
    message = _safe_message(
        error.get("message") or response.reason_phrase or "Unknown Google API error.",
        api_key,
    )
    return (str(status)[:100] if status else None, message)


async def _verify_model(client: httpx.AsyncClient, api_key: str, model_id: str, detection_id: str) -> None:
    page_token = None
    try:
        for _ in range(100):
            params = {"pageSize": 1000}
            if page_token:
                params["pageToken"] = page_token
            response = await client.get(
                f"{API_ROOT}/models",
                headers={"x-goog-api-key": api_key},
                params=params,
            )
            if response.is_error:
                google_status, google_message = _google_error(response, api_key)
                logger.warning(
                    "Gemini model-list request failed detection_id=%s http_status=%s "
                    "model=%s google_status=%s google_message=%s",
                    detection_id,
                    response.status_code,
                    model_id,
                    google_status or "unspecified",
                    google_message,
                )
                raise GeminiAnalysisError(
                    f"Gemini model verification failed (HTTP {response.status_code}): "
                    f"{google_message} You can retry.",
                    http_status=response.status_code,
                    google_status=google_status,
                    google_message=google_message,
                )
            body = response.json()
            if not isinstance(body, dict):
                raise ValueError("Invalid models response.")
            models = body.get("models", [])
            if not isinstance(models, list):
                raise ValueError("Invalid models list.")
            for model in models:
                if not isinstance(model, dict):
                    continue
                listed_id = str(model.get("name", "")).removeprefix("models/")
                base_id = str(model.get("baseModelId", ""))
                if model_id in {listed_id, base_id}:
                    methods = model.get("supportedGenerationMethods", [])
                    if "generateContent" in methods:
                        logger.info(
                            "Gemini model verified detection_id=%s model=%s "
                            "api_version=v1beta supported_method=generateContent",
                            detection_id,
                            model_id,
                        )
                        return
                    raise GeminiAnalysisError(
                        f"Configured Gemini model {model_id} does not support "
                        "generateContent. Set GEMINI_MODEL to an image-capable "
                        "model that supports generateContent.",
                        google_status="UNSUPPORTED_GENERATION_METHOD",
                        google_message=(
                            f"Model {model_id} does not list generateContent "
                            "in supportedGenerationMethods."
                        ),
                    )
            page_token = body.get("nextPageToken")
            if not page_token:
                break
    except GeminiAnalysisError:
        raise
    except httpx.TimeoutException as exc:
        logger.warning(
            "Gemini model-list request failed detection_id=%s http_status=timeout "
            "model=%s google_status=TIMEOUT google_message=%s",
            detection_id,
            model_id,
            "Gemini model-list request timed out.",
        )
        raise GeminiAnalysisError(
            "Gemini model verification timed out. You can retry.",
            google_status="TIMEOUT",
            google_message="Gemini model-list request timed out.",
        ) from exc
    except httpx.RequestError as exc:
        message = _safe_message(exc, api_key)
        logger.warning(
            "Gemini model-list request failed detection_id=%s http_status=network_error "
            "model=%s google_status=NETWORK_ERROR google_message=%s",
            detection_id,
            model_id,
            message,
        )
        raise GeminiAnalysisError(
            "Gemini model verification could not reach Google. You can retry.",
            google_status="NETWORK_ERROR",
            google_message=message,
        ) from exc
    except (ValueError, TypeError) as exc:
        raise GeminiAnalysisError(
            "Gemini returned an invalid model list. You can retry.",
            google_status="INVALID_MODEL_LIST",
            google_message=_safe_message(exc, api_key),
        ) from exc

    message = (
        f"Model {model_id} was not returned by the Gemini API model-list "
        "endpoint for this API key."
    )
    logger.warning(
        "Gemini model unavailable detection_id=%s http_status=200 model=%s "
        "google_status=MODEL_NOT_LISTED google_message=%s",
        detection_id,
        model_id,
        message,
    )
    raise GeminiAnalysisError(
        f"{message} Set GEMINI_MODEL to a listed model that supports "
        "generateContent.",
        http_status=200,
        google_status="MODEL_NOT_LISTED",
        google_message=message,
    )


class GeminiDiseaseAnalysis(BaseModel):
    assessment: Literal["likely_disease", "possible_causes", "inconclusive"]
    likely_disease: str | None = Field(max_length=300)
    possible_causes: list[str] = Field(max_length=8)
    explanation: str = Field(max_length=3000)
    visible_symptoms: list[str] = Field(max_length=12)
    immediate_actions: list[str] = Field(max_length=12)
    treatment_management: list[str] = Field(max_length=12)
    organic_options: list[str] = Field(max_length=12)
    prevention: list[str] = Field(max_length=12)
    follow_up: list[str] = Field(max_length=12)
    expert_guidance: str = Field(max_length=2000)

    @model_validator(mode="after")
    def validate_assessment(self):
        if self.assessment == "likely_disease" and not self.likely_disease:
            raise ValueError("A likely disease assessment needs a disease name.")
        if self.assessment != "likely_disease" and self.likely_disease is not None:
            raise ValueError(
                "Only a likely disease assessment may include a disease name."
            )
        return self


def _prompt(crop_name: str) -> str:
    return f"""
Examine the attached actual leaf image of {crop_name}. The crop name is supplied
by the application's crop classifier; independently inspect the visible image
before drawing conclusions. Return only one JSON object with these exact keys:
assessment, likely_disease, possible_causes, explanation, visible_symptoms,
immediate_actions, treatment_management, organic_options, prevention,
follow_up, expert_guidance.

Use assessment "likely_disease" only when visible image evidence supports a
specific likely disease; otherwise use "possible_causes" or "inconclusive".
Never present a suspected disease as confirmed. If the image is unclear, say so
and use "inconclusive", with likely_disease null. Describe visible symptoms
separately from possible causes. Give practical, crop-appropriate steps, but do
not name pesticide products, chemical active ingredients, or application
dosages. Explain that disease-specific treatment requires local expert
confirmation. Do not infer facts not visible in the image.

Use arrays of concise strings for possible_causes, visible_symptoms,
immediate_actions, treatment_management, organic_options, prevention, and
follow_up. Use plain strings for explanation and expert_guidance. Use null for
likely_disease unless assessment is "likely_disease".
""".strip()


async def _generate_content(
    client: httpx.AsyncClient,
    image_bytes: bytes,
    crop_name: str,
    mime_type: str,
    api_key: str,
    model_id: str,
    detection_id: str,
) -> httpx.Response:
    logger.info(
        "Gemini generateContent request detection_id=%s model=%s "
        "api_version=v1beta image_mime_type=%s image_bytes=%s",
        detection_id,
        model_id,
        mime_type,
        len(image_bytes),
    )
    try:
        response = await client.post(
            f"{API_ROOT}/models/{model_id}:generateContent",
            headers={"x-goog-api-key": api_key},
            json={
                "contents": [{
                    "role": "user",
                    "parts": [
                        {"text": _prompt(crop_name)},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": base64.b64encode(image_bytes).decode("ascii"),
                            }
                        },
                    ],
                }],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "temperature": 0.2,
                    "maxOutputTokens": 2048,
                },
            },
        )
    except httpx.TimeoutException as exc:
        logger.warning(
            "Gemini request failed detection_id=%s http_status=timeout model=%s "
            "google_status=TIMEOUT google_message=%s",
            detection_id,
            model_id,
            "Gemini request timed out.",
        )
        raise GeminiAnalysisError("Gemini analysis timed out. You can retry.") from exc
    except httpx.RequestError as exc:
        message = _safe_message(exc, api_key)
        logger.warning(
            "Gemini request failed detection_id=%s http_status=network_error model=%s "
            "google_status=NETWORK_ERROR google_message=%s",
            detection_id,
            model_id,
            message,
        )
        raise GeminiAnalysisError(
            "Gemini could not be reached. You can retry.",
            google_status="NETWORK_ERROR",
            google_message=message,
        ) from exc

    if response.is_error:
        google_status, google_message = _google_error(response, api_key)
        logger.warning(
            "Gemini request failed detection_id=%s http_status=%s model=%s "
            "google_status=%s google_message=%s",
            detection_id,
            response.status_code,
            model_id,
            google_status or "unspecified",
            google_message,
        )
        raise GeminiAnalysisError(
            f"Gemini analysis failed (HTTP {response.status_code}): "
            f"{google_message} You can retry.",
            http_status=response.status_code,
            google_status=google_status,
            google_message=google_message,
        )

    logger.info(
        "Gemini generateContent succeeded detection_id=%s http_status=%s "
        "model=%s api_version=v1beta google_status=OK",
        detection_id,
        response.status_code,
        model_id,
    )
    return response


async def analyze_leaf_image(
    image_bytes: bytes,
    crop_name: str,
    mime_type: str,
    api_key: str | None,
    model_name: str,
    detection_id: str,
) -> dict:
    if not api_key:
        raise GeminiAnalysisError(
            "Gemini is not configured on the backend.",
            status="not_configured",
        )

    model_id = model_name.removeprefix("models/")
    if not MODEL_ID_PATTERN.fullmatch(model_id):
        raise GeminiAnalysisError(
            "The configured Gemini model identifier is invalid.",
            google_status="INVALID_MODEL_ID",
            google_message="GEMINI_MODEL must be a model ID, not a URL or path.",
        )

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            try:
                await _verify_model(client, api_key, model_id, detection_id)
            except GeminiAnalysisError as exc:
                if (
                    exc.google_status
                    not in {"MODEL_NOT_LISTED", "UNSUPPORTED_GENERATION_METHOD"}
                    or model_id == FALLBACK_MODEL_ID
                ):
                    raise
                logger.warning(
                    "Gemini configured model unavailable; using verified fallback "
                    "detection_id=%s configured_model=%s fallback_model=%s "
                    "google_status=%s google_message=%s",
                    detection_id,
                    model_id,
                    FALLBACK_MODEL_ID,
                    exc.google_status,
                    exc.google_message or str(exc),
                )
                model_id = FALLBACK_MODEL_ID
                await _verify_model(client, api_key, model_id, detection_id)
            try:
                response = await _generate_content(
                    client,
                    image_bytes,
                    crop_name,
                    mime_type,
                    api_key,
                    model_id,
                    detection_id,
                )
            except GeminiAnalysisError as exc:
                if (
                    exc.google_status != "NOT_FOUND"
                    or model_id == FALLBACK_MODEL_ID
                ):
                    raise
                logger.warning(
                    "Gemini configured model returned NOT_FOUND; trying verified "
                    "fallback detection_id=%s configured_model=%s fallback_model=%s "
                    "google_status=%s google_message=%s",
                    detection_id,
                    model_id,
                    FALLBACK_MODEL_ID,
                    exc.google_status,
                    exc.google_message or str(exc),
                )
                model_id = FALLBACK_MODEL_ID
                await _verify_model(client, api_key, model_id, detection_id)
                response = await _generate_content(
                    client,
                    image_bytes,
                    crop_name,
                    mime_type,
                    api_key,
                    model_id,
                    detection_id,
                )
    except httpx.TimeoutException as exc:
        logger.warning(
            "Gemini client failed detection_id=%s http_status=timeout model=%s "
            "google_status=TIMEOUT google_message=%s",
            detection_id,
            model_id,
            "Gemini request timed out.",
        )
        raise GeminiAnalysisError(
            "Gemini analysis timed out. You can retry.",
            google_status="TIMEOUT",
            google_message="Gemini request timed out.",
        ) from exc
    except httpx.RequestError as exc:
        message = _safe_message(exc, api_key)
        logger.warning(
            "Gemini client failed detection_id=%s http_status=network_error model=%s "
            "google_status=NETWORK_ERROR google_message=%s",
            detection_id,
            model_id,
            message,
        )
        raise GeminiAnalysisError(
            "Gemini could not be reached. You can retry.",
            google_status="NETWORK_ERROR",
            google_message=message,
        ) from exc

    try:
        parts = response.json()["candidates"][0]["content"]["parts"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise GeminiAnalysisError(
            "Gemini returned an incomplete or invalid analysis. You can retry."
        ) from exc
    if not isinstance(parts, list):
        raise GeminiAnalysisError(
            "Gemini returned an incomplete or invalid analysis. You can retry."
        )

    result = None
    for part in parts:
        if not isinstance(part, dict) or part.get("thought"):
            continue
        text = part.get("text")
        if not isinstance(text, str):
            continue
        try:
            result = GeminiDiseaseAnalysis.model_validate_json(text)
        except (ValueError, ValidationError):
            continue
        break

    if result is None:
        raise GeminiAnalysisError(
            "Gemini returned an incomplete or invalid analysis. You can retry."
        )

    if result.assessment == "inconclusive" and result.likely_disease:
        raise GeminiAnalysisError(
            "Gemini returned an inconsistent analysis. You can retry."
        )

    return result.model_dump(mode="json")
