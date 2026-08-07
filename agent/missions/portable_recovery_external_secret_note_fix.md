Mission: Fix Portable Recovery External Secret Documentation

Goal

Resolve the final env.example documentation mismatch identified by the strict portable recovery suite.

Modify only:

- agent/bootstrap/env.example

Do not modify tests.
Do not modify Python code.
Do not modify shell scripts.
Do not modify project.example.json.
Do not modify README.
Do not add dependencies.
All existing unittest tests must pass.

Requirements

agent/bootstrap/env.example must explicitly document that protected runtime values and secrets remain external to Git.

Add clear comment text near the top of env.example containing the exact concepts:

- secrets remain external to Git
- protected runtime values are supplied externally
- real access values must never be committed
- the committed file contains placeholders only

Use safe documentation wording only.

Do not add any real values.

Do not change the existing placeholder assignments unless required for syntax preservation.

Preserve all existing generic and MITIGATE_AI-prefixed compatibility variables.

The file must remain simple KEY="VALUE" template syntax with comments.

All sensitive assignments must remain neutral placeholders.

All existing unittest tests must pass.

Deliverables

- agent/bootstrap/env.example
