
from functools import lru_cache

from app.core.config import get_settings
from app.services.audio.local_whisper_provider import LocalWhisperProvider


@lru_cache(maxsize=1)
def get_video_whisper_provider() -> LocalWhisperProvider:
    settings = get_settings()

    return LocalWhisperProvider(
        model_size=settings.LOCAL_WHISPER_MODEL,
        device=settings.LOCAL_WHISPER_DEVICE,
        compute_type=settings.LOCAL_WHISPER_COMPUTE_TYPE,
        cpu_threads=settings.LOCAL_WHISPER_CPU_THREADS,
    )
