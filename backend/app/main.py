from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.auth import router as auth_router
from app.api.v1.endpoints.text import router as text_router
from app.api.v1.endpoints.prompts import router as prompts_router

from app.core.config import get_settings
from app.services.llm.litellm_client import LiteLLMClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # Initialize one shared LiteLLM HTTP client.
    app.state.litellm_client = LiteLLMClient(settings)

    yield

    # Close the HTTP connection pool during shutdown.
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
