
import re

import httpx

from app.services.safety.schemas import ModerationResult


UNSAFE_CATEGORIES = """
S1: Violent Crimes.
S2: Non-Violent Crimes.
S3: Sex Crimes.
S4: Child Exploitation.
S5: Defamation.
S6: Specialized Advice.
S7: Privacy.
S8: Intellectual Property.
S9: Indiscriminate Weapons.
S10: Hate.
S11: Self-Harm.
S12: Sexual Content.
S13: Elections.
""".strip()


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

    def _build_prompt(
        self,
        text: str,
        *,
        role: str,
        context: str | None = None,
    ) -> str:
        if role not in {"user", "assistant"}:
            raise ValueError("Unsupported moderation role.")

        if role == "user":
            conversation = f"User: {text}"
            target = "User"
            target_role = "User"
        else:
            if not context or not context.strip():
                raise ValueError(
                    "User context is required for output moderation."
                )

            conversation = (
                f"User: {context}\n\n"
                f"Agent: {text}"
            )
            target = "Agent"
            target_role = "Agent"

        return f"""
Task: Check if there is unsafe content in '{target}' messages
in conversations according to our safety policy with the below categories.

<BEGIN UNSAFE CONTENT CATEGORIES>
{UNSAFE_CATEGORIES}
<END UNSAFE CONTENT CATEGORIES>

<BEGIN CONVERSATION>

{conversation}

<END CONVERSATION>

Provide your safety assessment for ONLY THE LAST {target_role}
in the above conversation:

- First line must read 'safe' or 'unsafe'.
- If unsafe, a second line must include a comma-separated
  list of violated categories.
""".strip()

    async def moderate(
        self,
        text: str,
        *,
        role: str,
        context: str | None = None,
    ) -> ModerationResult:
        prompt = self._build_prompt(
            text,
            role=role,
            context=context,
        )

        headers = {"Content-Type": "application/json"}

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "temperature": 0,
            "max_tokens": 50,
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
        content = data["choices"][0]["message"]["content"]

        if not isinstance(content, str) or not content.strip():
            raise ValueError(
                "Llama Guard returned an empty classification."
            )

        lines = content.strip().splitlines()
        first_line = lines[0].strip().lower()

        if first_line == "safe":
            return ModerationResult(is_safe=True)

        if first_line == "unsafe":
            categories = (
                tuple(
                    re.findall(
                        r"\bS(?:1[0-3]|[1-9])\b",
                        "\n".join(lines[1:]).upper(),
                    )
                )
            )

            if not categories:
                raise ValueError(
                    "Llama Guard returned unsafe without categories."
                )

            return ModerationResult(
                is_safe=False,
                categories=categories,
            )

        raise ValueError(
            "Llama Guard returned an invalid classification."
        )
