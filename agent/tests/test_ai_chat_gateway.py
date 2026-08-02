from __future__ import annotations

import io
import json
import os
import stat
import tempfile
import unittest
from typing import Any, Dict, List, Mapping, Optional

from agent.api.ai_chat_gateway import (
    ChatGateway,
    ChatGatewayConfig,
    ConflictError,
    NotFoundError,
    Planner,
    StorageError,
    ValidationError,
)


class FakeClock:
    def __init__(self, start: float = 1700000000.0):
        self.t = start

    def now(self) -> float:
        self.t += 1.0
        return self.t


class SeqIdGen:
    def __init__(self) -> None:
        self.counters: Dict[str, int] = {}
        self.fixed: Dict[str, Optional[str]] = {}

    def set_fixed(self, prefix: str, value: str) -> None:
        self.fixed[prefix] = value

    def new_id(self, prefix: str) -> str:
        if prefix in self.fixed and self.fixed[prefix] is not None:
            # return the same id each time for duplicate tests
            return self.fixed[prefix]  # type: ignore[return-value]
        c = self.counters.get(prefix, 0) + 1
        self.counters[prefix] = c
        return f"{prefix}{c:04d}"


class FakePlanner(Planner):
    def __init__(self) -> None:
        self.requests: List[Mapping[str, Any]] = []
        self.should_fail: bool = False

    def plan(
        self,
        *,
        conversation_id: str,
        message_id: str,
        request_id: str,
        text: str,
        images: List[Mapping[str, Any]],
    ) -> Mapping[str, Any]:
        if self.should_fail:
            raise RuntimeError("planner fail")
        self.requests.append({
            "conversation_id": conversation_id,
            "message_id": message_id,
            "request_id": request_id,
            "text": text,
            "images": images,
        })
        # simple plan with dependency
        return {
            "missions": [
                {"id": "mA", "title": "first", "depends_on": [], "priority": 5},
                {"id": "mB", "title": "second", "depends_on": ["mA"], "priority": 5},
            ]
        }


class FakeQueue:
    def __init__(self) -> None:
        self.enqueued: List[Mapping[str, Any]] = []
        self.should_fail: bool = False

    def enqueue(self, plan: Mapping[str, Any]) -> List[str]:
        if self.should_fail:
            raise RuntimeError("queue fail")
        self.enqueued.append(plan)
        ids = [m.get("id") for m in plan.get("missions", [])]
        return [str(x) for x in ids if x is not None]


# Helpers to craft small valid images

def make_png_1x1() -> bytes:
    # Minimal PNG with IHDR 1x1 and IEND, crc not validated here as we only inspect header
    return (b"\x89PNG\r\n\x1a\n"  # signature
            b"\x00\x00\x00\x0d"  # length 13
            b"IHDR"               # IHDR
            b"\x00\x00\x00\x01"  # width=1
            b"\x00\x00\x00\x01"  # height=1
            b"\x08\x02\x00\x00\x00"  # bit depth, color type, etc
            b"\x90\x77\x53\xde"  # fake CRC
            b"\x00\x00\x00\x00IEND\xaeB`\x82")


def make_jpeg_min() -> bytes:
    # SOI + JFIF APP0 minimal + EOI; magic detection uses SOI only
    return b"\xff\xd8" + b"JFIF minimal" + b"\xff\xd9"


def make_webp_min() -> bytes:
    # RIFF container with WEBP header
    return b"RIFF" + b"\x1a\x00\x00\x00" + b"WEBP" + b"VP8X" + b"\x00" * 10


class ChatGatewayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.base = self.tmpdir.name
        self.conv_path = os.path.join(self.base, "conversations.json")
        self.uploads_meta = os.path.join(self.base, "uploads.json")
        self.uploads_dir = os.path.join(self.base, "uploads")
        self.clock = FakeClock(1700000000.0)
        self.ids = SeqIdGen()
        self.planner = FakePlanner()
        self.queue = FakeQueue()
        self.cfg = ChatGatewayConfig(
            conversations_path=self.conv_path,
            uploads_metadata_path=self.uploads_meta,
            uploads_dir=self.uploads_dir,
            max_image_size_bytes=10 * 1024 * 1024,
            max_images_per_message=10,
        )
        self.gw = ChatGateway(config=self.cfg, planner=self.planner, mission_queue=self.queue, clock=self.clock, id_generator=self.ids)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    # Conversations
    def test_conversation_creation_and_listing(self) -> None:
        c1 = self.gw.create_conversation("First")
        c2 = self.gw.create_conversation("Second")
        self.assertEqual(c1["status"], "active")
        lst = self.gw.list_conversations()
        self.assertEqual([c1["conversation_id"], c2["conversation_id"]], [x["conversation_id"] for x in lst])
        # Events
        ev = self.gw.latest_events(10)
        self.assertTrue(any(e.get("event") == "conversation_created" for e in ev))

    def test_conversation_archive_delete(self) -> None:
        c = self.gw.create_conversation("X")
        cid = c["conversation_id"]
        c_arch = self.gw.archive_conversation(cid)
        self.assertEqual(c_arch["status"], "archived")
        c_del = self.gw.delete_conversation(cid)
        self.assertEqual(c_del["status"], "deleted")

    # Uploads
    def test_png_validation_and_metadata(self) -> None:
        data = make_png_1x1()
        meta = self.gw.upload_image(data, "image/png", "clip.png")
        self.assertEqual(meta["media_type"], "image/png")
        self.assertEqual(meta["width"], 1)
        self.assertEqual(meta["height"], 1)
        content = self.gw.read_image(meta["image_id"])
        self.assertEqual(content, data)
        # File permissions are restrictive
        path = os.path.join(self.uploads_dir, meta["sha256"])
        st = os.stat(path)
        self.assertEqual(stat.S_IMODE(st.st_mode), 0o600)

    def test_jpeg_and_webp_validation(self) -> None:
        jmeta = self.gw.upload_image(make_jpeg_min(), "image/jpeg", "a.jpg")
        self.assertEqual(jmeta["media_type"], "image/jpeg")
        wmeta = self.gw.upload_image(make_webp_min(), "image/webp", "b.webp")
        self.assertEqual(wmeta["media_type"], "image/webp")

    def test_media_type_mismatch_and_malformed(self) -> None:
        with self.assertRaises(ValidationError):
            self.gw.upload_image(make_png_1x1(), "image/jpeg", "x.jpg")
        with self.assertRaises(ValidationError):
            self.gw.upload_image(b"not an image", "image/png", "x.png")

    def test_empty_and_oversized_image_rejection(self) -> None:
        with self.assertRaises(ValidationError):
            self.gw.upload_image(b"", "image/png", "x.png")
        cfg = ChatGatewayConfig(self.conv_path, self.uploads_meta, self.uploads_dir, max_image_size_bytes=8)
        gw2 = ChatGateway(config=cfg, planner=self.planner, mission_queue=self.queue, clock=self.clock, id_generator=self.ids)
        with self.assertRaises(ValidationError):
            gw2.upload_image(b"123456789", "image/png", "x.png")

    def test_filename_sanitization_and_path_safety(self) -> None:
        data = make_png_1x1()
        meta = self.gw.upload_image(data, "image/png", "../../evil;name.png")
        self.assertNotIn("/", meta["sanitized_filename"])  # no path traversal preserved
        path = os.path.join(self.uploads_dir, meta["sha256"])  # content-addressed path
        self.assertTrue(os.path.isfile(path))

    def test_duplicate_image_detection_and_deletion(self) -> None:
        data = make_png_1x1()
        m1 = self.gw.upload_image(data, "image/png", "a.png")
        m2 = self.gw.upload_image(data, "image/png", "b.png")
        self.assertEqual(m1["sha256"], m2["sha256"])  # deterministic sha-256
        # Only one bytes file exists
        path = os.path.join(self.uploads_dir, m1["sha256"])
        self.assertTrue(os.path.exists(path))
        # Delete one image: content remains referenced by the other
        self.gw.delete_image(m2["image_id"], force=True)
        self.assertTrue(os.path.exists(path))
        # Delete last reference: content removed
        self.gw.delete_image(m1["image_id"], force=True)
        self.assertFalse(os.path.exists(path))

    # Messages
    def test_text_only_message_and_ordering(self) -> None:
        conv = self.gw.create_conversation("Dev")
        cid = conv["conversation_id"]
        ack1 = self.gw.send_message(cid, "do X", [], mode="planning")
        ack2 = self.gw.send_message(cid, "do Y", [], mode="planning")
        msgs = self.gw.list_messages(cid)
        self.assertEqual([ack1["message_id"], ack2["message_id"]], [m["message_id"] for m in msgs])
        # Planner called, queue not used for planning mode
        self.assertEqual(len(self.planner.requests), 2)
        self.assertEqual(len(self.queue.enqueued), 0)

    def test_screenshot_only_and_multiple_images_and_limit(self) -> None:
        conv = self.gw.create_conversation("Dev2")
        cid = conv["conversation_id"]
        img1 = self.gw.upload_image(make_png_1x1(), "image/png", "a.png")
        img2 = self.gw.upload_image(make_png_1x1(), "image/png", "b.png")
        # screenshot-only allowed
        ack = self.gw.send_message(cid, " ", [img1["image_id"]], mode="analysis")
        self.assertEqual(ack["mode"], "analysis")
        # multiple images allowed
        ack2 = self.gw.send_message(cid, "task", [img1["image_id"], img2["image_id"]], mode="planning")
        self.assertIn("request_id", ack2)
        # limit enforcement
        cfg = ChatGatewayConfig(self.conv_path, self.uploads_meta, self.uploads_dir, max_images_per_message=1)
        gw2 = ChatGateway(config=cfg, planner=self.planner, mission_queue=self.queue, clock=self.clock, id_generator=self.ids)
        with self.assertRaises(ValidationError):
            gw2.send_message(cid, "hi", [img1["image_id"], img2["image_id"]], mode="analysis")

    def test_empty_message_rejection(self) -> None:
        conv = self.gw.create_conversation("Dev3")
        with self.assertRaises(ValidationError):
            self.gw.send_message(conv["conversation_id"], "   ", [], mode="analysis")

    def test_plan_and_enqueue_success(self) -> None:
        conv = self.gw.create_conversation("Dev4")
        ack = self.gw.send_message(conv["conversation_id"], "build", [], mode="plan_and_enqueue")
        self.assertIn("missions", ack)
        self.assertEqual(len(self.queue.enqueued), 1)
        ev = self.gw.latest_events(5)
        self.assertTrue(any(e.get("event") == "missions_enqueued" for e in ev))

    def test_planner_failure_and_queue_failure(self) -> None:
        conv = self.gw.create_conversation("Dev5")
        # planner failure => no enqueue
        self.planner.should_fail = True
        ack = self.gw.send_message(conv["conversation_id"], "build", [], mode="plan_and_enqueue")
        self.assertEqual(ack["missions"], [])
        self.assertEqual(len(self.queue.enqueued), 0)
        events = [e.get("event") for e in self.gw.latest_events(10)]
        self.assertIn("planning_failed", events)
        # queue failure after successful plan
        self.planner.should_fail = False
        self.queue.should_fail = True
        ack2 = self.gw.send_message(conv["conversation_id"], "build2", [], mode="plan_and_enqueue")
        self.assertEqual(ack2["missions"], [])
        events2 = [e.get("event") for e in self.gw.latest_events(10)]
        self.assertIn("enqueue_failed", events2)

    def test_duplicate_request_rejection_via_idgen(self) -> None:
        conv = self.gw.create_conversation("Dev6")
        # Force request ids to be identical for duplicate detection
        self.ids.set_fixed("r_", "r_fixed")
        self.gw.send_message(conv["conversation_id"], "one", [], mode="planning")
        with self.assertRaises(ConflictError):
            self.gw.send_message(conv["conversation_id"], "two", [], mode="planning")

    def test_structured_events_and_redaction(self) -> None:
        conv = self.gw.create_conversation("Dev7")
        self.gw.send_message(conv["conversation_id"], "password=secret", [], mode="analysis")
        evs = self.gw.latest_events(5)
        for e in evs:
            self.assertIn("event", e)
            # ensure no raw text included
            self.assertNotIn("password=secret", json.dumps(e))

    def test_image_deletion_protection(self) -> None:
        conv = self.gw.create_conversation("Dev8")
        img = self.gw.upload_image(make_png_1x1(), "image/png", "x.png")
        self.gw.send_message(conv["conversation_id"], "see", [img["image_id"]], mode="analysis")
        with self.assertRaises(ConflictError):
            self.gw.delete_image(img["image_id"], force=False)
        # Force deletion allowed
        self.gw.delete_image(img["image_id"], force=True)
        with self.assertRaises(NotFoundError):
            self.gw.get_image_metadata(img["image_id"])  # deleted

    def test_safe_restart_recovery_and_corruption_rejection(self) -> None:
        # Existing gateway wrote files; create a new one reading same files
        gw2 = ChatGateway(config=self.cfg, planner=self.planner, mission_queue=self.queue, clock=self.clock, id_generator=self.ids)
        self.assertIsNotNone(gw2.status())
        # Corrupt storage file
        with open(self.conv_path, "w", encoding="utf-8") as f:
            f.write("not json")
        with self.assertRaises(StorageError):
            ChatGateway(config=self.cfg, planner=self.planner, mission_queue=self.queue, clock=self.clock, id_generator=self.ids)

    def test_unrelated_files_remain_unchanged(self) -> None:
        other = os.path.join(self.base, "unrelated.txt")
        with open(other, "w", encoding="utf-8") as f:
            f.write("keep me")
        # Perform operations
        c = self.gw.create_conversation("Dev9")
        self.gw.send_message(c["conversation_id"], "x", [], mode="analysis")
        # Ensure unrelated file is unchanged
        with open(other, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "keep me")

    def test_raw_image_bytes_never_in_state(self) -> None:
        meta = self.gw.upload_image(make_png_1x1(), "image/png", "x.png")
        # Scan JSON files for PNG signature bytes sequence as text should not exist
        with open(self.uploads_meta, "r", encoding="utf-8") as f:
            s = f.read()
            self.assertNotIn("PNG\r\n\x1a\n", s)
        with open(self.conv_path, "r", encoding="utf-8") as f:
            s2 = f.read()
            self.assertNotIn("PNG\r\n\x1a\n", s2)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
