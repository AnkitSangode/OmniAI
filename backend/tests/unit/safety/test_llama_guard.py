from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.safety.llama_guard import LlamaGuardModerator
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def moderator():
    return LlamaGuardModerator(
        base_url="http://localhost:8001/v1",
        model="meta-llama/Llama-Guard-3-1B",
    )


@pytest.mark.asyncio
async def test_safe_classification(moderator):
    mock_response = {
        "choices": [
            {
                "message": {
                    "content": "safe"
                }
            }
        ]
    }

    with patch(
        "app.services.safety.llama_guard.httpx.AsyncClient"
    ) as client_class:
        client = client_class.return_value
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        response = MagicMock()
        response.json.return_value = mock_response
        response.raise_for_status.return_value = None
        client.post = AsyncMock(return_value=response)

        result = await moderator.moderate(
            "Hello",
            role="user",
        )

    assert result.is_safe is True


@pytest.mark.asyncio
async def test_unsafe_classification_with_categories(moderator):
    mock_response = {
        "choices": [
            {
                "message": {
                    "content": "unsafe\nS1"
                }
            }
        ]
    }

    with patch(
        "app.services.safety.llama_guard.httpx.AsyncClient"
    ) as client_class:
        client = client_class.return_value
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        response = MagicMock()
        response.json.return_value = mock_response
        response.raise_for_status.return_value = None
        client.post = AsyncMock(return_value=response)

        result = await moderator.moderate(
            "Test content",
            role="assistant",
        )

    assert result.is_safe is False
    assert result.categories == ("S1",)


@pytest.mark.asyncio
async def test_invalid_classification_is_rejected(moderator):
    mock_response = {
        "choices": [
            {
                "message": {
                    "content": "I think this is safe"
                }
            }
        ]
    }

    with patch(
        "app.services.safety.llama_guard.httpx.AsyncClient"
    ) as client_class:
        client = client_class.return_value
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        response = MagicMock()
        response.json.return_value = mock_response
        response.raise_for_status.return_value = None
        client.post = AsyncMock(return_value=response)
        

        with pytest.raises(ValueError):
            await moderator.moderate(
                "Test content",
                role="user",
            )


@pytest.mark.asyncio
async def test_invalid_role_is_rejected(moderator):
    with pytest.raises(ValueError):
        await moderator.moderate(
            "Test content",
            role="system",
        )


@pytest.mark.asyncio
async def test_http_failure_is_propagated(moderator):
    with patch(
        "app.services.safety.llama_guard.httpx.AsyncClient"
    ) as client_class:
        client = client_class.return_value
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        client.post = AsyncMock(
            side_effect=httpx.ConnectError("Connection failed")
        )

        with pytest.raises(httpx.ConnectError):
            await moderator.moderate(
                "Hello",
                role="user",
            )