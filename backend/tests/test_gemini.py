import asyncio
import base64
import json

import httpx

from backend.app import gemini


def valid_analysis():
    return {
        "assessment": "likely_disease",
        "likely_disease": "Possible apple scab",
        "possible_causes": ["Apple scab-like symptoms"],
        "explanation": "The image shows symptoms that can be consistent with apple scab.",
        "visible_symptoms": ["Olive-brown leaf lesions"],
        "immediate_actions": ["Inspect nearby leaves for similar symptoms."],
        "treatment_management": ["Seek local confirmation before disease-specific treatment."],
        "organic_options": ["Remove fallen leaves from the area."],
        "prevention": ["Improve airflow around the canopy."],
        "follow_up": ["Monitor new growth for changes."],
        "expert_guidance": "Consult a local agricultural extension expert if symptoms spread.",
    }


def test_gemini_request_includes_actual_image_and_crop(monkeypatch):
    image_bytes = b"actual leaf image bytes"
    captured = {}
    client_type = httpx.AsyncClient

    def handler(request):
        captured["request"] = request
        response_body = {
            "candidates": [{
                "content": {
                    "parts": [{"text": json.dumps(valid_analysis())}]
                }
            }]
        }
        return httpx.Response(200, json=response_body)

    monkeypatch.setattr(
        gemini.httpx,
        "AsyncClient",
        lambda timeout: client_type(
            timeout=timeout,
            transport=httpx.MockTransport(handler),
        ),
    )

    result = asyncio.run(gemini.analyze_leaf_image(
        image_bytes,
        "Apple",
        "image/jpeg",
        "test-secret",
        "gemini-test-model",
    ))

    request = captured["request"]
    body = json.loads(request.content)
    parts = body["contents"][0]["parts"]
    image_part = next(part["inline_data"] for part in parts if "inline_data" in part)

    assert request.url.path.endswith("/models/gemini-test-model:generateContent")
    assert request.headers["x-goog-api-key"] == "test-secret"
    assert "test-secret" not in str(request.url)
    assert "Apple" in parts[0]["text"]
    assert image_part["mime_type"] == "image/jpeg"
    assert base64.b64decode(image_part["data"]) == image_bytes
    assert result == valid_analysis()


def test_gemini_requires_server_side_api_key():
    try:
        asyncio.run(gemini.analyze_leaf_image(
            b"leaf",
            "Apple",
            "image/png",
            None,
            "gemini-test-model",
        ))
    except gemini.GeminiAnalysisError as error:
        assert error.status == "not_configured"
        assert "not configured" in str(error)
    else:
        raise AssertionError("Gemini must reject a missing API key.")
