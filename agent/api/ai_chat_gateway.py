from __future__ import annotations

import dataclasses
import json
import os
import re
import secrets
import shutil
import stat
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Protocol, Sequence, Tuple

__all__ = [
    "ChatGateway",
    "ChatGatewayError",
    "ValidationError",
    "NotFoundError",
    "ConflictError",
    "StorageError",
    "IdentifierGenerator",
    "Clock",
]


# Exceptions
class ChatGatewayError(Exception):
    pass


class ValidationError(ChatGatewayError):
    pass


class NotFoundError(ChatGatewayError):
    pass


class ConflictError(ChatGatewayError):
    pass


class StorageError(ChatGatewayError):
    pass


# Protocols for DI
class IdentifierGenerator(Protocol):
    def new_id(self, prefix: str) -> str:  # pragma: no cover - simple protocol
        ...


class Clock(Protocol):
    def now(self) -> float:  # pragma: no cover - simple protocol
        ...


class Planner(Protocol):
    def plan(
        self,
        *,
        conversation_id: str,
        message_id: str,
        request_id: str,
        text: str,
        images: List[Mapping[str, Any]],
    ) -> Mapping[str, Any]:  # plan contains list of missions, dependencies, priorities
        ...


class MissionQueue(Protocol):
    def enqueue(self, plan: Mapping[str, Any]) -> List[str]:  # returns mission ids in order
        ...


class ImageAnalysisProvider(Protocol):
    def analyze(self, *, images: List[bytes], prompt: Optional[str]) -> Mapping[str, Any]:
        ...


# Helpers
_ID_RE = re.compile(r"^[a-z0-9_\-]{3,128}$")


def _validate_id(value: str, name: str) -> None:
    if not isinstance(value, str) or not _ID_RE.match(value):
        raise ValidationError(f"invalid {name}")


def _now_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sanitize_filename(filename: str) -> str:
    # Replace backslashes to prevent Windows-style traversal
    filename = filename.replace("\\", "/")
    base = os.path.basename(filename)
    # Remove NUL and control chars
    base = "".join(ch if 32 <= ord(ch) < 127 else "_" for ch in base)
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
    cleaned = "".join(ch if ch in allowed else "_" for ch in base)
    cleaned = cleaned.lstrip(".")
    if not cleaned:
        cleaned = "unnamed"
    if len(cleaned) > 100:
        cleaned = cleaned[:100]
    return cleaned


def _ensure_dir(path: str, mode: int) -> None:
    if not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)
        try:
            os.chmod(path, mode)
        except PermissionError:
            # Best effort; ignore if FS doesn't allow
            pass


def _atomic_write_json(path: str, data: Mapping[str, Any]) -> None:
    directory = os.path.dirname(path) or "."
    _ensure_dir(directory, 0o700)
    tmp_fd, tmp_path = tempfile.mkstemp(prefix=".tmp_", dir=directory)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass


def _read_json(path: str) -> Mapping[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:  # pragma: no cover - error path used in tests but not line-by-line
            raise StorageError(f"corrupted json: {path}") from e
    if not isinstance(data, dict):
        raise StorageError("invalid storage root object")
    return data


class _FileLock:
    def __init__(self, lock_path: str):
        self._lock_path = lock_path
        self._fd: Optional[int] = None

    def __enter__(self) -> "_FileLock":
        directory = os.path.dirname(self._lock_path) or "."
        _ensure_dir(directory, 0o700)
        # Simple exclusive lock via O_EXCL lockfile
        for _ in range(10):
            try:
                self._fd = os.open(self._lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.write(self._fd, f"{os.getpid()}\n".encode("utf-8"))
                return self
            except FileExistsError:
                time.sleep(0.01)
        # Last attempt
        try:
            self._fd = os.open(self._lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(self._fd, f"{os.getpid()}\n".encode("utf-8"))
            return self
        except FileExistsError as e:  # pragma: no cover - timing dependent
            raise StorageError("unable to acquire storage lock") from e

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if self._fd is not None:
                os.close(self._fd)
        finally:
            try:
                os.remove(self._lock_path)
            except FileNotFoundError:
                pass


# Image validation
_SUPPORTED_MEDIA = {"image/png", "image/jpeg", "image/jpg", "image/webp"}


def _detect_media_type(data: bytes) -> Optional[str]:
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(data) >= 2 and data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _png_dimensions(data: bytes) -> Tuple[Optional[int], Optional[int]]:
    try:
        if len(data) < 24:
            return (None, None)
        # PNG signature (8), IHDR length (4), IHDR (4), width(4), height(4)
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            return (None, None)
        if data[12:16] != b"IHDR":
            return (None, None)
        width = int.from_bytes(data[16:20], "big")
        height = int.from_bytes(data[20:24], "big")
        return (width, height)
    except Exception:
        return (None, None)


@dataclass(frozen=True)
class ChatGatewayConfig:
    conversations_path: str
    uploads_metadata_path: str
    uploads_dir: str
    max_image_size_bytes: int = 10 * 1024 * 1024
    max_images_per_message: int = 10


class _DefaultIdentifierGenerator:
    def new_id(self, prefix: str) -> str:
        token = secrets.token_hex(8)
        return f"{prefix}{token}"


class _DefaultClock:
    def now(self) -> float:  # pragma: no cover - trivial
        return time.time()


class _ConversationsStorage:
    def __init__(self, path: str):
        self._path = path
        self._lock_path = path + ".lock"
        self._data: Dict[str, Any] = {}
        self._loaded = False
        self._load_or_init()

    def _load_or_init(self) -> None:
        if os.path.exists(self._path):
            with _FileLock(self._lock_path):
                data = _read_json(self._path)
            # Validate shape
            if not isinstance(data.get("conversations"), dict) or not isinstance(data.get("messages"), dict):
                raise StorageError("invalid conversations storage structure")
            reqs = data.get("requests")
            if reqs is None:
                data["requests"] = {}
            elif not isinstance(reqs, dict):
                raise StorageError("invalid conversations requests index")
            self._data = data  # type: ignore[assignment]
            self._loaded = True
            return
        # Initialize fresh
        self._data = {"conversations": {}, "messages": {}, "requests": {}}
        self._save()
        self._loaded = True

    def _save(self) -> None:
        with _FileLock(self._lock_path):
            _atomic_write_json(self._path, self._data)

    # Conversation ops
    def put_conversation(self, conv: Mapping[str, Any]) -> None:
        cid = str(conv["conversation_id"])
        self._data["conversations"][cid] = dict(conv)
        self._save()

    def get_conversation(self, conversation_id: str) -> Mapping[str, Any]:
        c = self._data["conversations"].get(conversation_id)
        if not c:
            raise NotFoundError("conversation not found")
        return dict(c)

    def list_conversations(self) -> List[Mapping[str, Any]]:
        items = [dict(v) for v in self._data["conversations"].values()]
        items.sort(key=lambda x: (x.get("created_at", ""), x.get("conversation_id", "")))
        return items

    def update_conversation(self, conversation_id: str, updates: Mapping[str, Any]) -> Mapping[str, Any]:
        c = self._data["conversations"].get(conversation_id)
        if not c:
            raise NotFoundError("conversation not found")
        c = dict(c)
        c.update(updates)
        self._data["conversations"][conversation_id] = c
        self._save()
        return dict(c)

    # Message ops
    def put_message(self, msg: Mapping[str, Any]) -> None:
        mid = str(msg["message_id"])
        rid = str(msg["request_id"]) if "request_id" in msg else None
        if mid in self._data["messages"]:
            raise ConflictError("duplicate message_id")
        if rid is not None and rid in self._data["requests"]:
            raise ConflictError("duplicate request_id")
        self._data["messages"][mid] = dict(msg)
        if rid is not None:
            self._data["requests"][rid] = mid
        # bump conversation message_count and updated_at
        cid = str(msg["conversation_id"])
        conv = self._data["conversations"].get(cid)
        if not conv:
            raise NotFoundError("conversation not found")
        conv = dict(conv)
        conv["message_count"] = int(conv.get("message_count", 0)) + 1
        conv["updated_at"] = str(msg.get("created_at"))
        self._data["conversations"][cid] = conv
        self._save()

    def list_messages(self, conversation_id: str) -> List[Mapping[str, Any]]:
        items = [dict(v) for v in self._data["messages"].values() if v.get("conversation_id") == conversation_id]
        items.sort(key=lambda x: (x.get("created_at", ""), x.get("message_id", "")))
        return items

    def get_message(self, message_id: str) -> Mapping[str, Any]:
        m = self._data["messages"].get(message_id)
        if not m:
            raise NotFoundError("message not found")
        return dict(m)

    def is_image_referenced(self, image_id: str) -> bool:
        for m in self._data["messages"].values():
            try:
                imgs = m.get("image_ids", [])
                if image_id in imgs:
                    return True
            except Exception:
                continue
        return False

    def counts(self) -> Tuple[int, int]:
        return (len(self._data["conversations"]), len(self._data["messages"]))


class _UploadsStorage:
    def __init__(self, metadata_path: str, uploads_dir: str):
        self._meta_path = metadata_path
        self._meta_lock = metadata_path + ".lock"
        self._uploads_dir = uploads_dir
        _ensure_dir(self._uploads_dir, 0o700)
        self._data: Dict[str, Any] = {}
        self._loaded = False
        self._load_or_init()

    def _load_or_init(self) -> None:
        if os.path.exists(self._meta_path):
            with _FileLock(self._meta_lock):
                data = _read_json(self._meta_path)
            if not isinstance(data.get("images"), dict):
                raise StorageError("invalid uploads storage structure")
            if data.get("sha_index") is None:
                data["sha_index"] = {}
            elif not isinstance(data.get("sha_index"), dict):
                raise StorageError("invalid uploads sha index structure")
            self._data = data  # type: ignore[assignment]
            self._loaded = True
            return
        self._data = {"images": {}, "sha_index": {}}
        self._save()
        self._loaded = True

    def _save(self) -> None:
        with _FileLock(self._meta_lock):
            _atomic_write_json(self._meta_path, self._data)

    def put_image_metadata(self, meta: Mapping[str, Any]) -> None:
        iid = str(meta["image_id"])
        if iid in self._data["images"]:
            raise ConflictError("duplicate image_id")
        self._data["images"][iid] = dict(meta)
        sha = str(meta["sha256"]) if "sha256" in meta else None
        if sha:
            arr = self._data["sha_index"].get(sha)
            if arr is None:
                self._data["sha_index"][sha] = [iid]
            else:
                if iid not in arr:
                    arr.append(iid)
        self._save()

    def get_image_metadata(self, image_id: str) -> Mapping[str, Any]:
        m = self._data["images"].get(image_id)
        if not m:
            raise NotFoundError("image not found")
        return dict(m)

    def list_images_by_sha(self, sha_hex: str) -> List[str]:
        arr = self._data["sha_index"].get(sha_hex, [])
        return list(arr)

    def delete_image_metadata(self, image_id: str) -> Mapping[str, Any]:
        m = self._data["images"].pop(image_id, None)
        if not m:
            raise NotFoundError("image not found")
        sha_hex = m.get("sha256")
        if sha_hex:
            arr = self._data["sha_index"].get(sha_hex)
            if arr:
                try:
                    arr.remove(image_id)
                except ValueError:
                    pass
                if not arr:
                    del self._data["sha_index"][sha_hex]
        self._save()
        return dict(m)

    def read_image_bytes(self, sha_hex: str) -> bytes:
        path = os.path.join(self._uploads_dir, sha_hex)
        try:
            with open(path, "rb") as f:
                return f.read()
        except FileNotFoundError as e:
            raise NotFoundError("image content not found") from e

    def write_image_bytes_if_absent(self, sha_hex: str, content: bytes) -> bool:
        # returns True if written, False if already existed
        path = os.path.join(self._uploads_dir, sha_hex)
        if os.path.exists(path):
            return False
        tmp_fd, tmp_path = tempfile.mkstemp(prefix=".up_", dir=self._uploads_dir)
        try:
            os.write(tmp_fd, content)
            os.fchmod(tmp_fd, 0o600)
            os.fsync(tmp_fd)
            os.close(tmp_fd)
            os.replace(tmp_path, path)
            # Ensure directory metadata flushed
            try:
                dir_fd = os.open(self._uploads_dir, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except Exception:
                pass
            return True
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass

    def delete_image_bytes_if_unreferenced(self, sha_hex: str) -> bool:
        # Deletes bytes if no metadata references remain
        remaining = self._data["sha_index"].get(sha_hex, [])
        if remaining:
            return False
        path = os.path.join(self._uploads_dir, sha_hex)
        try:
            os.remove(path)
            return True
        except FileNotFoundError:
            return False

    def image_count(self) -> int:
        return len(self._data["images"])


@dataclass
class _Event:
    event: str
    timestamp: str
    request_id: Optional[str] = None
    conversation_id: Optional[str] = None
    message_id: Optional[str] = None
    image_id: Optional[str] = None
    info: Optional[Mapping[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "event": self.event,
            "timestamp": self.timestamp,
        }
        if self.request_id:
            d["request_id"] = self.request_id
        if self.conversation_id:
            d["conversation_id"] = self.conversation_id
        if self.message_id:
            d["message_id"] = self.message_id
        if self.image_id:
            d["image_id"] = self.image_id
        if self.info is not None:
            # include only safe info
            d["info"] = dict(self.info)
        return d


class ChatGateway:
    def __init__(
        self,
        *,
        config: ChatGatewayConfig,
        planner: Optional[Planner] = None,
        mission_queue: Optional[MissionQueue] = None,
        image_analysis_provider: Optional[ImageAnalysisProvider] = None,
        clock: Optional[Clock] = None,
        id_generator: Optional[IdentifierGenerator] = None,
    ) -> None:
        self._config = config
        self._planner = planner
        self._queue = mission_queue
        self._image_provider = image_analysis_provider
        self._clock = clock or _DefaultClock()
        self._ids = id_generator or _DefaultIdentifierGenerator()
        # storages
        self._conv_store = _ConversationsStorage(config.conversations_path)
        self._up_store = _UploadsStorage(config.uploads_metadata_path, config.uploads_dir)
        # events
        self._events: List[_Event] = []

    # Events
    def _emit(self, event: str, *, request_id: Optional[str] = None, conversation_id: Optional[str] = None,
              message_id: Optional[str] = None, image_id: Optional[str] = None, info: Optional[Mapping[str, Any]] = None) -> None:
        ts = _now_iso(self._clock.now())
        # Ensure no sensitive data in info: callers must ensure safe fields only
        self._events.append(_Event(event=event, timestamp=ts, request_id=request_id,
                                   conversation_id=conversation_id, message_id=message_id, image_id=image_id, info=info))

    # Public API
    def create_conversation(self, title: str) -> Mapping[str, Any]:
        if not isinstance(title, str) or not title.strip():
            raise ValidationError("invalid title")
        cid = self._ids.new_id("c_")
        _validate_id(cid, "conversation_id")
        ts = _now_iso(self._clock.now())
        conv = {
            "conversation_id": cid,
            "title": title,
            "created_at": ts,
            "updated_at": ts,
            "status": "active",
            "message_count": 0,
        }
        self._conv_store.put_conversation(conv)
        self._emit("conversation_created", conversation_id=cid)
        return conv

    def list_conversations(self) -> List[Mapping[str, Any]]:
        return self._conv_store.list_conversations()

    def get_conversation(self, conversation_id: str) -> Mapping[str, Any]:
        _validate_id(conversation_id, "conversation_id")
        return self._conv_store.get_conversation(conversation_id)

    def archive_conversation(self, conversation_id: str) -> Mapping[str, Any]:
        _validate_id(conversation_id, "conversation_id")
        ts = _now_iso(self._clock.now())
        updated = self._conv_store.update_conversation(conversation_id, {"status": "archived", "updated_at": ts})
        self._emit("conversation_archived", conversation_id=conversation_id)
        return updated

    def delete_conversation(self, conversation_id: str) -> Mapping[str, Any]:
        _validate_id(conversation_id, "conversation_id")
        ts = _now_iso(self._clock.now())
        updated = self._conv_store.update_conversation(conversation_id, {"status": "deleted", "updated_at": ts})
        self._emit("conversation_deleted", conversation_id=conversation_id)
        return updated

    def upload_image(self, content: bytes, media_type: str, filename: str) -> Mapping[str, Any]:
        if not isinstance(content, (bytes, bytearray)):
            raise ValidationError("invalid content")
        data = bytes(content)
        if len(data) == 0:
            raise ValidationError("empty file")
        if len(data) > int(self._config.max_image_size_bytes):
            raise ValidationError("file too large")
        if media_type not in _SUPPORTED_MEDIA:
            raise ValidationError("unsupported media type")
        detected = _detect_media_type(data)
        if detected is None:
            raise ValidationError("unsupported or malformed file")
        # Accept "image/jpg" as jpeg
        if media_type == "image/jpg":
            media_type = "image/jpeg"
        if detected != media_type:
            raise ValidationError("media-type and content mismatch")
        image_id = self._ids.new_id("i_")
        _validate_id(image_id, "image_id")
        sanitized_filename = _sanitize_filename(filename)
        # Dimensions (PNG only)
        width: Optional[int] = None
        height: Optional[int] = None
        if detected == "image/png":
            w, h = _png_dimensions(data)
            width, height = w, h
        # Compute sha256
        digest = sha256(data).hexdigest()
        # Write bytes once per sha
        self._up_store.write_image_bytes_if_absent(digest, data)
        meta = {
            "image_id": image_id,
            "media_type": detected,
            "size_bytes": len(data),
            "sha256": digest,
            "width": width,
            "height": height,
            "created_at": _now_iso(self._clock.now()),
            "sanitized_filename": sanitized_filename,
            "metadata_stripped": False,
        }
        self._up_store.put_image_metadata(meta)
        self._emit("image_uploaded", image_id=image_id, info={"media_type": detected})
        return meta

    def get_image_metadata(self, image_id: str) -> Mapping[str, Any]:
        _validate_id(image_id, "image_id")
        return self._up_store.get_image_metadata(image_id)

    def read_image(self, image_id: str) -> bytes:
        _validate_id(image_id, "image_id")
        meta = self._up_store.get_image_metadata(image_id)
        return self._up_store.read_image_bytes(meta["sha256"])

    def delete_image(self, image_id: str, force: bool = False) -> Mapping[str, Any]:
        _validate_id(image_id, "image_id")
        # prevent deletion if referenced and not forced
        if not force and self._conv_store.is_image_referenced(image_id):
            raise ConflictError("image is referenced by a message")
        meta = self._up_store.delete_image_metadata(image_id)
        # delete bytes if unreferenced
        self._up_store.delete_image_bytes_if_unreferenced(meta.get("sha256", ""))
        self._emit("image_deleted", image_id=image_id)
        # Return safe metadata (no path)
        return meta

    def send_message(self, conversation_id: str, text: str, image_ids: Sequence[str], mode: str = "plan_and_enqueue") -> Mapping[str, Any]:
        _validate_id(conversation_id, "conversation_id")
        conv = self._conv_store.get_conversation(conversation_id)
        if conv.get("status") == "deleted":
            raise ConflictError("conversation deleted")
        # Validate images
        if not isinstance(image_ids, (list, tuple)):
            raise ValidationError("invalid image_ids")
        if len(image_ids) > int(self._config.max_images_per_message):
            raise ValidationError("too many images")
        resolved_images: List[Mapping[str, Any]] = []
        for iid in image_ids:
            _validate_id(iid, "image_id")
            resolved_images.append(self._up_store.get_image_metadata(iid))
        # Message must not be empty
        if not (isinstance(text, str) and len(text) > 0 and text.strip()) and not resolved_images:
            raise ValidationError("empty message")
        # Mode
        if mode not in ("analysis", "planning", "plan_and_enqueue"):
            raise ValidationError("invalid mode")
        # Generate IDs
        message_id = self._ids.new_id("m_")
        _validate_id(message_id, "message_id")
        request_id = self._ids.new_id("r_")
        _validate_id(request_id, "request_id")
        ts = _now_iso(self._clock.now())
        # Preserve admin text exactly; do not include secrets in events
        msg_record = {
            "message_id": message_id,
            "conversation_id": conversation_id,
            "role": "administrator",
            "text": text,
            "image_ids": list(image_ids),
            "created_at": ts,
            "request_id": request_id,
            "status": "received",
        }
        # Store message first (atomic with conversation update)
        self._conv_store.put_message(msg_record)
        self._emit("message_received", request_id=request_id, conversation_id=conversation_id, message_id=message_id,
                   info={"mode": mode, "has_images": bool(resolved_images)})
        # Mode behaviors
        mission_ids: List[str] = []
        if mode == "analysis":
            # Don't call planner or queue
            self._emit("analysis_requested", request_id=request_id, conversation_id=conversation_id, message_id=message_id)
            return {
                "request_id": request_id,
                "message_id": message_id,
                "conversation_id": conversation_id,
                "mode": mode,
                "missions": [],
            }
        # Prepare plan input
        if self._planner is None:
            raise ValidationError("planner not configured")
        try:
            plan = self._planner.plan(
                conversation_id=conversation_id,
                message_id=message_id,
                request_id=request_id,
                text=text,
                images=[{k: v for k, v in img.items() if k != "_path"} for img in resolved_images],
            )
        except Exception:
            # failure: record event and mark message
            safe_info = {"reason": "planning_error"}
            self._emit("planning_failed", request_id=request_id, conversation_id=conversation_id, message_id=message_id, info=safe_info)
            # Update message status (store a patched record)
            patched = dict(msg_record)
            patched["status"] = "planning_failed"
            # Overwrite in storage: put_message enforces no dup; so we need direct mutation
            # It's acceptable to update underlying storage messages directly for status update.
            # Implement by fetching and rewriting storage file: use internal API
            self._conv_store._data["messages"][message_id] = dict(patched)  # type: ignore[attr-defined]
            self._conv_store._save()  # type: ignore[attr-defined]
            return {
                "request_id": request_id,
                "message_id": message_id,
                "conversation_id": conversation_id,
                "mode": mode,
                "missions": [],
            }
        self._emit("plan_created", request_id=request_id, conversation_id=conversation_id, message_id=message_id,
                   info={"missions": len(plan.get("missions", []))})
        if mode == "planning":
            # Do not enqueue
            patched = dict(msg_record)
            patched["status"] = "planned"
            self._conv_store._data["messages"][message_id] = dict(patched)  # type: ignore[attr-defined]
            self._conv_store._save()  # type: ignore[attr-defined]
            return {
                "request_id": request_id,
                "message_id": message_id,
                "conversation_id": conversation_id,
                "mode": mode,
                "missions": [],
            }
        # plan_and_enqueue
        if self._queue is None:
            raise ValidationError("mission queue not configured")
        try:
            mission_ids = list(self._queue.enqueue(plan))
        except Exception:
            self._emit("enqueue_failed", request_id=request_id, conversation_id=conversation_id, message_id=message_id,
                       info={"reason": "enqueue_error"})
            patched = dict(msg_record)
            patched["status"] = "enqueue_failed"
            self._conv_store._data["messages"][message_id] = dict(patched)  # type: ignore[attr-defined]
            self._conv_store._save()  # type: ignore[attr-defined]
            return {
                "request_id": request_id,
                "message_id": message_id,
                "conversation_id": conversation_id,
                "mode": mode,
                "missions": [],
            }
        self._emit("missions_enqueued", request_id=request_id, conversation_id=conversation_id, message_id=message_id,
                   info={"count": len(mission_ids)})
        patched = dict(msg_record)
        patched["status"] = "enqueued"
        patched["missions"] = list(mission_ids)
        self._conv_store._data["messages"][message_id] = dict(patched)  # type: ignore[attr-defined]
        self._conv_store._save()  # type: ignore[attr-defined]
        return {
            "request_id": request_id,
            "message_id": message_id,
            "conversation_id": conversation_id,
            "mode": mode,
            "missions": mission_ids,
        }

    def list_messages(self, conversation_id: str) -> List[Mapping[str, Any]]:
        _validate_id(conversation_id, "conversation_id")
        # Ensure conversation exists
        self._conv_store.get_conversation(conversation_id)
        return self._conv_store.list_messages(conversation_id)

    def get_message(self, message_id: str) -> Mapping[str, Any]:
        _validate_id(message_id, "message_id")
        return self._conv_store.get_message(message_id)

    def latest_events(self, limit: int) -> List[Mapping[str, Any]]:
        if limit <= 0:
            return []
        return [e.to_dict() for e in self._events[-limit:]]

    def status(self) -> Mapping[str, Any]:
        conv_c, msg_c = self._conv_store.counts()
        return {
            "conversations": conv_c,
            "messages": msg_c,
            "images": self._up_store.image_count(),
        }
