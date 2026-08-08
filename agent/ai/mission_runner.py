from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai.code_generator import CodeGenerator
from core.logger import build_logger
from providers.openai.provider import openai_provider
from services.planner import Planner
from services.repository_scanner import RepositoryScanner
from policies.core_protection import (
    load_core_lock_manifest,
    validate_mission_write,
)


log = build_logger()

AGENT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = AGENT_ROOT.parent
MISSIONS_ROOT = AGENT_ROOT / "missions"


class MissionError(RuntimeError):
    """Raised when an autonomous mission cannot be completed safely."""


def run_git(
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a Git command from the repository root."""

    return subprocess.run(
        ["git", *args],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=check,
    )


def require_clean_repository() -> None:
    """Stop when uncommitted repository changes are present."""

    result = run_git("status", "--porcelain")

    if result.stdout.strip():
        raise MissionError(
            "Repository is not clean. Commit or restore changes first."
        )


def require_main_branch() -> None:
    """Require missions to start from the main branch."""

    result = run_git("branch", "--show-current")
    branch = result.stdout.strip()

    if branch != "main":
        raise MissionError(
            f"Mission must start from main; current branch is {branch!r}."
        )


def load_mission(mission_name: str) -> tuple[Path, str]:
    """Load a mission Markdown file safely."""

    filename = (
        mission_name
        if mission_name.endswith(".md")
        else f"{mission_name}.md"
    )

    mission_path = (MISSIONS_ROOT / filename).resolve()

    if MISSIONS_ROOT.resolve() not in mission_path.parents:
        raise MissionError("Mission path escapes the missions directory.")

    if not mission_path.is_file():
        raise MissionError(f"Mission not found: {mission_path}")

    content = mission_path.read_text(encoding="utf-8").strip()

    if not content:
        raise MissionError("Mission file is empty.")

    return mission_path, content


def extract_deliverables(mission: str) -> set[str]:
    """
    Extract repository-relative deliverables from the mission.

    Deliverables must appear after the 'Deliverables' heading.
    """

    deliverables: set[str] = set()
    in_deliverables = False

    for raw_line in mission.splitlines():
        line = raw_line.strip()
        normalized = line.lstrip("#").strip().lower()

        if normalized == "deliverables":
            in_deliverables = True
            continue

        if not in_deliverables:
            continue

        if not line:
            continue

        if line.startswith("#"):
            break

        candidate = line.lstrip("-*0123456789. ").strip()

        if not candidate:
            continue

        if not candidate.startswith("agent/"):
            continue

        if candidate.startswith("/") or ".." in Path(candidate).parts:
            raise MissionError(
                f"Unsafe deliverable path: {candidate}"
            )

        deliverables.add(candidate)

    if not deliverables:
        raise MissionError(
            "No valid agent/ deliverables were found in the mission."
        )

    return deliverables


def create_branch(mission_path: Path) -> str:
    """Create an isolated autonomous-development branch."""

    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    mission_slug = mission_path.stem.replace("_", "-")
    branch = f"agent/mission-{mission_slug}-{timestamp}"

    run_git("switch", "-c", branch)

    log.info("Mission branch created: %s", branch)

    return branch


def build_generation_plan(
    mission_path: Path,
    mission: str,
    deliverables: set[str],
):
    """Create an execution plan enriched with mission information."""

    planner = Planner()

    plan = planner.create_plan(
        f"Implement autonomous mission: {mission_path.stem}\n\n"
        f"{mission}"
    )

    plan.title = f"Mission: {mission_path.stem}"
    plan.description = mission
    plan.estimated_files = sorted(deliverables)
    plan.metadata["mission_file"] = str(
        mission_path.relative_to(REPOSITORY_ROOT)
    )
    plan.metadata["allowed_deliverables"] = sorted(deliverables)

    plan.metadata["testing_policy"] = {
        "framework": "unittest",
        "rules": [
            "Use Python standard library unittest only.",
            "Never import or use pytest.",
            "Never add new testing dependencies.",
            "Never modify requirements.txt.",
            "Never suggest pip install commands.",
            "All tests must be compatible with unittest discovery.",
        ],
    }

    return plan


def parse_generation(content: str) -> dict[str, Any]:
    """Parse the AI JSON response."""

    cleaned = content.strip()

    if cleaned.startswith("```"):
        lines = cleaned.splitlines()

        if len(lines) >= 3:
            cleaned = "\n".join(lines[1:-1]).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise MissionError(
            f"AI response was not valid JSON: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise MissionError("AI response root must be an object.")

    files = data.get("files")

    if not isinstance(files, list) or not files:
        raise MissionError(
            "AI response must contain a non-empty files list."
        )

    return data


def validate_generated_file(
    entry: dict[str, Any],
    deliverables: set[str],
) -> tuple[Path, str]:
    """Validate one generated file against the mission allowlist."""

    relative = entry.get("path")
    content = entry.get("content")

    if not isinstance(relative, str):
        raise MissionError("Generated file path must be a string.")

    if relative not in deliverables:
        raise MissionError(
            f"Generated path is outside the allowlist: {relative}"
        )

    if not isinstance(content, str) or not content.strip():
        raise MissionError(f"Generated file is empty: {relative}")

    destination = (REPOSITORY_ROOT / relative).resolve()

    if REPOSITORY_ROOT.resolve() not in destination.parents:
        raise MissionError(
            f"Generated path escapes repository: {relative}"
        )

    forbidden_fragments = (
        "OPENAI_API_KEY=",
        "sk-proj-",
        "BEGIN PRIVATE KEY",
        "os.system(",
        "subprocess.Popen(",
        "eval(",
        "exec(",
    )

    for fragment in forbidden_fragments:
        if fragment in content:
            raise MissionError(
                f"Forbidden content in {relative}: {fragment}"
            )

    return destination, content


def write_generated_files(
    data: dict[str, Any],
    deliverables: set[str],
    mission_text: str,
) -> list[Path]:
    """Write generated files atomically."""

    generated_entries = data["files"]
    generated_paths: set[str] = set()
    written: list[Path] = []

    for entry in generated_entries:
        if not isinstance(entry, dict):
            raise MissionError(
                "Every generated file entry must be an object."
            )

        destination, content = validate_generated_file(
            entry,
            deliverables,
        )

        relative = str(destination.relative_to(REPOSITORY_ROOT))

        try:
            protection_config = load_core_lock_manifest(
                REPOSITORY_ROOT / "agent/policies/core_lock_manifest.json"
            )
            protection_decision = validate_mission_write(
                relative,
                mission_text,
                protection_config,
            )
        except Exception:
            raise MissionError("CORE_PROTECTION_UNAVAILABLE")

        if not protection_decision.allowed:
            raise MissionError(
                protection_decision.code or "CORE_PATH_LOCKED"
            )

        if relative in generated_paths:
            raise MissionError(
                f"Duplicate generated file: {relative}"
            )

        generated_paths.add(relative)

        destination.parent.mkdir(parents=True, exist_ok=True)

        temporary = destination.with_suffix(
            destination.suffix + ".tmp"
        )

        temporary.write_text(
            content.rstrip() + "\n",
            encoding="utf-8",
        )

        temporary.replace(destination)

        written.append(destination)

        log.info("Generated file written: %s", relative)

    missing = deliverables - generated_paths

    if missing:
        raise MissionError(
            f"AI did not generate all deliverables: {sorted(missing)}"
        )

    return written


def validate_generated_files(files: list[Path]) -> None:
    """Compile generated Python and run the complete unit-test suite."""

    python_files = [
        str(path)
        for path in files
        if path.suffix == ".py"
    ]

    if python_files:
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


def commit_and_push(
    branch: str,
    mission_path: Path,
    deliverables: set[str],
    summary: str,
) -> None:
    """Commit successful mission output and push its branch."""

    tracked_paths = sorted(
        deliverables
        | {
            str(mission_path.relative_to(REPOSITORY_ROOT)),
        }
    )

    run_git("add", *tracked_paths)

    diff_result = run_git(
        "diff",
        "--cached",
        "--quiet",
        check=False,
    )

    if diff_result.returncode == 0:
        raise MissionError("Mission produced no Git changes.")

    message = f"Agent mission: {mission_path.stem}"

    if summary:
        message += f"\n\n{summary[:500]}"

    run_git("commit", "-m", message)
    run_git("push", "-u", "origin", branch)


def recover_failed_mission() -> None:
    """Discard uncommitted mission output after failure."""

    run_git("reset", "--hard", "HEAD", check=False)
    run_git("clean", "-fd", "--", "agent", check=False)


def run_mission(mission_name: str) -> int:
    """Execute one autonomous development mission."""

    require_clean_repository()
    require_main_branch()

    mission_path, mission = load_mission(mission_name)
    deliverables = extract_deliverables(mission)

    if not openai_provider.is_available():
        raise MissionError("OpenAI provider is unavailable.")

    branch = create_branch(mission_path)

    try:
        scanner = RepositoryScanner(REPOSITORY_ROOT)
        repository_index = scanner.scan()

        plan = build_generation_plan(
            mission_path,
            mission,
            deliverables,
        )

        generator = CodeGenerator(
            ai_provider=openai_provider,
        )

        result = generator.generate(
            plan,
            repository_index,
            temperature=0.1,
            max_tokens=20000,
            request_metadata={
                "mission": mission,
                "deliverables": sorted(deliverables),
            },
        )

        if not result.success:
            raise MissionError(
                f"AI generation failed: {result.error}"
            )

        data = parse_generation(result.content)

        written = write_generated_files(
            data,
            deliverables,
            mission,
        )

        validate_generated_files(written)

        summary = str(data.get("summary", "")).strip()

        commit_and_push(
            branch,
            mission_path,
            deliverables,
            summary,
        )

        print()
        print("MISSION COMPLETED")
        print(f"Mission: {mission_path.name}")
        print(f"Branch: {branch}")
        print("Generated files:")

        for path in written:
            print(
                f"  - {path.relative_to(REPOSITORY_ROOT)}"
            )

        print()
        print("The branch was pushed to GitHub.")
        print("It was NOT merged into main.")

        return 0

    except Exception:
        log.exception(
            "Mission failed: %s",
            mission_path.name,
        )

        recover_failed_mission()
        raise


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a MITIGATE AI development mission."
    )

    parser.add_argument(
        "mission",
        help=(
            "Mission filename or name, for example: "
            "patch_engine or patch_engine.md"
        ),
    )

    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    return run_mission(args.mission)


if __name__ == "__main__":
    raise SystemExit(main())
