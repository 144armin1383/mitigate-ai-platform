from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.logger import build_logger
from providers.base import AIRequest
from providers.openai.provider import openai_provider
from services.repository_scanner import RepositoryScanner


log = build_logger()

AGENT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = AGENT_ROOT.parent

ALLOWED_FILES = {
    "agent/ai/prompt_builder.py",
    "agent/ai/code_generator.py",
    "agent/tests/test_prompt_builder.py",
    "agent/tests/test_code_generator.py",
}

CONTEXT_FILES = (
    "agent/services/planner.py",
    "agent/services/repository_scanner.py",
    "agent/providers/base.py",
    "agent/providers/openai/provider.py",
    "agent/executors/base.py",
    "agent/services/worker.py",
)


def run_git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=check,
    )


def require_clean_repository() -> None:
    result = run_git("status", "--porcelain")

    if result.stdout.strip():
        raise RuntimeError(
            "Repository is not clean. Commit or restore existing changes first."
        )


def create_branch() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    branch = f"agent/self-build-{timestamp}"

    run_git("switch", "-c", branch)
    return branch


def build_repository_context() -> str:
    scanner = RepositoryScanner(REPOSITORY_ROOT)
    index = scanner.scan()

    paths = "\n".join(
        f"- {item.path} ({item.category})"
        for item in index.files[:120]
    )

    source_sections: list[str] = []

    for relative in CONTEXT_FILES:
        path = REPOSITORY_ROOT / relative

        if not path.is_file():
            continue

        content = path.read_text(encoding="utf-8")

        source_sections.append(
            f"\n### FILE: {relative}\n"
            f"```python\n{content}\n```"
        )

    return (
        f"Repository root: {index.root}\n"
        f"Total files: {index.total_files}\n"
        f"Total directories: {index.total_directories}\n\n"
        f"Repository files:\n{paths}\n\n"
        f"Relevant existing source files:\n"
        + "\n".join(source_sections)
    )


def build_prompt(context: str) -> str:
    allowed = "\n".join(f"- {path}" for path in sorted(ALLOWED_FILES))

    return f"""
You are extending the MITIGATE AI Agent repository.

Build the first production-quality AI coding layer.

Create exactly these files:

{allowed}

Requirements:

1. prompt_builder.py
   - Build a deterministic software-engineering prompt.
   - Accept an ExecutionPlan and RepositoryIndex.
   - Include task, domain, priority, repository summary, candidate files,
     safety constraints, and required output format.
   - Keep source code and comments entirely in English.
   - Use type hints and dataclasses where useful.
   - Do not call external services.

2. code_generator.py
   - Use ProviderRegistry or an injected AIProvider.
   - Accept an ExecutionPlan and RepositoryIndex.
   - Use PromptBuilder.
   - Return a typed result containing success, content, provider, model,
     error, and metadata.
   - Do not write files, run shell commands, modify Git, or expose secrets.

3. Tests
   - Add deterministic unit tests for both modules.
   - Tests must not make a real API request.
   - Use a fake AI provider.
   - Use Python standard library unittest unless an existing test framework
     is clearly configured.

Security constraints:

- Never access or mention .env contents.
- Never output API keys, tokens, credentials, or secrets.
- Never delete or rename existing files.
- Never modify files outside the exact allowlist.
- Do not add shell execution.
- Do not add automatic Git merge or direct main-branch modification.
- Preserve compatibility with Python 3.12.

Return only valid JSON in this exact structure:

{{
  "summary": "brief implementation summary",
  "files": [
    {{
      "path": "agent/ai/prompt_builder.py",
      "content": "complete file content"
    }}
  ]
}}

Do not wrap the JSON in Markdown fences.

Repository context:

{context}
""".strip()


def parse_response(content: str) -> dict[str, Any]:
    cleaned = content.strip()

    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        cleaned = "\n".join(lines[1:-1]).strip()

    data = json.loads(cleaned)

    if not isinstance(data, dict):
        raise ValueError("AI response root must be a JSON object.")

    files = data.get("files")

    if not isinstance(files, list) or not files:
        raise ValueError("AI response must contain a non-empty files list.")

    return data


def validate_file_entry(entry: dict[str, Any]) -> tuple[Path, str]:
    relative = entry.get("path")
    content = entry.get("content")

    if not isinstance(relative, str) or relative not in ALLOWED_FILES:
        raise ValueError(f"Disallowed generated path: {relative!r}")

    if not isinstance(content, str) or not content.strip():
        raise ValueError(f"Generated file is empty: {relative}")

    destination = (REPOSITORY_ROOT / relative).resolve()

    if REPOSITORY_ROOT not in destination.parents:
        raise ValueError(f"Generated path escapes repository: {relative}")

    forbidden_fragments = (
        "OPENAI_API_KEY=",
        "sk-proj-",
        "BEGIN PRIVATE KEY",
        "subprocess.run(",
        "os.system(",
        "eval(",
        "exec(",
    )

    for fragment in forbidden_fragments:
        if fragment in content:
            raise ValueError(
                f"Forbidden content found in {relative}: {fragment}"
            )

    return destination, content


def write_generated_files(data: dict[str, Any]) -> list[Path]:
    written: list[Path] = []

    for entry in data["files"]:
        if not isinstance(entry, dict):
            raise ValueError("Each generated file entry must be an object.")

        destination, content = validate_file_entry(entry)

        destination.parent.mkdir(parents=True, exist_ok=True)

        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(content.rstrip() + "\n", encoding="utf-8")
        temporary.replace(destination)

        written.append(destination)
        log.info("Generated file written: %s", destination)

    expected = {str(path.relative_to(REPOSITORY_ROOT)) for path in written}

    if expected != ALLOWED_FILES:
        missing = sorted(ALLOWED_FILES - expected)
        extra = sorted(expected - ALLOWED_FILES)

        raise ValueError(
            f"Generated file set mismatch. Missing={missing}, extra={extra}"
        )

    return written


def validate_generated_files(files: list[Path]) -> None:
    python_files = [str(path) for path in files if path.suffix == ".py"]

    subprocess.run(
        [sys.executable, "-m", "py_compile", *python_files],
        cwd=REPOSITORY_ROOT,
        check=True,
    )

    subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "agent/tests",
            "-p",
            "test_*.py",
            "-v",
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
    )


def commit_and_push(branch: str, summary: str) -> None:
    run_git("add", *sorted(ALLOWED_FILES))

    diff_check = run_git("diff", "--cached", "--quiet", check=False)

    if diff_check.returncode == 0:
        raise RuntimeError("Agent generated no Git changes.")

    message = "Agent: add initial AI coding engine"

    if summary:
        message = f"{message}\n\n{summary[:500]}"

    run_git("commit", "-m", message)
    run_git("push", "-u", "origin", branch)


def main() -> int:
    require_clean_repository()

    if not openai_provider.is_available():
        raise RuntimeError("OpenAI provider is unavailable.")

    branch = create_branch()
    log.info("Autonomous development branch created: %s", branch)

    try:
        context = build_repository_context()
        prompt = build_prompt(context)

        response = openai_provider.generate(
            AIRequest(
                prompt=prompt,
                system_prompt=(
                    "You are a senior Python engineer working inside a "
                    "strict, allowlisted autonomous-development pipeline."
                ),
                max_tokens=12000,
            )
        )

        if not response.success:
            raise RuntimeError(
                f"OpenAI generation failed: {response.error}"
            )

        data = parse_response(response.content)
        written = write_generated_files(data)

        validate_generated_files(written)

        summary = str(data.get("summary", "")).strip()
        commit_and_push(branch, summary)

        print()
        print("AUTONOMOUS DEVELOPMENT COMPLETED")
        print(f"Branch: {branch}")
        print("Files:")
        for path in written:
            print(f"  - {path.relative_to(REPOSITORY_ROOT)}")
        print()
        print("The branch was pushed to GitHub.")
        print("It was NOT merged into main.")

        return 0

    except Exception:
        log.exception("Autonomous development failed.")

        run_git("reset", "--hard", "HEAD", check=False)
        run_git("clean", "-fd", "--", "agent/ai", "agent/tests", check=False)

        raise


if __name__ == "__main__":
    raise SystemExit(main())
