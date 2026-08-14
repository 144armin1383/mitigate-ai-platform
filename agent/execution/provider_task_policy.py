from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from agent.execution.runtime_adapter import RuntimeCapabilities


@dataclass(frozen=True)
class ProviderTaskDecision:
    preferred: tuple[str, ...]
    requirements: RuntimeCapabilities
    forced_provider: str | None = None
    rationale: str = ""


_TECHNICAL_TYPES = {
    "backend", "api", "testing", "documentation", "infrastructure",
    "security", "database", "bugfix", "maintenance", "refactor", "test",
    "tests", "github", "deployment", "seo", "inspection", "general",
}
_FRONTEND_TYPES = {"frontend", "content", "wordpress"}


def _explicit_provider(text: str) -> str | None:
    value = str(text or "").lower()
    patterns = {
        "openhands": (
            r"\b(?:provider|runtime)\s*[:=]\s*openhands\b",
            r"\buse\s+openhands\b",
            r"\bwith\s+openhands\b",
        ),
        "openclaw": (
            r"\b(?:provider|runtime)\s*[:=]\s*openclaw\b",
            r"\buse\s+openclaw\b",
            r"\bwith\s+openclaw\b",
        ),
    }
    matches = [name for name, items in patterns.items() if any(re.search(p, value) for p in items)]
    return matches[0] if len(matches) == 1 else None


def decide_provider(task_type: str, objective: str = "") -> ProviderTaskDecision:
    task = str(task_type or "general").strip().lower()
    text = str(objective or "")
    forced = _explicit_provider(text)

    if forced == "openhands":
        return ProviderTaskDecision(
            preferred=("openhands",),
            requirements=RuntimeCapabilities(coding=True, terminal=True, file_editing=True, tests=True, isolated_workspace=True),
            forced_provider=forced,
            rationale="explicit_operator_runtime_switch",
        )
    if forced == "openclaw":
        return ProviderTaskDecision(
            preferred=("openclaw",),
            requirements=RuntimeCapabilities(coding=True, terminal=True, file_editing=True, tests=True, browser=True, isolated_workspace=True),
            forced_provider=forced,
            rationale="explicit_operator_runtime_switch",
        )

    visual_markers = (
        "page", "landing", "layout", "design", "visual", "ui", "ux", "style",
        "wordpress page", "form", "career", "recruit", "content", "motion",
        "reference site", "reference url", "motionsites", "browser", "responsive",
    )
    technical_markers = (
        "bug", "backend", "api", "database", "server", "security", "deploy",
        "performance", "technical seo", "schema", "redirect", "sitemap", "robots",
        "monitor", "maintenance", "test", "refactor", "php", "nginx", "systemd",
    )
    lowered = text.lower()
    visual = task in _FRONTEND_TYPES or any(marker in lowered for marker in visual_markers)
    technical = task in _TECHNICAL_TYPES or any(marker in lowered for marker in technical_markers)

    if visual and not technical:
        return ProviderTaskDecision(
            preferred=("openclaw", "openhands"),
            requirements=RuntimeCapabilities(coding=True, terminal=True, file_editing=True, tests=True, browser=True, isolated_workspace=True),
            rationale="visual_frontend_browser_work_prefers_openclaw",
        )

    return ProviderTaskDecision(
        preferred=("openhands", "openclaw"),
        requirements=RuntimeCapabilities(coding=True, terminal=True, file_editing=True, tests=True, isolated_workspace=True),
        rationale="technical_software_engineering_prefers_openhands",
    )


def provider_contract(provider: str) -> tuple[str, ...]:
    if provider == "openclaw":
        return (
            "Own frontend/UI/UX, WordPress page creation and editing, content presentation, forms, responsive styling, browser validation and visual-reference work.",
            "Inspect the existing live/site UI first and reuse its design system rather than inventing a disconnected style.",
            "Reference sites such as motionsites.ai may be inspected for layout/motion inspiration when requested; do not copy proprietary source code or protected assets.",
            "Never hard-code the current public IP into WordPress content or application routes; use site-relative or canonical WordPress URLs so a later domain switch survives.",
            "If a material product requirement cannot be safely inferred, ask one concise consolidated clarification question instead of inventing business facts.",
        )
    return (
        "Own backend/API/database/infrastructure/deployment/security/testing/maintenance/bug-fix/refactor and technical-SEO work.",
        "Prefer repository evidence, automated tests, logs and reproducible diagnostics over visual guesswork.",
        "For live-site monitoring or technical SEO, inspect only what is necessary and keep code/server changes separate from frontend design work.",
    )


__all__ = ["ProviderTaskDecision", "decide_provider", "provider_contract"]
