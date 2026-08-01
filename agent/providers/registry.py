from __future__ import annotations

from dataclasses import dataclass, field

from providers.base import AIProvider, AIRequest, AIResponse


@dataclass
class ProviderRegistry:
    """
    Register AI providers and execute requests with automatic failover.
    """

    providers: list[AIProvider] = field(default_factory=list)

    def register(self, provider: AIProvider) -> None:
        if any(item.name == provider.name for item in self.providers):
            raise ValueError(f"Provider already registered: {provider.name}")

        self.providers.append(provider)

    def available_providers(self) -> list[AIProvider]:
        return [
            provider
            for provider in self.providers
            if provider.is_available()
        ]

    def generate(self, request: AIRequest) -> AIResponse:
        errors: list[str] = []

        for provider in self.available_providers():
            try:
                response = provider.generate(request)

                if response.success:
                    return response

                errors.append(
                    f"{provider.name}: {response.error or 'unknown error'}"
                )

            except Exception as exc:
                errors.append(f"{provider.name}: {exc}")

        return AIResponse(
            content="",
            provider="none",
            model=request.model or "unknown",
            success=False,
            error="No AI provider succeeded. " + " | ".join(errors),
        )


registry = ProviderRegistry()
