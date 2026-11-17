
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "OmniAI"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str

    # Authentication
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Usage and cost tracking
    LLM_MODEL_PRICING: dict[str, dict[str, float]] = {}

    # Image storage
    IMAGE_STORAGE_DIR: str = "storage/images"
    HF_TOKEN: str | None = None
    IMAGE_MODEL_ID: str = "black-forest-labs/FLUX.1-schnell"
    IMAGE_PROVIDER: str = "auto"
    IMAGE_INFERENCE_TIMEOUT_SECONDS: int = 180
    IMAGE_BACKEND: str = "mock"

    # ComfyUI image generation
    COMFYUI_BASE_URL: str | None = None
    COMFYUI_API_KEY: str | None = None
    COMFYUI_WORKFLOW_PATH: str = "workflows/comfyui_text_to_image_api.json"
    COMFYUI_TIMEOUT_SECONDS: int = 600
    COMFYUI_POLL_INTERVAL_SECONDS: float = 2.0

    # Audio storage and providers
    AUDIO_STORAGE_DIR: str = "storage/audio"
    AUDIO_BACKEND: str = "real"

    WHISPER_PROVIDER: str = "huggingface"
    WHISPER_MODEL_ID: str = "openai/whisper-large-v3"

    # Text-to-Speech
    TTS_PROVIDER: str = "kokoro"
    TTS_MODEL_ID: str = "hexgrad/Kokoro-82M"
    TTS_LANGUAGE: str = "en-us"
    TTS_VOICE: str = "af_heart"
    TTS_SPEED: float = 1.0
    TTS_DEVICE: str = "cpu"
    TTS_TIMEOUT_SECONDS: int = 600

    AUDIO_INFERENCE_TIMEOUT_SECONDS: int = 180

    # Video processing
    VIDEO_STORAGE_DIR: str = "storage/videos"
    FFMPEG_TIMEOUT_SECONDS: int = 300
    MAX_VIDEO_DURATION_SECONDS: int = 1800


    LOCAL_WHISPER_MODEL: str = "base"
    LOCAL_WHISPER_DEVICE: str = "cpu"
    LOCAL_WHISPER_COMPUTE_TYPE: str = "int8"
    LOCAL_WHISPER_CPU_THREADS: int = 4

    # Image infrastructure pricing
    IMAGE_GPU_HOURLY_RATE_USD: float | None = None
    

    # AI Safety / Llama Guard
    SAFETY_ENABLED: bool = False
    SAFETY_PROVIDER: str = "llama_guard"
    SAFETY_BASE_URL: str = "http://localhost:8001/v1"
    SAFETY_API_KEY: str | None = None
    SAFETY_MODEL: str = "meta-llama/Llama-Guard-3-1B"
    SAFETY_TIMEOUT_SECONDS: int = 30

    # Langfuse Observability
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: str | None = None
    LANGFUSE_BASE_URL: str = "https://cloud.langfuse.com"

    # Frontend
    FRONTEND_URL: str = "http://localhost:3000"

    # LiteLLM Gateway
    LITELLM_BASE_URL: str = "http://localhost:4000/v1"
    LITELLM_API_KEY: str
    LITELLM_DEFAULT_MODEL: str = "omni-primary"
    LITELLM_TIMEOUT_SECONDS: int = 60

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
