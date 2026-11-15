
import logging
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app import main
from app.api.dependencies import get_current_user
from app.api.v1.endpoints.text import (
    get_observability_service,
    get_safety_service,
    get_usage_service,
)
from app.services.llm.litellm_client import (
    LiteLLMRequestError,
    LiteLLMTimeoutError,
)
from app.services.llm.schemas import TextGenerationResponse
from app.services.safety.schemas import (
    ModerationResult,
    SafetyServiceUnavailable,
    UnsafeContentError,
)

logger = logging.getLogger(__name__)


@pytest.fixture
def api_client(monkeypatch):
    """
    Provides an isolated API client with mocked:
    - LiteLLM client
    - Authenticated user
    - Usage service
    - Langfuse observability service
    - Safety service
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

    mock_safety = Mock()
    mock_safety.check_input = AsyncMock(
        return_value=ModerationResult(is_safe=True)
    )
    mock_safety.check_output = AsyncMock(
        return_value=ModerationResult(is_safe=True)
    )

    # Mock dependencies created by the application lifespan.
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

    main.app.dependency_overrides[get_safety_service] = (
        lambda: mock_safety
    )

    try:
        with TestClient(main.app) as client:
            yield (
                client,
                mock_llm,
                mock_usage_service,
                mock_observability,
                test_user,
                mock_safety,
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


def make_generation_response(
    content="Hello from OmniAI!",
    request_id="provider-request-123",
):
    return TextGenerationResponse(
        request_id=request_id,
        model="omni-primary",
        content=content,
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
    )


def test_generate_text_success(api_client):
    client, mock_llm, _, _, _, mock_safety = api_client

    mock_llm.generate.return_value = make_generation_response()

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

    mock_safety.check_input.assert_awaited_once_with("Hello")
    mock_safety.check_output.assert_awaited_once_with(
        "Hello from OmniAI!",
        context="Hello",
    )
    mock_llm.generate.assert_awaited_once()


def test_generate_text_unauthorized(api_client):
    client, _, _, _, _, _ = api_client

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
    client, mock_llm, _, _, _, mock_safety = api_client

    response = client.post(
        "/api/v1/text/generate",
        json={
            "messages": [],
        },
    )

    assert response.status_code == 422
    mock_llm.generate.assert_not_awaited()
    mock_safety.check_input.assert_not_awaited()


def test_generate_text_gateway_error(api_client):
    client, mock_llm, _, _, _, _ = api_client

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
    client, mock_llm, _, _, _, _ = api_client

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


def test_generate_text_moderates_user_input(api_client):
    client, mock_llm, _, _, _, mock_safety = api_client

    mock_llm.generate.return_value = make_generation_response()

    response = client.post(
        "/api/v1/text/generate",
        json=valid_generation_payload(),
    )

    assert response.status_code == 200

    mock_safety.check_input.assert_awaited_once_with("Hello")
    mock_safety.check_output.assert_awaited_once_with(
        "Hello from OmniAI!",
        context="Hello",
    )
    mock_llm.generate.assert_awaited_once()


def test_unsafe_input_never_reaches_llm(api_client):
    client, mock_llm, _, _, _, mock_safety = api_client

    mock_safety.check_input.side_effect = UnsafeContentError(
        ("S1",)
    )

    response = client.post(
        "/api/v1/text/generate",
        json=valid_generation_payload(),
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "unsafe_input"

    mock_llm.generate.assert_not_awaited()
    mock_safety.check_output.assert_not_awaited()


def test_unsafe_output_is_not_returned(api_client):
    client, mock_llm, usage_service, _, test_user, mock_safety = (
        api_client
    )

    mock_llm.generate.return_value = make_generation_response(
        content="Unsafe generated content",
    )

    mock_safety.check_output.side_effect = UnsafeContentError(
        ("S2",)
    )

    response = client.post(
        "/api/v1/text/generate",
        json=valid_generation_payload(),
    )

    assert response.status_code == 502
    assert "Unsafe generated content" not in response.text

    mock_llm.generate.assert_awaited_once()

    usage_service.record_request.assert_awaited_once()
    usage_args = usage_service.record_request.await_args.kwargs

    assert usage_args["user_id"] == test_user.id
    assert usage_args["status"] == "failed"
    assert usage_args["error_code"] == "unsafe_model_output"


def test_safety_provider_failure_blocks_generation(api_client):
    client, mock_llm, _, _, _, mock_safety = api_client

    mock_safety.check_input.side_effect = SafetyServiceUnavailable(
        "Provider unavailable"
    )

    response = client.post(
        "/api/v1/text/generate",
        json=valid_generation_payload(),
    )

    assert response.status_code == 503
    mock_llm.generate.assert_not_awaited()


def test_stream_text_success(api_client):
    client, _, _, _, _, mock_safety = api_client

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
    assert '"content": "Hello from OmniAI"' in body

    assert '"type": "usage"' in body
    assert '"prompt_tokens": 10' in body
    assert '"completion_tokens": 5' in body
    assert '"total_tokens": 15' in body

    assert '"type": "finish"' in body
    assert '"type": "done"' in body

    mock_safety.check_input.assert_awaited_once_with("Hello")
    mock_safety.check_output.assert_awaited_once_with(
        "Hello from OmniAI",
        context="Hello",
    )


def test_stream_text_buffers_content_until_moderated(api_client):
    client, _, _, _, _, mock_safety = api_client

    async def assert_output_is_safe(content, *, context=None):
        assert content == "Hello from OmniAI"
        assert context == "Hello"

    mock_safety.check_output.side_effect = assert_output_is_safe

    response = client.post(
        "/api/v1/text/stream",
        json=valid_generation_payload(),
    )

    assert response.status_code == 200
    assert '"content": "Hello from OmniAI"' in response.text

    # The original individual chunks must not be emitted.
    assert '"content": "Hello"' not in response.text
    assert '"content": " from OmniAI"' not in response.text


def test_stream_unsafe_input_never_reaches_llm(api_client):
    client, mock_llm, _, _, _, mock_safety = api_client

    mock_safety.check_input.side_effect = UnsafeContentError(
        ("S1",)
    )

    response = client.post(
        "/api/v1/text/stream",
        json=valid_generation_payload(),
    )

    assert response.status_code == 200
    assert '"code": "unsafe_input"' in response.text
    mock_llm.stream.assert_not_called()


def test_stream_unsafe_output_is_not_returned(api_client):
    client, _, _, _, _, mock_safety = api_client

    mock_safety.check_output.side_effect = UnsafeContentError(
        ("S2",)
    )

    response = client.post(
        "/api/v1/text/stream",
        json=valid_generation_payload(),
    )

    assert response.status_code == 200
    assert '"code": "unsafe_model_output"' in response.text
    assert "Hello from OmniAI" not in response.text


def test_stream_safety_provider_failure_blocks_output(api_client):
    client, _, _, _, _, mock_safety = api_client

    mock_safety.check_output.side_effect = SafetyServiceUnavailable(
        "Provider unavailable"
    )

    response = client.post(
        "/api/v1/text/stream",
        json=valid_generation_payload(),
    )

    assert response.status_code == 200
    assert '"code": "safety_unavailable"' in response.text
    assert "Hello from OmniAI" not in response.text


def test_stream_text_timeout(api_client):
    client, mock_llm, _, _, _, _ = api_client

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
    client, mock_llm, _, _, _, _ = api_client

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
    client, mock_llm, usage_service, _, test_user, _ = api_client

    mock_llm.generate.return_value = make_generation_response(
        request_id="provider-request-456",
        content="Usage tracking test",
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
    assert usage_args["prompt_tokens"] == 10
    assert usage_args["completion_tokens"] == 5
    assert usage_args["total_tokens"] == 15
    assert usage_args["status"] == "success"
    assert usage_args["provider_request_id"] == (
        "provider-request-456"
    )


def test_generate_text_records_failed_request(api_client):
    client, mock_llm, usage_service, _, test_user, _ = api_client

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
    client, _, usage_service, _, test_user, _ = api_client

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
    client, mock_llm, usage_service, _, _, _ = api_client

    mock_llm.generate.return_value = make_generation_response(
        request_id="provider-request-789",
        content="Generation should still succeed",
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
        _,
    ) = api_client

    mock_llm.generate.return_value = make_generation_response(
        request_id="provider-request-789",
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
    assert update_args["prompt_tokens"] == 10
    assert update_args["completion_tokens"] == 5
    assert update_args["total_tokens"] == 15
    assert update_args["actual_model"] == "omni-primary"
