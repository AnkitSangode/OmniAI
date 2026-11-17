from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from datetime import datetime, timezone

import pytest
from decimal import Decimal

from app.services.images.image_service import ImageService

from app.schemas.image import ImageGenerationRequest
from app.services.images import image_service as module
from app.services.images.image_safety import ImageSafetyResult, ImageSafetyStatus


class FakeRepository:
    def __init__(self, db):
        self.db = db
        self.items = {}

    async def create(self, item):
        # Simulate the database server default for created_at.
        # The real DB populates this during INSERT/flush; this fake repository must too.
        if item.created_at is None:
            item.created_at = datetime.now(timezone.utc)
        self.items[item.id] = item

    async def get_by_id(self, item_id, user_id):
        item = self.items.get(item_id)
        return item if item and item.user_id == user_id else None


class FakeProvider:
    async def generate(self, **kwargs):
        return SimpleNamespace(image_bytes=b"image-bytes", provider="mock-provider", model="image-v1")


class FakeStorage:
    async def save(self, image_bytes, generation_id):
        return "generated.png"


class FakeSafety:
    async def check(self, image_bytes):
        return ImageSafetyResult(status=ImageSafetyStatus.NOT_CHECKED)


class FakeWatermark:
    def apply(self, image_bytes):
        return image_bytes


@pytest.mark.asyncio
async def test_image_generation_records_usage(monkeypatch):
    monkeypatch.setattr(module, "ImageRepository", FakeRepository)
    db = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
    usage = MagicMock()
    usage.record_request = AsyncMock()

    service = module.ImageService(
        db, FakeProvider(), FakeStorage(), FakeWatermark(), FakeSafety(), usage
    )
    user_id = uuid4()
    request = ImageGenerationRequest(prompt="A red bicycle", width=512, height=512)

    response = await service.generate(request, user_id)

    assert response.status == "completed"
    assert response.moderation_status == "not_checked"
    usage.record_request.assert_awaited_once()
    recorded = usage.record_request.await_args.kwargs
    assert recorded["request_type"] == "image"
    assert recorded["request_id"] == str(response.id)
    assert recorded["model"] == "mock-provider/image-v1"
    assert recorded["status"] == "success"




def test_calculate_image_cost_with_configured_rate(monkeypatch):
    settings = SimpleNamespace(IMAGE_GPU_HOURLY_RATE_USD=0.50)
    monkeypatch.setattr(module, "get_settings", lambda: settings)

    result = ImageService._calculate_image_cost(60.0)

    assert result == Decimal("0.008333333333333333333333333333")


def test_calculate_image_cost_without_configured_rate(monkeypatch):
    settings = SimpleNamespace(IMAGE_GPU_HOURLY_RATE_USD=None)
    monkeypatch.setattr(module, "get_settings", lambda: settings)

    result = ImageService._calculate_image_cost(60.0)

    assert result is None


def test_calculate_image_cost_without_provider_timing(monkeypatch):
    settings = SimpleNamespace(IMAGE_GPU_HOURLY_RATE_USD=0.50)
    monkeypatch.setattr(module, "get_settings", lambda: settings)

    result = ImageService._calculate_image_cost(None)

    assert result is None
