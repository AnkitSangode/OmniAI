
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

    # Audio storage and providers
    AUDIO_STORAGE_DIR: str = "storage/audio"
    AUDIO_BACKEND: str = "real"

    WHISPER_PROVIDER: str = "huggingface"
    WHISPER_MODEL_ID: str = "openai/whisper-large-v3"
    HF_TOKEN: str | None = None

    TTS_PROVIDER: str = "replicate"
    TTS_MODEL_ID: str = "lucataco/xtts-v2"
    REPLICATE_API_TOKEN: str | None = None
    TTS_SPEAKER_URL: str = (
    "https://replicate.delivery/pbxt/Jt79w0xsT64R1JsiJ0LQRL8UcWspg5J4RFrU6YwEKpOT1ukS/male.wav"
    )
    TTS_LANGUAGE: str = "en"
    TTS_CLEANUP_VOICE: bool = False

    AUDIO_INFERENCE_TIMEOUT_SECONDS: int = 180

    # Video processing
    VIDEO_STORAGE_DIR: str = "storage/videos"
    FFMPEG_TIMEOUT_SECONDS: int = 300
    MAX_VIDEO_DURATION_SECONDS: int = 1800
    VIDEO_STORAGE_DIR: str = "storage/videos"


    LOCAL_WHISPER_MODEL: str = "base"
    LOCAL_WHISPER_DEVICE: str = "cpu"
    LOCAL_WHISPER_COMPUTE_TYPE: str = "int8"
    LOCAL_WHISPER_CPU_THREADS: int = 4

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
