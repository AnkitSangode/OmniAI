
from io import BytesIO

from PIL import Image, ImageDraw

from app.services.images.base import GeneratedImage, ImageProvider


class MockImageProvider(ImageProvider):

    async def generate(
        self,
        prompt: str,
        width: int,
        height: int,
    ) -> GeneratedImage:

        image = Image.new(
            "RGB",
            (width, height),
            color=(30, 41, 59),
        )

        draw = ImageDraw.Draw(image)

        draw.rectangle(
            (20, 20, width - 20, height - 20),
            outline=(56, 189, 248),
            width=3,
        )

        draw.text(
            (40, 40),
            "OmniAI - Mock Generated Image",
            fill=(255, 255, 255),
        )

        draw.text(
            (40, 80),
            prompt[:100],
            fill=(203, 213, 225),
        )

        buffer = BytesIO()
        image.save(buffer, format="PNG")

        return GeneratedImage(
            image_bytes=buffer.getvalue(),
            provider="mock",
            model="omniai-mock-v1",
        )
