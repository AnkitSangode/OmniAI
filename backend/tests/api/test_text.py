
import logging
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.main as main

from app.api.dependencies import get_current_user
from app.api.v1.endpoints.text import (
    get_observability_service,
    get_usage_service,
)
from app.services.llm.litellm_client import (
    LiteLLMRequestError,
    LiteLLMTimeoutError,
)
from app.services.llm.schemas import TextGenerationResponse


logger = logging.getLogger(__name__)


@pytest.fixture
def api_client(monkeypatch):
    """
    Provides an isolated API client with mocked:
    - LiteLLM client
    - Authenticated user
    - Usage service
    - Langfuse observability service
    """

    test_user = SimpleNamespace(
        id=uuid4(),
        is_active=True,
    )

    mock_llm = Mock()
    mock_llm.default_model = "omni-primary"
    mock_llm.generate = AsyncMock()
    mock_llm.close = AsyncMock()

    async def default_stream(payload):
        yield {
            "type": "content",
            "content": "Hello",
        }

        yield {
            "type": "content",
            "content": " from OmniAI",
        }

        yield {
            "type": "usage",
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        }

        yield {
            "type": "finish",
            "finish_reason": "stop",
        }

        yield {
            "type": "done",
        }

    mock_llm.stream = Mock(side_effect=default_stream)

    mock_usage_service = Mock()
    mock_usage_service.calculate_cost = Mock(return_value=None)
    mock_usage_service.record_request = AsyncMock()

    mock_generation = SimpleNamespace(
        update=Mock(),
    )

    mock_observability = Mock()
    mock_observability.enabled = True
    mock_observability.trace_generation = Mock(
        return_value=nullcontext(mock_generation)
    )
    mock_observability.update_generation = Mock()
    mock_observability.shutdown = Mock()

    # Mock the dependencies created by the application lifespan.
    monkeypatch.setattr(
        main,
        "get_settings",
        lambda: SimpleNamespace(),
    )

    monkeypatch.setattr(
        main,
        "LiteLLMClient",
        lambda settings: mock_llm,
    )

    # Some application lifespan implementations shut down Langfuse.
    if hasattr(main, "get_langfuse_service"):
        monkeypatch.setattr(
            main,
            "get_langfuse_service",
            lambda: mock_observability,
        )

    original_overrides = main.app.dependency_overrides.copy()

    main.app.dependency_overrides[get_current_user] = (
        lambda: test_user
    )

    main.app.dependency_overrides[get_usage_service] = (
        lambda: mock_usage_service
    )

    main.app.dependency_overrides[get_observability_service] = (
        lambda: mock_observability
    )

    try:
        with TestClient(main.app) as client:
            yield (
                client,
                mock_llm,
                mock_usage_service,
                mock_observability,
                test_user,
            )
    finally:
        main.app.dependency_overrides.clear()
        main.app.dependency_overrides.update(original_overrides)


def valid_generation_payload():
    return {
        "messages": [
            {
                "role": "user",
                "content": "Hello",
            }
        ]
    }


def test_generate_text_success(api_client):
    client, mock_llm, _, _, _ = api_client

    mock_llm.generate.return_value = TextGenerationResponse(
        request_id="provider-request-123",
        model="omni-primary",
        content="Hello from OmniAI!",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
    )

    response = client.post(
        "/api/v1/text/generate",
        json=valid_generation_payload(),
    )

    assert response.status_code == 200
    assert response.json()["content"] == "Hello from OmniAI!"
    assert response.json()["model"] == "omni-primary"
    assert response.json()["prompt_tokens"] == 10
    assert response.json()["completion_tokens"] == 5
    assert response.json()["total_tokens"] == 15

    mock_llm.generate.assert_awaited_once()


def test_generate_text_unauthorized(api_client):
    client, _, _, _, _ = api_client

    main.app.dependency_overrides.pop(
        get_current_user,
        None,
    )

    response = client.post(
        "/api/v1/text/generate",
        json=valid_generation_payload(),
    )

    assert response.status_code == 401


def test_generate_text_invalid_request(api_client):
    client, mock_llm, _, _, _ = api_client

    response = client.post(
        "/api/v1/text/generate",
        json={
            "messages": [],
        },
    )

    assert response.status_code == 422
    mock_llm.generate.assert_not_awaited()


def test_generate_text_gateway_error(api_client):
    client, mock_llm, _, _, _ = api_client

    mock_llm.generate.side_effect = LiteLLMRequestError(
        "Gateway unavailable"
    )

    response = client.post(
        "/api/v1/text/generate",
        json=valid_generation_payload(),
    )

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "AI generation service is unavailable."
    )


def test_generate_text_timeout(api_client):
    client, mock_llm, _, _, _ = api_client

    mock_llm.generate.side_effect = LiteLLMTimeoutError(
        "Request timed out"
    )

    response = client.post(
        "/api/v1/text/generate",
        json=valid_generation_payload(),
    )

    assert response.status_code == 504
    assert response.json()["detail"] == (
        "AI generation request timed out."
    )


def test_stream_text_success(api_client):
    client, _, _, _, _ = api_client

    response = client.post(
        "/api/v1/text/stream",
        json=valid_generation_payload(),
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
    assert '"prompt_tokens": 10' in body
    assert '"completion_tokens": 5' in body
    assert '"total_tokens": 15' in body

    assert '"type": "finish"' in body
    assert '"type": "done"' in body


def test_stream_text_timeout(api_client):
    client, mock_llm, _, _, _ = api_client

    async def failing_stream(payload):
        raise LiteLLMTimeoutError("Request timed out")
        yield

    mock_llm.stream = Mock(side_effect=failing_stream)

    response = client.post(
        "/api/v1/text/stream",
        json=valid_generation_payload(),
    )

    assert response.status_code == 200
    assert '"type": "error"' in response.text
    assert "AI generation request timed out." in response.text


def test_stream_text_gateway_error(api_client):
    client, mock_llm, _, _, _ = api_client

    async def failing_stream(payload):
        raise LiteLLMRequestError("Gateway unavailable")
        yield

    mock_llm.stream = Mock(side_effect=failing_stream)

    response = client.post(
        "/api/v1/text/stream",
        json=valid_generation_payload(),
    )

    assert response.status_code == 200
    assert '"type": "error"' in response.text
    assert "AI generation service is unavailable." in response.text


def test_generate_text_records_usage(api_client):
    client, mock_llm, usage_service, _, test_user = api_client

    mock_llm.generate.return_value = TextGenerationResponse(
        request_id="provider-request-456",
        model="omni-primary",
        content="Usage tracking test",
        prompt_tokens=20,
        completion_tokens=10,
        total_tokens=30,
    )

    response = client.post(
        "/api/v1/text/generate",
        json=valid_generation_payload(),
    )

    assert response.status_code == 200

    usage_service.record_request.assert_awaited_once()

    usage_args = usage_service.record_request.await_args.kwargs

    assert usage_args["user_id"] == test_user.id
    assert usage_args["request_type"] == "generate"
    assert usage_args["model"] == "omni-primary"
    assert usage_args["prompt_tokens"] == 20
    assert usage_args["completion_tokens"] == 10
    assert usage_args["total_tokens"] == 30
    assert usage_args["status"] == "success"
    assert usage_args["provider_request_id"] == (
        "provider-request-456"
    )


def test_generate_text_records_failed_request(api_client):
    client, mock_llm, usage_service, _, test_user = api_client

    mock_llm.generate.side_effect = LiteLLMRequestError(
        "Gateway unavailable"
    )

    response = client.post(
        "/api/v1/text/generate",
        json=valid_generation_payload(),
    )

    assert response.status_code == 502

    usage_service.record_request.assert_awaited_once()

    usage_args = usage_service.record_request.await_args.kwargs

    assert usage_args["user_id"] == test_user.id
    assert usage_args["request_type"] == "generate"
    assert usage_args["status"] == "failed"
    assert usage_args["error_code"] == "llm_gateway_error"


def test_stream_text_records_usage(api_client):
    client, _, usage_service, _, test_user = api_client

    response = client.post(
        "/api/v1/text/stream",
        json=valid_generation_payload(),
    )

    assert response.status_code == 200

    usage_service.record_request.assert_awaited_once()

    usage_args = usage_service.record_request.await_args.kwargs

    assert usage_args["user_id"] == test_user.id
    assert usage_args["request_type"] == "stream"
    assert usage_args["prompt_tokens"] == 10
    assert usage_args["completion_tokens"] == 5
    assert usage_args["total_tokens"] == 15
    assert usage_args["status"] == "success"


def test_usage_failure_does_not_break_generation(api_client):
    client, mock_llm, usage_service, _, _ = api_client

    mock_llm.generate.return_value = TextGenerationResponse(
        request_id="provider-request-789",
        model="omni-primary",
        content="Generation should still succeed",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
    )

    usage_service.record_request.side_effect = RuntimeError(
        "Database temporarily unavailable"
    )

    response = client.post(
        "/api/v1/text/generate",
        json=valid_generation_payload(),
    )

    assert response.status_code == 200
    assert response.json()["content"] == (
        "Generation should still succeed"
    )


def test_generate_text_creates_langfuse_trace(api_client):
    (
        client,
        mock_llm,
        _,
        observability,
        _,
    ) = api_client

    mock_llm.generate.return_value = TextGenerationResponse(
        request_id="provider-request-789",
        model="omni-primary",
        content="Hello from OmniAI!",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
    )

    response = client.post(
        "/api/v1/text/generate",
        json=valid_generation_payload(),
    )

    assert response.status_code == 200

    observability.trace_generation.assert_called_once()

    trace_args = observability.trace_generation.call_args.kwargs

    assert trace_args["request_type"] == "generate"
    assert trace_args["model"] == "omni-primary"
    assert trace_args["user_id"]

    observability.update_generation.assert_called_once()

    update_args = observability.update_generation.call_args.kwargs

    assert update_args["status"] == "success"
    assert update_args["tokens"]["input"] == 10
    assert update_args["tokens"]["output"] == 5
    assert update_args["tokens"]["total"] == 15
    assert update_args["actual_model"] == "omni-primary"
