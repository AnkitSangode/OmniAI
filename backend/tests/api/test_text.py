
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.api.dependencies import get_current_user
from app.services.llm.litellm_client import (
    LiteLLMRequestError,
    LiteLLMTimeoutError,
)
from app.api.v1.endpoints.text import get_usage_service
from app.services.llm.schemas import TextGenerationResponse


@pytest.fixture
def api_client(monkeypatch):
    async def mock_stream(payload):
        yield {"type": "content", "content": "Hello"}
        yield {"type": "content", "content": " from OmniAI"}
        yield {
            "type": "usage",
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        }
        yield {"type": "finish", "reason": "stop"}
        yield {"type": "done"}

    mock_usage_service = SimpleNamespace(
        record_request=AsyncMock(),
    )

    mock_llm = SimpleNamespace(
        generate=AsyncMock(),
        stream=mock_stream,
        close=AsyncMock(),
        default_model="omni-primary",
        usage_service=mock_usage_service,
    )

    monkeypatch.setattr(
        main,
        "get_settings",
        lambda: object(),
    )

    monkeypatch.setattr(
        main,
        "LiteLLMClient",
        lambda settings: mock_llm,
    )

    async def override_current_user():
        return SimpleNamespace(
            id=uuid4(),
            is_active=True,
        )

    original_overrides = main.app.dependency_overrides.copy()

    main.app.dependency_overrides[get_current_user] = (
        override_current_user
    )

    main.app.dependency_overrides[get_usage_service] = (
        lambda: mock_usage_service
    )

    try:
        with TestClient(main.app) as client:
            yield client, mock_llm

    finally:
        main.app.dependency_overrides.clear()
        main.app.dependency_overrides.update(original_overrides)



# --------------------------------------------------
# Non-streaming generation tests
# --------------------------------------------------


def test_generate_text_success(api_client):
    client, mock_llm = api_client

    mock_llm.generate.return_value = TextGenerationResponse(
        request_id="test-request-123",
        model="omni-primary",
        content="Hello from OmniAI!",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
    )

    response = client.post(
        "/api/v1/text/generate",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "Hello",
                }
            ]
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["content"] == "Hello from OmniAI!"
    assert data["model"] == "omni-primary"
    assert data["total_tokens"] == 15

    mock_llm.generate.assert_awaited_once()


def test_generate_text_unauthorized(api_client):
    client, _ = api_client

    main.app.dependency_overrides.pop(
        get_current_user,
        None,
    )

    response = client.post(
        "/api/v1/text/generate",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "Hello",
                }
            ]
        },
    )

    assert response.status_code == 401


def test_generate_text_invalid_request(api_client):
    client, mock_llm = api_client

    response = client.post(
        "/api/v1/text/generate",
        json={
            "messages": [],
        },
    )

    assert response.status_code == 422

    mock_llm.generate.assert_not_awaited()


def test_generate_text_gateway_error(api_client):
    client, mock_llm = api_client

    mock_llm.generate.side_effect = LiteLLMRequestError(
        "Gateway unavailable"
    )

    response = client.post(
        "/api/v1/text/generate",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "Hello",
                }
            ]
        },
    )

    assert response.status_code == 502

    assert response.json()["detail"] == (
        "AI generation service is currently unavailable."
    )


def test_generate_text_timeout(api_client):
    client, mock_llm = api_client

    mock_llm.generate.side_effect = LiteLLMTimeoutError(
        "Request timed out"
    )

    response = client.post(
        "/api/v1/text/generate",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "Hello",
                }
            ]
        },
    )

    assert response.status_code == 504


# --------------------------------------------------
# Streaming generation tests
# --------------------------------------------------


def test_stream_text_success(api_client):
    client, mock_llm = api_client

    response = client.post(
        "/api/v1/text/stream",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "Hello",
                }
            ]
        },
    )

    assert response.status_code == 200

    assert response.headers["content-type"].startswith(
        "text/event-stream"
    )

    body = response.text

    assert '"type": "content"' in body
    assert '"content": "Hello"' in body
    assert '"content": " from OmniAI"' in body
    assert '"type": "usage"' in body
    assert '"type": "finish"' in body
    assert '"type": "done"' in body


def test_stream_text_timeout(api_client):
    client, mock_llm = api_client

    async def timeout_stream(payload):
        raise LiteLLMTimeoutError("Gateway timed out")
        yield

    mock_llm.stream = timeout_stream

    response = client.post(
        "/api/v1/text/stream",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "Hello",
                }
            ]
        },
    )

    assert response.status_code == 200
    assert '"type": "error"' in response.text
    assert "AI generation timed out." in response.text


def test_stream_text_gateway_error(api_client):
    client, mock_llm = api_client

    async def failing_stream(payload):
        raise LiteLLMRequestError("Gateway unavailable")
        yield

    mock_llm.stream = failing_stream

    response = client.post(
        "/api/v1/text/stream",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "Hello",
                }
            ]
        },
    )

    assert response.status_code == 200
    assert '"type": "error"' in response.text
    assert "AI generation service is unavailable." in response.text



def test_generate_text_records_usage(api_client):
    client, mock_llm = api_client

    mock_llm.generate.return_value = TextGenerationResponse(
        request_id="provider-request-123",
        model="omni-primary",
        content="Hello!",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
    )

    response = client.post(
        "/api/v1/text/generate",
        json={
            "messages": [
                {"role": "user", "content": "Hello"}
            ]
        },
    )

    assert response.status_code == 200

    usage_service = mock_llm.usage_service

    usage_service.record_request.assert_awaited_once()

    recorded = usage_service.record_request.await_args.kwargs

    assert recorded["request_type"] == "generate"
    assert recorded["model"] == "omni-primary"
    assert recorded["prompt_tokens"] == 10
    assert recorded["completion_tokens"] == 5
    assert recorded["total_tokens"] == 15
    assert recorded["status"] == "success"
    assert recorded["provider_request_id"] == "provider-request-123"


def test_generate_text_records_failed_request(api_client):
    client, mock_llm = api_client

    mock_llm.generate.side_effect = LiteLLMRequestError(
        "Gateway unavailable"
    )

    response = client.post(
        "/api/v1/text/generate",
        json={
            "messages": [
                {"role": "user", "content": "Hello"}
            ]
        },
    )

    assert response.status_code == 502

    usage_service = mock_llm.usage_service

    usage_service.record_request.assert_awaited_once()

    recorded = usage_service.record_request.await_args.kwargs

    assert recorded["status"] == "failed"
    assert recorded["error_code"] == "gateway_error"
    assert recorded["request_type"] == "generate"


def test_stream_text_records_usage(api_client):
    client, mock_llm = api_client

    response = client.post(
        "/api/v1/text/stream",
        json={
            "messages": [
                {"role": "user", "content": "Hello"}
            ]
        },
    )

    assert response.status_code == 200

    usage_service = mock_llm.usage_service

    usage_service.record_request.assert_awaited_once()

    recorded = usage_service.record_request.await_args.kwargs

    assert recorded["request_type"] == "stream"
    assert recorded["status"] == "success"
    assert recorded["prompt_tokens"] == 10
    assert recorded["completion_tokens"] == 5
    assert recorded["total_tokens"] == 15


def test_usage_failure_does_not_break_generation(api_client):
    client, mock_llm = api_client

    mock_llm.generate.return_value = TextGenerationResponse(
        request_id="provider-request-456",
        model="omni-primary",
        content="Still successful!",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
    )

    mock_llm.usage_service.record_request.side_effect = (
        RuntimeError("Database unavailable")
    )

    response = client.post(
        "/api/v1/text/generate",
        json={
            "messages": [
                {"role": "user", "content": "Hello"}
            ]
        },
    )

    assert response.status_code == 200
    assert response.json()["content"] == "Still successful!"
