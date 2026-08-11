from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AIRequest:
    prompt: str
    system_prompt: str | None = None
    model: str | None = None
    temperature: float = 0.2
    max_tokens: int | None = None
    output_schema: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AIResponse:
    content: str
    provider: str
    model: str
    success: bool = True
    error: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class AIProvider(ABC):
    """
    Common interface for all MITIGATE AI providers.

    Every provider such as OpenAI, Claude or Gemini must implement
    this interface so providers can be changed without modifying
    the rest of the Agent.
    """

    name: str

    @abstractmethod
    def is_available(self) -> bool:
        """Return True when the provider is configured and reachable."""
        raise NotImplementedError

    @abstractmethod
    def generate(self, request: AIRequest) -> AIResponse:
        """Send a request to the provider and return a normalized response."""
        raise NotImplementedError

    def health_check(self) -> bool:
        """Basic provider health check."""
        return self.is_available()
