Mission: Build AI Chat Gateway with Secure Image Uploads

Goal

Create the private chat and conversation gateway used by the future MITIGATE AI Admin Panel.

The gateway must allow an authenticated administrator to send development instructions, attach screenshots, create conversations, preserve chat history, invoke AI Planner, and enqueue the resulting missions without using SSH.

Architecture

- Use Python standard library only.
- Do not add external dependencies.
- Do not modify requirements.txt.
- Keep chat, uploads, planning, queueing, and execution responsibilities separated.
- Use the existing AI Planner through its public API.
- Use the existing Mission Queue through its public API.
- Never execute missions directly inside chat request handling.
- Background Worker remains responsible for mission execution.
- Support dependency injection for Planner, Mission Queue, storage, clock, identifier generation, and image analysis provider.
- Fully typed and compatible with Python 3.12.

Conversation Model

- Support multiple independent conversations.
- Each conversation must have:
  - conversation_id
  - title
  - created_at
  - updated_at
  - status
  - message_count
- Supported conversation states:
  - active
  - archived
  - deleted
- Preserve deterministic message ordering.
- Support administrator and agent message roles.
- Each message must have:
  - message_id
  - conversation_id
  - role
  - text
  - image_ids
  - created_at
  - request_id
- Message identifiers and conversation identifiers must be validated.
- Prevent duplicate message and request identifiers.
- Store conversations and messages atomically as JSON.
- Recover safely after process restart.
- Never store secrets in conversation history.

Chat Behavior

- Accept plain text development requests.
- Accept text together with one or more screenshot references.
- Accept screenshot-only messages when at least one valid image is attached.
- Reject completely empty messages.
- Preserve the administrator's original text exactly.
- Produce a safe structured acknowledgement.
- Allow a message to request:
  - analysis only
  - planning only
  - plan and enqueue
- Default behavior must be plan and enqueue.
- Planner failures must not partially enqueue missions.
- Queue insertion must remain atomic.
- Return the created request identifier and mission identifiers.
- Never expose internal prompts, chain-of-thought, provider responses, API keys, or raw exceptions.

Image Upload Support

- Support PNG, JPEG, JPG, and WebP only.
- Support clipboard-pasted screenshots from the future browser panel.
- Support drag-and-drop uploads from the future browser panel.
- Support multiple images per message.
- Validate file content using magic bytes, not filename extension alone.
- Reject unsupported or malformed files.
- Reject empty files.
- Reject files above a configurable maximum size.
- Default maximum image size must be 10 MiB.
- Limit the number of images attached to one message.
- Default maximum images per message must be 10.
- Generate safe server-side image identifiers.
- Never use the original filename as a storage path.
- Preserve only a sanitized display filename.
- Store images outside publicly served directories.
- Prevent path traversal and symbolic-link escape.
- Write uploaded images atomically.
- Use restrictive file permissions.
- Never execute uploaded files.
- Never interpret image metadata as commands.
- Store safe image metadata:
  - image_id
  - media_type
  - size_bytes
  - sha256
  - width when safely detectable
  - height when safely detectable
  - created_at
  - sanitized_filename
- Detect duplicate uploads using SHA-256 while preserving separate message references.
- Delete image metadata and stored bytes together.
- Prevent deletion of an image referenced by an active message unless force deletion is explicitly requested.
- Record deletion events without retaining image content.

Image Privacy and Safety

- Do not preserve EXIF metadata when a safe standard-library rewrite is possible.
- When metadata stripping cannot be safely completed with the standard library, store the original image privately and mark metadata_stripped=false.
- Never claim metadata was removed unless it was actually removed.
- Never expose local filesystem paths in API responses.
- Never include uploaded image bytes in logs.
- Never log bearer tokens, cookies, authorization headers, or provider keys.
- Never send an image to an AI provider unless the administrator message explicitly requires image analysis.
- Image-provider integration must be behind a dependency-injected interface.
- Tests must use a fake image analysis provider.
- No real provider or network call may occur in tests.

Storage

- Store chat state in an atomic JSON data file.
- Store image metadata in an atomic JSON data file.
- Store image bytes in a dedicated private directory.
- Use file locking to prevent concurrent corruption.
- Recover safely from process restart.
- Reject corrupted storage instead of silently overwriting it.
- Provide deterministic JSON serialization.
- Support configurable:
  - conversations path
  - uploads metadata path
  - uploads directory
  - maximum image size
  - maximum images per message
- Unrelated files must never be modified.

Public Service Interface

Provide a ChatGateway class with methods suitable for the Private Admin API:

- create_conversation(title)
- list_conversations()
- get_conversation(conversation_id)
- archive_conversation(conversation_id)
- delete_conversation(conversation_id)
- upload_image(content, media_type, filename)
- get_image_metadata(image_id)
- read_image(image_id)
- delete_image(image_id, force=False)
- send_message(conversation_id, text, image_ids, mode)
- list_messages(conversation_id)
- get_message(message_id)
- latest_events(limit)
- status()

HTTP Integration Contract

The module must expose handler methods or service methods suitable for these future endpoints:

- POST /v1/chat/conversations
- GET /v1/chat/conversations
- GET /v1/chat/conversations/{conversation_id}
- DELETE /v1/chat/conversations/{conversation_id}
- POST /v1/chat/conversations/{conversation_id}/messages
- GET /v1/chat/conversations/{conversation_id}/messages
- POST /v1/uploads/images
- GET /v1/uploads/images/{image_id}
- DELETE /v1/uploads/images/{image_id}

Do not duplicate the existing Private Admin API server.
Create an independent service layer that can be mounted into the existing API in a later integration mission.

Upload Input Contract

- Support raw image bytes plus an explicit media type and filename at the service layer.
- Do not require multipart parsing inside the core storage layer.
- HTTP multipart parsing will be handled by the API integration layer.
- Reject media-type and magic-byte mismatches.
- Sanitize filenames deterministically.
- Return safe metadata only.

Planner and Queue Integration

- A chat message in analysis-only mode must not call Planner or Mission Queue.
- A chat message in planning-only mode may call Planner but must not enqueue missions.
- A chat message in plan-and-enqueue mode must call Planner and enqueue the complete plan atomically.
- Image identifiers and safe image metadata may be included in Planner input.
- Never include raw image bytes in Mission Queue records.
- Dependencies and priorities returned by Planner must be preserved.
- Duplicate request identifiers must be rejected.
- Planner failure must leave Mission Queue unchanged.
- Queue failure must leave the chat message stored with a safe failed status and no partial plan.

Structured Events

Emit deterministic structured events for:

- conversation_created
- conversation_archived
- conversation_deleted
- image_uploaded
- image_deleted
- message_received
- analysis_requested
- plan_created
- missions_enqueued
- planning_failed
- enqueue_failed

Each event must contain:

- event
- timestamp
- request_id when applicable
- conversation_id when applicable
- message_id when applicable
- image_id when applicable
- safe status information

Never include secrets, raw image content, unrestricted message text, filesystem paths, or raw exceptions in events.

Testing Policy

- Use Python standard library unittest only.
- Never import or use pytest.
- Never add testing dependencies.
- Never modify requirements.txt.
- Use unittest.mock.
- Use tempfile and TemporaryDirectory.
- Tests must not perform real network access.
- Tests must not call real AI providers.
- Tests must not run real Git commands.
- Tests must not execute Background Worker.
- Use fake Planner, fake Mission Queue, fake image provider, fake clock, and deterministic identifier generator.
- Every generated Python file must pass py_compile.
- Tests must run from repository root with unittest discovery.
- Use repository-root imports such as agent.api.ai_chat_gateway.
- Do not modify sys.path inside tests.

Testing Requirements

- Test conversation creation.
- Test deterministic conversation listing.
- Test conversation archive and deletion.
- Test message ordering.
- Test text-only message.
- Test screenshot-only message.
- Test text with multiple screenshots.
- Test empty message rejection.
- Test PNG validation.
- Test JPEG validation.
- Test WebP validation.
- Test extension and media-type mismatch rejection.
- Test malformed image rejection.
- Test empty image rejection.
- Test oversized image rejection.
- Test image-count limit.
- Test filename sanitization.
- Test path traversal rejection.
- Test atomic image writes.
- Test restrictive file permissions.
- Test deterministic SHA-256 metadata.
- Test duplicate image detection.
- Test image deletion.
- Test referenced-image deletion protection.
- Test force image deletion.
- Test safe restart recovery.
- Test corrupted storage rejection.
- Test analysis-only mode.
- Test planning-only mode.
- Test plan-and-enqueue mode.
- Test planner failure without partial enqueue.
- Test queue failure without partial enqueue.
- Test duplicate request rejection.
- Test deterministic structured events.
- Test secret redaction.
- Test raw image bytes never appear in logs or JSON state.
- Test unrelated files remain unchanged.
- All existing and newly generated unittest tests must pass.

Deliverables

- agent/api/ai_chat_gateway.py
- agent/tests/test_ai_chat_gateway.py
