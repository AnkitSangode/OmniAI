
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Application-generated ID for correlating a request.
    request_id: Mapped[str] = mapped_column(
        String(36),
        unique=True,
        nullable=False,
    )

    # LiteLLM/provider-generated request ID, when available.
    provider_request_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    request_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    model: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    prompt_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    completion_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    total_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # Estimated cost in USD. NULL means pricing is not configured.
    estimated_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 10),
        nullable=True,
    )

    latency_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    error_code: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "ix_usage_records_user_created",
            "user_id",
            "created_at",
        ),
        Index(
            "ix_usage_records_status",
            "status",
        ),
        Index(
            "ix_usage_records_model",
            "model",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"UsageRecord(request_id={self.request_id}, "
            f"user_id={self.user_id}, status={self.status})"
        )
