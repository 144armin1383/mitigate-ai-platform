from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from services.planner import ExecutionPlan
from services.repository_scanner import RepositoryIndex, RepositoryFile


@dataclass(frozen=True)
class BuiltPrompt:
    """
    Container for the final prompt used by an AI provider.

    - system: Instructional system prompt for deterministic behavior
    - user: Task-specific prompt including repository context and constraints
    """

    system: str
    user: str


class PromptBuilder:
    """
    Build a deterministic, software-engineering-focused prompt.

    The prompt is composed of:
    - Task details (title, description)
    - Domain and priority
    - Execution requirements and steps
    - Repository summary
    - Candidate files derived from the execution plan
    - Safety constraints
    - Required output format (JSON contract)

    This builder does not access external services and produces stable output
    for the same inputs. All content is in English.
    """

    def __init__(self, plan: ExecutionPlan, repo_index: RepositoryIndex) -> None:
        self.plan = plan
        self.repo_index = repo_index

    def build(self) -> BuiltPrompt:
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt()
        return BuiltPrompt(system=system_prompt, user=user_prompt)

    # Internal helpers

    def _build_system_prompt(self) -> str:
        # Keep the system prompt concise and deterministic.
        return (
            "You are the MITIGATE AI software engineering agent. "
            "Produce secure, deterministic, production-quality code. "
            "Always respond in English. Follow the Required Output Format exactly. "
            "Never access external networks or hidden environments."
        )

    def _build_user_prompt(self) -> str:
        sections: list[str] = []

        sections.append("MITIGATE AI Agent - Software Engineering Task")
        sections.append("")

        # Task details
        sections.append("Task")
        sections.append(f"- Title: {self.plan.title}")
        sections.append(f"- Description: {self.plan.description}")
        sections.append(f"- Domain: {self.plan.domain.value}")
        sections.append(f"- Priority: {self.plan.priority.value}")
        sections.append(f"- Requires tests: {self.plan.requires_tests}")
        sections.append(f"- Requires backup: {self.plan.requires_backup}")
        sections.append(f"- Requires commit: {self.plan.requires_commit}")
        sections.append(f"- Requires owner approval: {self.plan.requires_owner_approval}")
        sections.append("")

        # Planned steps (deterministic order as provided)
        if self.plan.steps:
            sections.append("Execution Steps")
            for i, step in enumerate(self.plan.steps, start=1):
                sections.append(f"{i}. {step}")
            sections.append("")

        # Repository summary
        sections.append("Repository Summary")
        sections.append(f"- Root: {self.repo_index.root}")
        sections.append(f"- Total files: {self.repo_index.total_files}")
        sections.append(f"- Total directories: {self.repo_index.total_directories}")
        # Deterministic per-category and per-extension counts
        category_counts = self._count_by(lambda f: f.category)
        if category_counts:
            sections.append("- File categories:")
            for category in sorted(category_counts):
                sections.append(f"  - {category}: {category_counts[category]}")
        ext_counts = self._count_by(lambda f: f.extension or "<none>")
        if ext_counts:
            sections.append("- File extensions:")
            for ext in sorted(ext_counts):
                sections.append(f"  - {ext}: {ext_counts[ext]}")
        sections.append("")

        # Candidate files: resolve from estimated paths deterministically
        sections.append("Candidate Files")
        candidates = self._resolve_candidate_files(self.plan.estimated_files)
        if candidates:
            for path in candidates:
                sections.append(f"- {path}")
        else:
            sections.append("- <none>")
        sections.append("")

        # Safety constraints (must be explicit and stable)
        sections.append("Safety Constraints")
        sections.append("- Never access or mention .env contents.")
        sections.append("- Never output API keys, tokens, credentials, or secrets.")
        sections.append("- Do not write files, run shell commands, or access external networks.")
        sections.append("- Do not modify Git history, perform merges, or push to remote branches.")
        sections.append("- Do not add shell execution or system-level side effects.")
        sections.append("- Keep all source code and comments entirely in English.")
        sections.append("- Prefer deterministic and reproducible solutions.")
        sections.append("")

        # Required output format - a precise JSON contract used by the Agent
        sections.append("Required Output Format")
        sections.append(
            "Return only valid JSON with the following structure (no Markdown fences):"
        )
        sections.append("{")
        sections.append("  \"summary\": \"brief implementation summary\",")
        sections.append("  \"files\": [")
        sections.append("    {")
        sections.append("      \"path\": \"relative/path/to/file.ext\",")
        sections.append("      \"content\": \"complete file content\"")
        sections.append("    }")
        sections.append("  ]")
        sections.append("}")
        sections.append("")

        # Implementation guidance (concise and deterministic)
        sections.append("Implementation Guidance")
        sections.append("- Follow Python 3.12 compatibility where applicable.")
        sections.append("- Ensure code is production-quality: typed, readable, and well-structured.")
        sections.append("- Respect repository conventions and avoid breaking changes.")
        sections.append("")

        return "\n".join(sections).rstrip() + "\n"

    def _count_by(self, key_func: callable[[RepositoryFile], str]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for f in self.repo_index.files:
            key = key_func(f)
            counts[key] = counts.get(key, 0) + 1
        return counts

    def _resolve_candidate_files(self, estimated_paths: Iterable[str]) -> list[str]:
        """
        Resolve candidate files based on plan.estimated_files against the
        repository index. Deterministically sorted and unique.

        Matching rules:
        - If an estimated path ends with '/' or looks like a directory, include
          all files whose paths start with that prefix.
        - If it is a specific file, include it if present, otherwise include the
          raw path as a hint.
        """
        repo_paths = [f.path for f in self.repo_index.files]
        repo_set = set(repo_paths)

        resolved: set[str] = set()
        for raw in estimated_paths:
            normalized = raw.strip()
            if not normalized:
                continue

            # Heuristic: treat as directory if endswith('/') or has no extension
            is_dir_hint = normalized.endswith('/') or ('.' not in normalized.split('/')[-1])

            if is_dir_hint:
                # Prefix match for directory-like hints
                for p in repo_paths:
                    if p.startswith(normalized):
                        resolved.add(p)
                # Keep the directory hint as well for visibility
                resolved.add(normalized)
            else:
                if normalized in repo_set:
                    resolved.add(normalized)
                else:
                    # Keep the hint to guide the model even if not present
                    resolved.add(normalized)

        return sorted(resolved)
