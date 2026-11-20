from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx

from app.api.v1.auth import router as auth_router
from app.api.v1.endpoints.analytics import router as analytics_router
from app.api.v1.endpoints import audio
from app.api.v1.endpoints.images import router as images_router
from app.api.v1.endpoints.prompts import router as prompts_router
from app.api.v1.endpoints.text import router as text_router
from app.api.v1.endpoints import video
from app.core.config import get_settings
from app.services.llm.litellm_client import LiteLLMClient
from app.services.safety.llama_guard import LlamaGuardModerator
from app.services.safety.safety_service import SafetyService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # Initialize one shared LiteLLM HTTP client.
    app.state.litellm_client = LiteLLMClient(settings)

    # Share one HTTP connection pool and moderator across all safety-enabled
    # endpoints (text, image prompts, and audio). The pool is owned by lifespan.
    app.state.safety_http_client = None
    app.state.safety_service = None

    if settings.SAFETY_ENABLED:
        if settings.SAFETY_PROVIDER != "llama_guard":
            await app.state.litellm_client.close()
            raise RuntimeError(
                f"Unsupported safety provider: {settings.SAFETY_PROVIDER}"
            )

        app.state.safety_http_client = httpx.AsyncClient(
            timeout=settings.SAFETY_TIMEOUT_SECONDS,
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
                keepalive_expiry=30.0,
            ),
        )
        moderator = LlamaGuardModerator(
            base_url=settings.SAFETY_BASE_URL,
            model=settings.SAFETY_MODEL,
            api_key=settings.SAFETY_API_KEY,
            timeout_seconds=settings.SAFETY_TIMEOUT_SECONDS,
            http_client=app.state.safety_http_client,
        )
        app.state.safety_service = SafetyService(moderator=moderator)

    try:
        yield
    finally:
        # Close shared clients after all requests have completed.
        if app.state.safety_http_client is not None:
            await app.state.safety_http_client.aclose()
        await app.state.litellm_client.close()


app = FastAPI(
    title="OmniAI API",
    description="Unified Multimodal AI Platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(
    auth_router,
    prefix="/api/v1",
)

app.include_router(
    text_router,
    prefix="/api/v1",
)

app.include_router(prompts_router, prefix="/api/v1")

app.include_router(analytics_router, prefix="/api/v1")

app.include_router(images_router, prefix="/api/v1")

app.include_router(audio.router, prefix="/api/v1")

app.include_router(video.router, prefix="/api/v1")
