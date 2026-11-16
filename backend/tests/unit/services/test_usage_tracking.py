from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.usage_tracking import record_usage_safely


@pytest.mark.asyncio
async def test_record_usage_safely_records_request():
    usage_service = MagicMock()
    usage_service.record_request = AsyncMock()
    user_id = uuid4()

    await record_usage_safely(
        usage_service,
        user_id=user_id,
        request_id="request-123",
        request_type="audio",
        model="whisper/large-v3",
        latency_ms=120,
        status="success",
    )

    usage_service.record_request.assert_awaited_once()
    kwargs = usage_service.record_request.await_args.kwargs
    assert kwargs["user_id"] == user_id
    assert kwargs["request_id"] == "request-123"
    assert kwargs["request_type"] == "audio"
    assert kwargs["model"] == "whisper/large-v3"
    assert kwargs["latency_ms"] == 120
    assert kwargs["status"] == "success"


@pytest.mark.asyncio
async def test_record_usage_safely_is_noop_without_usage_service():
    await record_usage_safely(
        None,
        user_id=uuid4(),
        request_type="image",
        model="provider/model",
        latency_ms=20,
        status="success",
    )


@pytest.mark.asyncio
async def test_record_usage_safely_swallows_telemetry_failure():
    usage_service = MagicMock()
    usage_service.record_request = AsyncMock(side_effect=RuntimeError("database down"))

    # Telemetry is best-effort and must not break the primary AI operation.
    await record_usage_safely(
        usage_service,
        user_id=uuid4(),
        request_id="request-456",
        request_type="video",
        model="ffmpeg/video-processing",
        latency_ms=-5,
        status="failed",
        error_code="RuntimeError",
    )

    kwargs = usage_service.record_request.await_args.kwargs
    assert kwargs["latency_ms"] == 0
    assert kwargs["error_code"] == "RuntimeError"
