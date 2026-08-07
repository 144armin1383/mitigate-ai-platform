Mission: Restore Portable Recovery Backward Compatibility

Goal

Restore backward-compatible template fields required by the strict portable recovery contract without modifying any production Python code, shell scripts, tests, documentation files, or deployment assets.

Modify only:

- agent/bootstrap/env.example
- agent/bootstrap/project.example.json

Do not modify tests.
Do not modify Python files.
Do not modify shell scripts.
Do not modify README.
Do not modify requirements.txt.
Do not add dependencies.

Critical Rule

Do not simplify, replace, rename, or remove existing template fields.

Preserve every currently existing safe field and add only the missing compatibility fields required by the recovery contract.

All existing unittest tests must pass.

1. Environment Template Backward Compatibility

agent/bootstrap/env.example must preserve every existing assignment.

Add these exact variables if they are not already present:

ENVIRONMENT="<ENVIRONMENT>"
ENV_NAME="<ENVIRONMENT>"

Also preserve existing environment aliases such as ENV where already present.

The file must continue to contain the currently established generic and MITIGATE-prefixed compatibility variables.

Do not remove or rename any existing safe variable.

2. Environment External Configuration Documentation

Near the top of env.example, add clear comment lines containing these exact concepts:

# Secrets remain external to Git.
# Protected runtime values are supplied outside this repository.
# Real access values must never be committed.
# This committed file contains placeholders only.

These are comments only.

Do not introduce provider-specific access variable names.

Do not add real values.

Do not change sensitive placeholders into operational values.

All sensitive-looking fields must remain neutral placeholders.

3. Project Template Backward Compatibility

agent/bootstrap/project.example.json must preserve all currently existing safe fields.

Add these exact top-level fields if they are missing:

- project_id
- project_name
- repository
- default_branch
- allowed_paths
- denied_paths
- memory_enabled
- metadata

Recommended safe values:

"project_id": "<PROJECT_ID>"
"project_name": "<PROJECT_NAME>"
"repository": "<REPOSITORY>"
"default_branch": "main"
"allowed_paths": []
"denied_paths": []
"memory_enabled": true
"metadata": {}

Do not replace existing fields such as:

- name
- project
- environment
- description
- version
- site_type
- adapter
- supported_site_types

They may coexist intentionally for backward compatibility.

4. Preserve Existing Canonical Site Compatibility

Preserve:

"adapter": "<SITE_ADAPTER>"

as a configurable string.

Preserve the existing supported_site_types list including:

- wordpress
- lovable
- react
- nextjs
- static
- php
- generic_git
- custom

Do not convert adapter into an object.

5. JSON Safety

project.example.json must remain valid JSON.

Do not add comments to JSON.

Do not introduce duplicate keys.

Do not embed authentication values.

Do not add provider access configuration.

6. Backward Compatibility Principle

The portable templates must support both:

- legacy consumers expecting earlier field names
- newer consumers expecting current canonical field names

This mission must add compatibility aliases/fields rather than replacing existing contracts.

7. Security

Do not add:

- real credentials
- provider-specific access variables
- realistic keys
- passwords
- authentication material
- private runtime values

Do not weaken placeholder-only requirements.

8. Regression Validation

All existing unittest tests must pass.

env.example must remain parseable as simple KEY="VALUE" assignments plus comments.

project.example.json must parse successfully as JSON.

Deliverables

- agent/bootstrap/env.example
- agent/bootstrap/project.example.json
