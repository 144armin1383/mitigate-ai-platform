from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from providers.base import AIProvider, AIRequest, AIResponse


AGENT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(AGENT_ROOT / ".env")


class OpenAIProvider(AIProvider):
    """OpenAI provider for the MITIGATE AI Agent."""

    name = "openai"

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.default_model = os.getenv("OPENAI_MODEL", "gpt-5").strip()
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None

    def is_available(self) -> bool:
        return bool(self.client and self.default_model)

    def generate(self, request: AIRequest) -> AIResponse:
        model = request.model or self.default_model

        if not self.is_available():
            return AIResponse(
                content="",
                provider=self.name,
                model=model,
                success=False,
                error="OpenAI provider is not configured.",
            )

        try:
            request_kwargs = {
                "model": model,
                "instructions": (
                    request.system_prompt
                    or "You are the MITIGATE AI software engineering agent."
                ),
                "input": request.prompt,
                "max_output_tokens": request.max_tokens,
            }

            if request.output_schema is not None:
                request_kwargs["text"] = {
                    "format": {
                        "type": "json_schema",
                        "name": request.output_schema["name"],
                        "description": request.output_schema.get(
                            "description",
                            "",
                        ),
                        "schema": request.output_schema["schema"],
                        "strict": bool(
                            request.output_schema.get(
                                "strict",
                                True,
                            )
                        ),
                    }
                }

            response = self.client.responses.create(
                **request_kwargs
            )

            usage = {}

            if getattr(response, "usage", None):
                usage = {
                    "input_tokens": getattr(
                        response.usage,
                        "input_tokens",
                        None,
                    ),
                    "output_tokens": getattr(
                        response.usage,
                        "output_tokens",
                        None,
                    ),
                    "total_tokens": getattr(
                        response.usage,
                        "total_tokens",
                        None,
                    ),
                }

            return AIResponse(
                content=response.output_text,
                provider=self.name,
                model=model,
                success=True,
                usage=usage,
            )

        except Exception as exc:
            return AIResponse(
                content="",
                provider=self.name,
                model=model,
                success=False,
                error=str(exc),
            )


openai_provider = OpenAIProvider()
