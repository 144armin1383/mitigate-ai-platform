from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from ai.prompt_builder import PromptBuilder
from providers.base import AIProvider, AIRequest, AIResponse
from services.planner import ExecutionPlan
from services.repository_scanner import RepositoryIndex


@dataclass
class CodeGenerationResult:
    """
    Normalized, typed result for a code generation request.

    - success: Provider reported success
    - content: Raw content returned by the AI provider
    - provider: Provider name
    - model: Concrete model used
    - error: Error message if any
    - metadata: Extra metadata such as request/response usage
    """

    success: bool
    content: str
    provider: str
    model: str
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class CodeGenerator:
    """
    High-level code generation facade using the configured AI provider or an injected one.

    Responsibilities:
    - Build a deterministic prompt using PromptBuilder
    - Create an AIRequest
    - Invoke the AI provider
    - Return a typed CodeGenerationResult

    This component does not write files, run shell commands, modify Git, or
    expose secrets. It is safe and side-effect free.
    """

    def __init__(self, ai_provider: Optional[AIProvider] = None) -> None:
        self._provider = ai_provider

    def _get_provider(self) -> AIProvider:
        if self._provider is not None:
            return self._provider

        # Attempt to obtain a default provider from a registry if available.
        try:
            from providers.registry import registry as provider_registry  # type: ignore
        except Exception as exc:  # pragma: no cover - defensive fallback
            raise RuntimeError("No AI provider available.") from exc

        # Try common patterns without assuming a specific registry API.
        for attr in ("get_default", "default", "get", "pick"):
            if hasattr(provider_registry, attr):
                candidate = getattr(provider_registry, attr)
                provider = candidate() if callable(candidate) else candidate
                if provider is not None:
                    return provider

        if hasattr(provider_registry, "providers"):
            providers = getattr(provider_registry, "providers")
            for p in providers:
                try:
                    if p.is_available():
                        return p
                except Exception:
                    continue

        raise RuntimeError("No AI provider available.")

    def _plan_to_dict(self, plan: ExecutionPlan) -> dict[str, Any]:
        # Convert ExecutionPlan to a JSON-serializable dict with enum values.
        data = asdict(plan)
        if "domain" in data and hasattr(data["domain"], "value"):
            data["domain"] = data["domain"].value  # type: ignore
        if "priority" in data and hasattr(data["priority"], "value"):
            data["priority"] = data["priority"].value  # type: ignore
        return data

    def generate(
        self,
        plan: ExecutionPlan,
        repo_index: RepositoryIndex,
        *,
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        request_metadata: Optional[dict[str, Any]] = None,
    ) -> CodeGenerationResult:
        """
        Generate code for the given plan using repository context.

        - plan: The execution plan to fulfill
        - repo_index: Indexed repository context
        - model: Optional explicit model override
        - temperature: Low temperature for determinism
        - max_tokens: Optional token/output limit
        - request_metadata: Optional custom metadata to pass to the provider
        """
        builder = PromptBuilder(plan, repo_index)
        built = builder.build()

        provider = self._get_provider()

        output_schema = {
            "name": "mitigate_generated_files",
            "description": (
                "MITIGATE autonomous mission generation envelope."
            ),
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "summary": {
                        "type": "string",
                    },
                    "files": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "path": {
                                    "type": "string",
                                },
                                "content": {
                                    "type": "string",
                                },
                            },
                            "required": [
                                "path",
                                "content",
                            ],
                        },
                    },
                },
                "required": [
                    "summary",
                    "files",
                ],
            },
        }

        request = AIRequest(
            prompt=built.user,
            system_prompt=built.system,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            output_schema=output_schema,
            metadata={
                "plan": self._plan_to_dict(plan),
                "repository": repo_index.to_dict(),
                "request_metadata": request_metadata or {},
            },
        )

        response: AIResponse = provider.generate(request)

        metadata: dict[str, Any] = {
            "request": {
                "model": request.model,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "output_schema": request.output_schema,
                "metadata": request.metadata,
            },
            "response": {
                "usage": response.usage,
                "metadata": response.metadata,
            },
        }

        return CodeGenerationResult(
            success=response.success,
            content=response.content,
            provider=response.provider,
            model=response.model,
            error=response.error,
            metadata=metadata,
        )
