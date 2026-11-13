
from uuid import uuid4

from app.services.observability.langfuse_service import (
    get_langfuse_service,
)


def main():
    service = get_langfuse_service()

    if not service.enabled:
        raise RuntimeError(
            "Langfuse is disabled. Check LANGFUSE_PUBLIC_KEY "
            "and LANGFUSE_SECRET_KEY in backend/.env."
        )

    request_id = str(uuid4())

    print("Sending test trace to Langfuse...")

    try:
        with service.trace_generation(
            request_id=request_id,
            user_id="omniai-connectivity-test",
            request_type="connectivity_test",
            model="omniai-test-model",
        ) as generation:

            service.update_generation(
                generation=generation,
                status="success",
                request_type="connectivity_test",
                prompt_tokens=10,
                completion_tokens=20,
                total_tokens=30,
                actual_model="omniai-test-model",
                estimated_cost=None,
            )

        print("Test trace submitted.")
        print(f"Request ID: {request_id}")
        print("Check your Langfuse dashboard.")

    finally:
        service.shutdown()


if __name__ == "__main__":
    main()
