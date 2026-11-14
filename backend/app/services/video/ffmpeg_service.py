
import asyncio
import json
import logging
import shutil
import subprocess

from fractions import Fraction
from pathlib import Path
from typing import Any

from app.core.config import get_settings


logger = logging.getLogger(__name__)

settings = get_settings()


class FFmpegError(Exception):
    """Raised when an FFmpeg or FFprobe operation fails."""


class FFmpegService:
    """
    Handles video metadata extraction and audio extraction using
    FFmpeg and FFprobe.

    Subprocess execution runs in a worker thread to support
    Windows and Linux asyncio event loops.
    """

    def __init__(self) -> None:
        self.ffmpeg_path = shutil.which("ffmpeg")
        self.ffprobe_path = shutil.which("ffprobe")

        if not self.ffmpeg_path:
            raise FFmpegError(
                "FFmpeg executable was not found. "
                "Make sure FFmpeg is installed and added to PATH."
            )

        if not self.ffprobe_path:
            raise FFmpegError(
                "FFprobe executable was not found. "
                "Make sure FFmpeg is installed and added to PATH."
            )

    async def extract_metadata(
        self,
        video_path: str | Path,
    ) -> dict[str, Any]:
        """
        Extract video metadata using FFprobe.

        Returns:
            duration_seconds
            width
            height
            frame_rate
            video_codec
            audio_codec
            format_name
            has_audio
        """

        video_path = Path(video_path)

        if not video_path.exists():
            raise FFmpegError(
                f"Video file does not exist: {video_path}"
            )

        command = [
            self.ffprobe_path,
            "-v",
            "error",
            "-show_entries",
            (
                "format=duration,format_name:"
                "stream=codec_type,codec_name,width,height,r_frame_rate"
            ),
            "-of",
            "json",
            str(video_path),
        ]

        stdout, _ = await self._run_command(command)

        try:
            probe_data = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise FFmpegError(
                "FFprobe returned invalid JSON metadata."
            ) from exc

        streams = probe_data.get("streams", [])
        format_data = probe_data.get("format", {})

        video_stream = next(
            (
                stream
                for stream in streams
                if stream.get("codec_type") == "video"
            ),
            None,
        )

        audio_stream = next(
            (
                stream
                for stream in streams
                if stream.get("codec_type") == "audio"
            ),
            None,
        )

        if video_stream is None:
            raise FFmpegError(
                "The uploaded file does not contain a video stream."
            )

        try:
            duration_seconds = float(
                format_data.get("duration", 0)
            )
        except (TypeError, ValueError) as exc:
            raise FFmpegError(
                "Unable to determine video duration."
            ) from exc

        if duration_seconds <= 0:
            raise FFmpegError(
                "The video has an invalid or zero duration."
            )

        max_duration = settings.MAX_VIDEO_DURATION_SECONDS

        if duration_seconds > max_duration:
            raise FFmpegError(
                f"Video duration exceeds the maximum allowed "
                f"duration of {max_duration} seconds."
            )

        frame_rate = self._parse_frame_rate(
            video_stream.get("r_frame_rate")
        )

        metadata = {
            "duration_seconds": duration_seconds,
            "width": video_stream.get("width"),
            "height": video_stream.get("height"),
            "frame_rate": frame_rate,
            "video_codec": video_stream.get("codec_name"),
            "audio_codec": (
                audio_stream.get("codec_name")
                if audio_stream
                else None
            ),
            "format_name": format_data.get("format_name"),
            "has_audio": audio_stream is not None,
        }

        logger.info(
            "Video metadata extracted successfully: "
            "duration=%s, resolution=%sx%s, has_audio=%s",
            metadata["duration_seconds"],
            metadata["width"],
            metadata["height"],
            metadata["has_audio"],
        )

        return metadata

    async def extract_audio(
        self,
        video_path: str | Path,
        output_path: str | Path,
    ) -> Path:
        """
        Extract audio from a video and convert it to:

        - WAV format
        - Mono channel
        - 16 kHz sample rate
        - PCM signed 16-bit audio

        This format is suitable for Whisper transcription.
        """

        video_path = Path(video_path)
        output_path = Path(output_path)

        if not video_path.exists():
            raise FFmpegError(
                f"Video file does not exist: {video_path}"
            )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        command = [
            self.ffmpeg_path,
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]

        await self._run_command(command)

        if not output_path.exists():
            raise FFmpegError(
                "FFmpeg completed without creating the extracted audio file."
            )

        if output_path.stat().st_size == 0:
            raise FFmpegError(
                "The extracted audio file is empty."
            )

        logger.info(
            "Audio extracted successfully: %s",
            output_path,
        )

        return output_path

    @staticmethod
    def _parse_frame_rate(
        frame_rate: str | None,
    ) -> float | None:
        """Convert FFprobe frame-rate notation into a float."""

        if not frame_rate or frame_rate in {"0/0", "N/A"}:
            return None

        try:
            return float(Fraction(frame_rate))
        except (ValueError, ZeroDivisionError):
            logger.warning(
                "Unable to parse frame rate: %s",
                frame_rate,
            )
            return None

    async def _run_command(
        self,
        command: list[str],
    ) -> tuple[str, str]:
        """
        Execute an external command without blocking
        the FastAPI asyncio event loop.

        subprocess.run executes inside a worker thread,
        avoiding Windows asyncio subprocess limitations.
        """

        try:
            process = await asyncio.to_thread(
                subprocess.run,
                command,
                capture_output=True,
                text=True,
                timeout=settings.FFMPEG_TIMEOUT_SECONDS,
                check=False,
            )

        except subprocess.TimeoutExpired as exc:
            raise FFmpegError(
                "FFmpeg/FFprobe command timed out after "
                f"{settings.FFMPEG_TIMEOUT_SECONDS} seconds."
            ) from exc

        except FileNotFoundError as exc:
            raise FFmpegError(
                "FFmpeg or FFprobe executable could not be found."
            ) from exc

        except OSError as exc:
            raise FFmpegError(
                f"Unable to execute FFmpeg/FFprobe: {exc}"
            ) from exc

        if process.returncode != 0:
            error_details = (
                process.stderr[-2000:]
                if process.stderr
                else "No error details available."
            )

            logger.error(
                "External command failed with exit code %s: %s",
                process.returncode,
                error_details,
            )

            raise FFmpegError(
                f"FFmpeg/FFprobe command failed: {error_details}"
            )

        return process.stdout, process.stderr
