
import logging
from contextlib import ExitStack, contextmanager
from decimal import Decimal
from functools import lru_cache
from typing import Any, Iterator

from langfuse import Langfuse, propagate_attributes

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class LangfuseService:
    def __init__(self) -> None:
        settings = get_settings()

        self.client: Langfuse | None = None

        if not (
            settings.LANGFUSE_PUBLIC_KEY
            and settings.LANGFUSE_SECRET_KEY
        ):
            logger.info(
                "Langfuse is disabled: credentials are not configured."
            )
            return

        try:
            self.client = Langfuse(
                public_key=settings.LANGFUSE_PUBLIC_KEY,
                secret_key=settings.LANGFUSE_SECRET_KEY,
                base_url=settings.LANGFUSE_BASE_URL,
                environment=settings.ENVIRONMENT,
            )

            logger.info("Langfuse observability initialized.")

        except Exception:
            logger.exception(
                "Could not initialize Langfuse. "
                "Observability will remain disabled."
            )

    @property
    def enabled(self) -> bool:
        return self.client is not None

    @contextmanager
    def trace_generation(
        self,
        *,
        user_id: str,
        request_id: str,
        request_type: str,
        model: str,
    ) -> Iterator[Any]:
        """
        Create a root request span and nested LLM generation.

        No prompt or response content is captured.
        """
        if self.client is None:
            yield None
            return

        with ExitStack() as stack:
            stack.enter_context(
                self.client.start_as_current_observation(
                    as_type="span",
                    name=f"text-{request_type}-request",
                    metadata={
                        "request_id": request_id,
                        "request_type": request_type,
                    },
                )
            )

            stack.enter_context(
                propagate_attributes(
                    user_id=user_id,
                    tags=["omniai", "text", request_type],
                    metadata={
                        "request_id": request_id,
                    },
                )
            )

            generation = stack.enter_context(
                self.client.start_as_current_observation(
                    as_type="generation",
                    name="litellm-chat-completion",
                    model=model,
                    metadata={
                        "request_type": request_type,
                    },
                )
            )

            yield generation

    def update_generation(
        self,
        generation: Any,
        *,
        status: str,
        request_type: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        actual_model: str | None = None,
        estimated_cost: Decimal | None = None,
        error_code: str | None = None,
    ) -> None:
        if generation is None:
            return

        metadata = {
            "request_type": request_type,
            "status": status,
        }

        if actual_model:
            metadata["actual_model"] = actual_model

        update: dict[str, Any] = {
            "output": {
                "status": status,
            },
            "metadata": metadata,
        }

        if total_tokens > 0:
            update["usage_details"] = {
                "input": prompt_tokens,
                "output": completion_tokens,
                "total": total_tokens,
            }

        if estimated_cost is not None:
            update["cost_details"] = {
                "total": float(estimated_cost),
            }

        if status != "success":
            update["level"] = (
                "WARNING" if status == "cancelled" else "ERROR"
            )
            update["status_message"] = error_code or status

        try:
            generation.update(**update)

        except Exception:
            logger.exception(
                "Could not update Langfuse generation."
            )

    def shutdown(self) -> None:
        if self.client is None:
            return

        try:
            self.client.shutdown()
            logger.info("Langfuse client shut down.")

        except Exception:
            logger.exception("Langfuse shutdown failed.")


@lru_cache
def get_langfuse_service() -> LangfuseService:
    return LangfuseService()
