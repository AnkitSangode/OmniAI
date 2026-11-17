
from __future__ import annotations

import asyncio
import copy
import json
import uuid
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.images.base import GeneratedImage, ImageProvider


class ComfyUIImageProvider(ImageProvider):
    """Submit an API-format ComfyUI workflow and retrieve its saved image."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.COMFYUI_BASE_URL:
            raise ValueError("COMFYUI_BASE_URL is required for ComfyUI image generation.")

        self.base_url = settings.COMFYUI_BASE_URL.rstrip("/")
        self.api_key = settings.COMFYUI_API_KEY
        self.timeout = settings.COMFYUI_TIMEOUT_SECONDS
        self.poll_interval = settings.COMFYUI_POLL_INTERVAL_SECONDS
        self.workflow_path = Path(settings.COMFYUI_WORKFLOW_PATH)

        if not self.workflow_path.is_absolute():
            self.workflow_path = Path.cwd() / self.workflow_path

        if not self.workflow_path.is_file():
            raise FileNotFoundError(
                f"ComfyUI workflow file not found: {self.workflow_path}"
            )

        with self.workflow_path.open("r", encoding="utf-8") as file:
            self.workflow: dict[str, Any] = json.load(file)

        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout),
            headers=self._headers(),
        )

    def _headers(self) -> dict[str, str]:
        if self.api_key:
            return {"Authorization": f"Bearer {self.api_key}"}
        return {}

    @staticmethod
    def _find_node(
        workflow: dict[str, Any],
        *,
        class_type: str,
        title: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        matches = [
            (node_id, node)
            for node_id, node in workflow.items()
            if node.get("class_type") == class_type
            and (title is None or node.get("_meta", {}).get("title") == title)
        ]

        if len(matches) != 1:
            raise ValueError(
                f"Expected exactly one {class_type} node"
                f"{f' titled {title!r}' if title else ''}; found {len(matches)}."
            )

        return matches[0]

    @staticmethod
    def _validate_dimensions(width: int, height: int) -> None:
        for name, value in (("width", width), ("height", height)):
            if not 64 <= value <= 2048:
                raise ValueError(f"{name} must be between 64 and 2048.")

            if value % 8 != 0:
                raise ValueError(f"{name} must be divisible by 8.")

    def _build_prompt(
        self,
        prompt: str,
        width: int,
        height: int,
    ) -> dict[str, Any]:
        self._validate_dimensions(width, height)
        workflow = copy.deepcopy(self.workflow)

        _, prompt_node = self._find_node(
            workflow,
            class_type="PrimitiveStringMultiline",
            title="Text String (User Prompt)",
        )
        prompt_node["inputs"]["value"] = prompt

        _, latent_node = self._find_node(
            workflow,
            class_type="EmptyLatentImage",
        )
        latent_node["inputs"]["width"] = width
        latent_node["inputs"]["height"] = height

        self._find_node(workflow, class_type="SaveImage")

        return workflow

    async def generate(
        self,
        prompt: str,
        width: int,
        height: int,
    ) -> GeneratedImage:
        workflow = self._build_prompt(prompt, width, height)
        client_id = str(uuid.uuid4())

        # Measure the provider operation, not the rest of ImageService.
        provider_started_at = perf_counter()

        response = await self.client.post(
            "/prompt",
            json={"prompt": workflow, "client_id": client_id},
        )
        response.raise_for_status()

        submitted = response.json()
        prompt_id = submitted.get("prompt_id")

        if not prompt_id:
            raise RuntimeError(f"ComfyUI did not return prompt_id: {submitted}")

        history = await self._wait_for_history(prompt_id)
        output = self._extract_saved_image(history)

        image_response = await self.client.get(
            "/view",
            params={
                "filename": output["filename"],
                "subfolder": output.get("subfolder", ""),
                "type": output.get("type", "output"),
            },
        )
        image_response.raise_for_status()

        provider_elapsed_seconds = perf_counter() - provider_started_at

        return GeneratedImage(
            image_bytes=image_response.content,
            provider="comfyui",
            model="workflow",
            provider_elapsed_seconds=provider_elapsed_seconds,
        )

    async def _wait_for_history(
        self,
        prompt_id: str,
    ) -> dict[str, Any]:
        """Poll ComfyUI until the workflow succeeds or the timeout expires."""
        deadline = asyncio.get_running_loop().time() + self.timeout

        while asyncio.get_running_loop().time() < deadline:
            response = await self.client.get(f"/history/{prompt_id}")
            response.raise_for_status()

            payload = response.json()
            record = payload.get(prompt_id)

            if record:
                status_info = record.get("status") or {}
                status = status_info.get("status_str")

                if status == "error":
                    raise RuntimeError(
                        f"ComfyUI workflow failed: {status_info}"
                    )

                if status == "success":
                    outputs = record.get("outputs") or {}

                    if not outputs:
                        raise RuntimeError(
                            "ComfyUI reported success but returned no outputs."
                        )

                    return record

            await asyncio.sleep(self.poll_interval)

        raise TimeoutError(
            f"ComfyUI generation {prompt_id} "
            f"exceeded {self.timeout} seconds."
        )

    def _extract_saved_image(
        self,
        history: dict[str, Any],
    ) -> dict[str, str]:
        for node in history.get("outputs", {}).values():
            for image in node.get("images", []):
                if image.get("filename"):
                    return image

        raise RuntimeError("ComfyUI completed but returned no saved image.")

    async def aclose(self) -> None:
        await self.client.aclose()
