import re

import httpx

from app.services.safety.schemas import ModerationResult


class LlamaGuardModerator:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    async def moderate(
        self,
        text: str,
        *,
        role: str,
    ) -> ModerationResult:
        if role not in {"user", "assistant"}:
            raise ValueError("Unsupported moderation role.")

        headers = {"Content-Type": "application/json"}

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": role,
                    "content": text,
                }
            ],
            "temperature": 0,
            "max_tokens": 20,
        }

        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
        ) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()

        data = response.json()
        content = (
            data["choices"][0]["message"]["content"]
            .strip()
        )

        first_line = content.splitlines()[0].strip().lower()

        if first_line == "safe":
            return ModerationResult(is_safe=True)

        if first_line == "unsafe":
            categories = tuple(
                re.findall(r"\bS\d+\b", content.upper())
            )
            return ModerationResult(
                is_safe=False,
                categories=categories,
            )

        raise ValueError(
            "Llama Guard returned an invalid classification."
        )