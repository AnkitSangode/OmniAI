
from io import BytesIO

from huggingface_hub import AsyncInferenceClient

from app.core.config import get_settings
from app.services.images.base import GeneratedImage, ImageProvider


class HuggingFaceImageProvider(ImageProvider):

    def __init__(self):
        settings = get_settings()

        if not settings.HF_TOKEN:
            raise ValueError(
                "HF_TOKEN is required for Hugging Face image generation."
            )

        self.model_id = settings.IMAGE_MODEL_ID
        self.provider_name = "huggingface"

        self.client = AsyncInferenceClient(
            provider=settings.IMAGE_PROVIDER,
            api_key=settings.HF_TOKEN,
            timeout=settings.IMAGE_INFERENCE_TIMEOUT_SECONDS,
        )

    async def generate(
        self,
        prompt: str,
        width: int,
        height: int,
    ) -> GeneratedImage:

        image = await self.client.text_to_image(
            prompt=prompt,
            model=self.model_id,
            width=width,
            height=height,
        )

        buffer = BytesIO()
        image.save(buffer, format="PNG")

        return GeneratedImage(
            image_bytes=buffer.getvalue(),
            provider=self.provider_name,
            model=self.model_id,
        )
