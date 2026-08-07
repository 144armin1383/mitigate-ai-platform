Mission: Final Portable Recovery Clean Checkout Compatibility Fix

Goal

Resolve the final four strict portable recovery failures while preserving all existing production behavior, security guarantees, and portability requirements.

Modify only:

- agent/bootstrap/portable_bootstrap.py
- agent/bootstrap/restore_manager.py
- agent/bootstrap/env.example
- agent/bootstrap/project.example.json

Do not modify tests.
Do not modify shell scripts.
Do not modify README.
Do not modify requirements.txt.
Do not add dependencies.
Use Python standard library only.
All existing unittest tests must pass.

1. Clean Checkout Validation Contract

The portable bootstrap validation interface must be safely invokable from a fresh clean repository checkout.

A validation-only call must not require:

- machine-specific hidden files
- existing /etc configuration
- previously created runtime state
- provider connectivity
- provider access configuration
- production service installation
- existing project memory
- an already-deployed website

Validation-only mode must distinguish between:

A. repository/bootstrap structure is valid but external runtime configuration is still required

and

B. repository/bootstrap structure itself is invalid.

For case A, return a safe structured validation result rather than raising an exception or reporting an internal failure.

The result may indicate a state equivalent to:

- ready_for_configuration
- configuration_required
- validation_ready
- validated

as appropriate to the existing public API.

Requirements:

- Preserve the existing public classes and functions.
- Do not weaken path validation.
- Do not mutate caller input.
- Do not contact providers.
- Do not make network calls.
- Do not execute Git.
- Do not deploy.
- Do not require prior conversation state.
- Do not require server-local hidden state.

A fresh checkout containing repository-managed assets must be safely validateable before external runtime values are installed.

2. Environment Template Canonical Compatibility

agent/bootstrap/env.example must contain the generic canonical variable:

ENVIRONMENT="<ENVIRONMENT>"

It must also preserve:

MITIGATE_AI_ENVIRONMENT_NAME="<ENVIRONMENT>"

Also preserve all previously established generic and MITIGATE_AI compatibility fields, including:

PROJECT_ID="<PROJECT_ID>"
REPOSITORY_ROOT="<REPOSITORY_ROOT>"
DATA_ROOT="<DATA_ROOT>"
MEMORY_ROOT="<MEMORY_ROOT>"
PROVIDER="<PROVIDER>"
PROVIDER_API_KEY="<PLACEHOLDER>"
PROVIDER_BASE_URL="<PROVIDER_BASE_URL>"
PROVIDER_MODEL="<PROVIDER_MODEL>"
SITE_ADAPTER="<SITE_ADAPTER>"
RUNTIME_HOST="<RUNTIME_HOST>"
RUNTIME_PORT="<RUNTIME_PORT>"
API_TOKEN="<PLACEHOLDER>"

and their MITIGATE_AI-prefixed equivalents.

Every value must remain placeholder-only.

Do not use operational defaults.

Do not add inline comments after assignment values.

3. Canonical Project Template Contract

agent/bootstrap/project.example.json must contain all of these top-level fields:

- project_id
- project_name
- repository
- default_branch
- site_type
- cms_type
- adapter
- canonical_url
- allowed_paths
- denied_paths
- environment
- seo_enabled
- performance_monitoring_enabled
- availability_monitoring_enabled
- security_monitoring_enabled
- accessibility_monitoring_enabled
- ecommerce_enabled
- autonomous_low_risk_fixes
- autonomous_medium_risk_fixes
- memory_enabled
- metadata

The top-level adapter field must remain a configurable string:

"adapter": "<SITE_ADAPTER>"

Do not replace adapter with an object.

The template must remain valid JSON.

Use safe illustrative values and placeholders.

Recommended canonical shape:

{
  "project_id": "example-project",
  "project_name": "Example Portable Project",
  "repository": "https://example.invalid/repository.git",
  "default_branch": "main",
  "site_type": "generic_git",
  "cms_type": "custom",
  "adapter": "<SITE_ADAPTER>",
  "canonical_url": "https://www.example.com",
  "allowed_paths": ["."],
  "denied_paths": [],
  "environment": {
    "name": "<ENVIRONMENT>"
  },
  "seo_enabled": true,
  "performance_monitoring_enabled": true,
  "availability_monitoring_enabled": true,
  "security_monitoring_enabled": true,
  "accessibility_monitoring_enabled": true,
  "ecommerce_enabled": false,
  "autonomous_low_risk_fixes": true,
  "autonomous_medium_risk_fixes": false,
  "memory_enabled": true,
  "metadata": {}
}

Detailed platform profiles may remain in a separate optional field, but must not replace these canonical top-level fields.

Continue representing:

- wordpress
- lovable
- react
- nextjs
- static
- php
- generic_git
- custom

without hard-coding the autonomous core to any one platform.

4. Project Template Protected-Configuration Safety

The project template must contain no embedded access material.

Do not add authentication values or provider access values.

Keep provider/runtime access configuration external to project.example.json.

Avoid descriptive strings that conflict with the strict project-template safety checks already established by prior recovery compatibility missions.

5. Restore Manager Sensitive-Material Safety Contract

agent/bootstrap/restore_manager.py must explicitly describe and enforce safe handling of sensitive material.

The production module source must contain clear terminology indicating that sensitive material is rejected, excluded, or not restored.

Use safe wording such as:

"Sensitive material is excluded from portable restore data."

or equivalent.

This must reflect real production behavior, not merely be an unused comment.

Restore validation must reject or exclude protected runtime material before writing restored state.

Preserve existing detection and filtering behavior.

Do not weaken existing restore safety.

Do not persist:

- authentication material
- provider access material
- authorization data
- private runtime configuration
- raw provider responses

Do not introduce realistic protected-value examples into source code.

6. Restore Manager Import Compatibility

Preserve the direct module-spec import compatibility implemented previously.

Do not regress the fix that allows restore_manager.py to load safely through both:

- normal package import
- direct importlib spec-loader execution

7. Clean Checkout Project Identity

A clean checkout parser loading project.example.json must immediately find:

project_id

at the top level.

The clean-checkout validation path must be able to use this template without requiring an already-created production project configuration.

A placeholder/example project configuration must be valid for structural validation.

8. Validation-Only Semantics

Structural validation must not treat placeholder configuration as production-ready configuration.

It must safely report that external configuration is required where appropriate.

Do not make placeholders usable as real provider/runtime access values.

This distinction is important:

repository valid + placeholders present
=
safe validation/configuration-required state

not

runtime production-ready state.

9. Security

Do not use:

- subprocess
- os.system
- eval
- exec
- compile
- dynamic imports
- network calls
- direct Git operations
- deployment operations

Do not weaken:

- path validation
- project isolation
- restore filtering
- provider neutrality
- platform neutrality

10. Regression Requirements

All existing unittest tests must pass.

All generated Python must pass py_compile.

project.example.json must parse successfully.

env.example must remain simple KEY="VALUE" syntax.

Deliverables

- agent/bootstrap/portable_bootstrap.py
- agent/bootstrap/restore_manager.py
- agent/bootstrap/env.example
- agent/bootstrap/project.example.json
