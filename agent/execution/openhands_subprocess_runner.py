from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--workspace", required=True)
    return p


def main() -> int:
    args = _build_parser().parse_args()
    payload = json.loads(os.environ.get("MITIGATE_OPENHANDS_REQUEST_JSON", "{}"))
    workspace = Path(args.workspace).expanduser().resolve()

    from openhands.sdk import Agent, Conversation, LLM, Tool
    from openhands.tools.file_editor import FileEditorTool
    from openhands.tools.task_tracker import TaskTrackerTool
    from openhands.tools.terminal import TerminalTool

    model = str(payload.get("model") or os.environ.get("MITIGATE_OPENHANDS_MODEL") or "gpt-5.5")
    api_key_env = str(payload.get("api_key_env") or "OPENAI_API_KEY")
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise RuntimeError("configured_llm_api_key_is_unavailable")

    agent = Agent(
        llm=LLM(model=model, api_key=api_key),
        tools=[
            Tool(name=TerminalTool.name),
            Tool(name=FileEditorTool.name),
            Tool(name=TaskTrackerTool.name),
        ],
    )
    conversation = Conversation(agent=agent, workspace=str(workspace))
    conversation.send_message(str(payload.get("prompt") or ""))
    conversation.run()

    run_id: Any = getattr(conversation, "id", None) or getattr(conversation, "conversation_id", None)
    print(json.dumps({"run_id": str(run_id) if run_id is not None else None}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
