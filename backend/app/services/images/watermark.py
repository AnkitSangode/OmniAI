from io import BytesIO

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError


class ImageWatermarkService:
    """Adds a visible AI-generated attribution to an image.

    The output is normalized to PNG so the watermark's alpha channel is
    preserved consistently across generated image providers.
    """

    LABEL = "AI-GENERATED | OmniAI"

    def apply(self, image_bytes: bytes) -> bytes:
        if not image_bytes:
            raise ValueError("Cannot watermark an empty image.")

        try:
            with Image.open(BytesIO(image_bytes)) as source:
                image = source.convert("RGBA")
        except (UnidentifiedImageError, OSError) as exc:
            raise ValueError("Generated image is not a valid image file.") from exc

        width, height = image.size
        if width < 1 or height < 1:
            raise ValueError("Generated image has invalid dimensions.")

        band_height = min(36, max(24, height // 12))
        padding = max(8, min(16, width // 64))

        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        font = ImageFont.load_default()

        top = max(0, height - band_height)
        draw.rectangle(
            (0, top, width, height),
            fill=(0, 0, 0, 150),
        )

        text_bbox = draw.textbbox((0, 0), self.LABEL, font=font)
        text_height = text_bbox[3] - text_bbox[1]
        text_y = top + max(0, (band_height - text_height) // 2) - text_bbox[1]

        draw.text(
            (padding, text_y),
            self.LABEL,
            font=font,
            fill=(255, 255, 255, 255),
        )

        watermarked = Image.alpha_composite(image, overlay)

        output = BytesIO()
        watermarked.save(output, format="PNG")
        return output.getvalue()
