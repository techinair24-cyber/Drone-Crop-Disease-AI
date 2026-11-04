import base64
import json
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError, model_validator


class GeminiAnalysisError(Exception):
    def __init__(self, message: str, status: Literal["failed", "not_configured"] = "failed"):
        super().__init__(message)
        self.status = status


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


async def analyze_leaf_image(
    image_bytes: bytes,
    crop_name: str,
    mime_type: str,
    api_key: str | None,
    model_name: str,
) -> dict:
    if not api_key:
        raise GeminiAnalysisError(
            "Gemini is not configured on the backend.",
            status="not_configured",
        )

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model_name}:generateContent"
    )
    payload = {
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
    }

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                url,
                headers={"x-goog-api-key": api_key},
                json=payload,
            )
    except httpx.TimeoutException as exc:
        raise GeminiAnalysisError("Gemini analysis timed out. You can retry.") from exc
    except httpx.RequestError as exc:
        raise GeminiAnalysisError(
            "Gemini could not be reached. You can retry."
        ) from exc

    if response.is_error:
        raise GeminiAnalysisError(
            f"Gemini analysis failed (HTTP {response.status_code}). You can retry."
        )

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
