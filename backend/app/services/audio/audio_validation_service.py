
import asyncio
import json
import shutil
import tempfile
from pathlib import Path


class AudioValidationService:
    """Validates uploaded audio using FFprobe."""

    ALLOWED_FORMATS = {
        "wav": {"wav"},
        "mp3": {"mp3"},
        "m4a": {"mov", "mp4", "m4a", "3gp", "3g2", "mj2"},
        "ogg": {"ogg"},
        "webm": {"matroska", "webm"},
    }

    def __init__(
        self,
        ffprobe_path: str | None = None,
        timeout_seconds: float = 10.0,
    ):
        self.ffprobe_path = (
            ffprobe_path or shutil.which("ffprobe")
        )

        if not self.ffprobe_path:
            raise RuntimeError(
                "FFprobe executable was not found."
            )

        self.timeout_seconds = timeout_seconds

    async def validate(
        self,
        audio_bytes: bytes,
        extension: str,
    ) -> None:
        if not audio_bytes:
            raise ValueError("Audio file cannot be empty.")

        safe_extension = extension.lower().lstrip(".")

        if safe_extension not in self.ALLOWED_FORMATS:
            raise ValueError("Unsupported audio extension.")

        temp_path: Path | None = None
        process: asyncio.subprocess.Process | None = None

        try:
            with tempfile.NamedTemporaryFile(
                suffix=f".{safe_extension}",
                delete=False,
            ) as temp_file:
                temp_file.write(audio_bytes)
                temp_path = Path(temp_file.name)

            process = await asyncio.create_subprocess_exec(
                self.ffprobe_path,
                "-v", "error",
                "-show_entries", "format=format_name",
                "-show_entries", "stream=codec_type",
                "-of", "json",
                str(temp_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, _ = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.timeout_seconds,
                )
            except TimeoutError as exc:
                process.kill()
                await process.wait()
                raise ValueError(
                    "Audio validation timed out."
                ) from exc

            if process.returncode != 0:
                raise ValueError(
                    "Uploaded file is not a valid audio file."
                )

            try:
                metadata = json.loads(stdout)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise ValueError(
                    "Could not inspect uploaded audio."
                ) from exc

            audio_streams = [
                stream
                for stream in metadata.get("streams", [])
                if stream.get("codec_type") == "audio"
            ]

            if not audio_streams:
                raise ValueError(
                    "Uploaded file does not contain an audio stream."
                )

            detected_formats = set(
                metadata.get("format", {})
                .get("format_name", "")
                .split(",")
            )

            expected_formats = self.ALLOWED_FORMATS[
                safe_extension
            ]

            if not detected_formats.intersection(expected_formats):
                raise ValueError(
                    "File content does not match its extension."
                )

        except FileNotFoundError as exc:
            raise RuntimeError(
                "FFprobe executable could not be started."
            ) from exc

        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
