import asyncio
import base64
import json

import httpx

from backend.app import gemini
from backend.app.config import get_settings


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
        if request.method == "GET":
            captured["list_request"] = request
            return httpx.Response(200, json={
                "models": [{
                    "name": "models/gemini-test-model",
                    "supportedGenerationMethods": ["generateContent"],
                }],
            })
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
        "test-detection-id",
    ))

    request = captured["request"]
    list_request = captured["list_request"]
    body = json.loads(request.content)
    parts = body["contents"][0]["parts"]
    image_part = next(part["inline_data"] for part in parts if "inline_data" in part)

    assert request.url.path.endswith("/models/gemini-test-model:generateContent")
    assert request.headers["x-goog-api-key"] == "test-secret"
    assert "test-secret" not in str(request.url)
    assert "generateContent" in request.url.path
    assert list_request.method == "GET"
    assert list_request.url.path.endswith("/v1beta/models")
    assert list_request.url.params["pageSize"] == "1000"
    assert "Apple" in parts[0]["text"]
    assert image_part["mime_type"] == "image/jpeg"
    assert base64.b64decode(image_part["data"]) == image_bytes
    assert result == valid_analysis()


def test_gemini_logs_google_error_body_and_redacts_api_key(monkeypatch, caplog):
    client_type = httpx.AsyncClient

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={
                "models": [{
                    "name": "models/gemini-test-model",
                    "supportedGenerationMethods": ["generateContent"],
                }, {
                    "name": "models/gemini-3.8-flash",
                    "supportedGenerationMethods": ["generateContent"],
                }],
            })
        return httpx.Response(404, json={
            "error": {
                "code": 404,
                "status": "NOT_FOUND",
                "message": "models/gemini-test-model is not available for API key test-secret",
            }
        })

    monkeypatch.setattr(
        gemini.httpx,
        "AsyncClient",
        lambda timeout: client_type(
            timeout=timeout,
            transport=httpx.MockTransport(handler),
        ),
    )

    try:
        asyncio.run(gemini.analyze_leaf_image(
            b"private image bytes",
            "Hibiscus",
            "image/jpeg",
            "test-secret",
            "gemini-test-model",
            "saved-hibiscus-detection",
        ))
    except gemini.GeminiAnalysisError as error:
        assert error.http_status == 404
        assert error.google_status == "NOT_FOUND"
        assert "test-secret" not in str(error)
    else:
        raise AssertionError("A Google 404 response must fail analysis.")

    assert "saved-hibiscus-detection" in caplog.text
    assert "NOT_FOUND" in caplog.text
    assert "http_status=404" in caplog.text
    assert "test-secret" not in caplog.text
    assert "private image bytes" not in caplog.text


def test_model_list_requires_generate_content_support(monkeypatch):
    client_type = httpx.AsyncClient

    def handler(request):
        return httpx.Response(200, json={
            "models": [{
                "name": "models/gemini-test-model",
                "supportedGenerationMethods": ["embedContent"],
            }],
        })

    monkeypatch.setattr(
        gemini.httpx,
        "AsyncClient",
        lambda timeout: client_type(
            timeout=timeout,
            transport=httpx.MockTransport(handler),
        ),
    )

    async def verify():
        async with gemini.httpx.AsyncClient(timeout=45) as client:
            await gemini._verify_model(
                client, "test-secret", "gemini-test-model", "test-detection-id"
            )

    try:
        asyncio.run(verify())
    except gemini.GeminiAnalysisError as error:
        assert error.google_status == "UNSUPPORTED_GENERATION_METHOD"
        assert "does not support generateContent" in str(error)
    else:
        raise AssertionError("A model without generateContent must be rejected.")


def test_unavailable_configured_model_falls_back_to_verified_image_model(monkeypatch):
    requests = []
    list_count = 0
    client_type = httpx.AsyncClient

    def handler(request):
        nonlocal list_count
        requests.append(request)
        if request.method == "GET":
            list_count += 1
            listed_model = (
                "gemini-2.5-flash"
                if list_count == 1
                else "gemini-3.8-flash"
            )
            return httpx.Response(200, json={
                "models": [{
                    "name": f"models/{listed_model}",
                    "supportedGenerationMethods": ["generateContent"],
                }],
            })
        if request.url.path.endswith(
            "/models/gemini-2.5-flash:generateContent"
        ):
            return httpx.Response(404, json={
                "error": {
                    "code": 404,
                    "status": "NOT_FOUND",
                    "message": "Configured Gemini model is not available.",
                }
            })
        return httpx.Response(200, json={
            "candidates": [{
                "content": {
                    "parts": [{"text": json.dumps(valid_analysis())}]
                }
            }]
        })

    monkeypatch.setattr(
        gemini.httpx,
        "AsyncClient",
        lambda timeout: client_type(
            timeout=timeout,
            transport=httpx.MockTransport(handler),
        ),
    )

    result = asyncio.run(gemini.analyze_leaf_image(
        b"actual hibiscus image",
        "Hibiscus",
        "image/jpeg",
        "test-secret",
        "gemini-2.5-flash",
        "saved-hibiscus-detection",
    ))

    assert result == valid_analysis()
    assert [request.method for request in requests] == ["GET", "POST", "GET", "POST"]
    assert requests[0].url.path.endswith("/v1beta/models")
    assert requests[1].url.path.endswith(
        "/models/gemini-2.5-flash:generateContent"
    )
    assert requests[2].url.path.endswith("/v1beta/models")
    assert requests[3].url.path.endswith(
        "/models/gemini-3.8-flash:generateContent"
    )
    assert "test-secret" not in str(requests[3].url)


def test_gemini_requires_server_side_api_key():
    try:
        asyncio.run(gemini.analyze_leaf_image(
            b"leaf",
            "Apple",
            "image/png",
            None,
            "gemini-test-model",
            "test-detection-id",
        ))
    except gemini.GeminiAnalysisError as error:
        assert error.status == "not_configured"
        assert "not configured" in str(error)
    else:
        raise AssertionError("Gemini must reject a missing API key.")


def test_gemini_model_defaults_and_environment_override(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    assert get_settings().gemini_model == "gemini-3.8-flash"

    monkeypatch.setenv("GEMINI_MODEL", " ")
    assert get_settings().gemini_model == "gemini-3.8-flash"

    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-model")
    assert get_settings().gemini_model == "gemini-test-model"
