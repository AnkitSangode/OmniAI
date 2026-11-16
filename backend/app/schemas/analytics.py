from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict


AnalyticsModality = Literal["text", "image", "audio", "video", "other"]


class AnalyticsSummary(BaseModel):
    total_requests: int
    successful_requests: int
    failed_requests: int
    success_rate: float
    total_tokens: int
    estimated_cost_usd: float | None
    requests_without_cost: int
    average_latency_ms: float


class ModalityBreakdown(BaseModel):
    modality: AnalyticsModality
    requests: int
    successful_requests: int
    failed_requests: int
    total_tokens: int
    estimated_cost_usd: float | None
    average_latency_ms: float


class ModelBreakdown(BaseModel):
    model: str
    requests: int
    total_tokens: int
    estimated_cost_usd: float | None
    average_latency_ms: float


class DailyUsage(BaseModel):
    day: date
    requests: int
    total_tokens: int
    estimated_cost_usd: float | None


class AnalyticsOverviewResponse(BaseModel):
    start_date: date
    end_date: date
    summary: AnalyticsSummary
    by_modality: list[ModalityBreakdown]
    by_model: list[ModelBreakdown]
    daily: list[DailyUsage]

    model_config = ConfigDict(from_attributes=True)
