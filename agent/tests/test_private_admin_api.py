from __future__ import annotations

import http.client
import json
import os
import signal
import socket
import tempfile
import threading
import time
import types
import unittest
from typing import Any, Dict, List, Mapping, Optional

from agent.api.private_admin_api import (
    AdminAuth,
    DuplicateRequestError,
    InvalidStateError,
    MissionQueueInterface,
    NotFoundError,
    PlannerFailureError,
    PlannerInterface,
    PlannerValidationError,
    ServerConfig,
    build_arg_parser,
    create_server,
)


# =============================
# Fakes for DI
# =============================

class FakePlanner(PlannerInterface):
    def __init__(self) -> None:
        self.calls: List[Mapping[str, Any]] = []

    def plan(self, request: Mapping[str, Any]) -> List[Mapping[str, Any]]:
        self.calls.append(dict(request))
        title = str(request.get("title"))
        if title == "validation_error":
            raise PlannerValidationError("invalid")
        if title == "planner_fail":
            raise PlannerFailureError("fail")
        # Return simple plan with two missions and preserved dependencies
        return [
            {"name": "m1", "description": "task1", "depends_on": []},
            {"name": "m2", "description": "task2", "depends_on": ["m1"]},
        ]


class FakeQueue(MissionQueueInterface):
    def __init__(self) -> None:
        self._missions: Dict[str, Dict[str, Any]] = {}
        self._req_ids: set[str] = set()
        self._counter = 0

    def enqueue_plan(self, request_id: str, missions: List[Mapping[str, Any]]) -> List[str]:
        if request_id in self._req_ids:
            raise DuplicateRequestError("duplicate")
        self._req_ids.add(request_id)
        ids: List[str] = []
        for spec in missions:
            self._counter += 1
            mid = f"m-{self._counter}"
            self._missions[mid] = {
                "id": mid,
                "status": "queued",
                "spec": dict(spec),
            }
            ids.append(mid)
        return ids

    def list_missions(self) -> List[Mapping[str, Any]]:
        return list(self._missions.values())

    def get_mission(self, mission_id: str) -> Mapping[str, Any]:
        if mission_id not in self._missions:
            raise NotFoundError("nf")
        return dict(self._missions[mission_id])

    def cancel(self, mission_id: str) -> None:
        m = self._missions.get(mission_id)
        if not m:
            raise NotFoundError("nf")
        if m["status"] in {"completed", "failed"}:
            raise InvalidStateError("bad")
        m["status"] = "canceled"

    def resume(self, mission_id: str) -> None:
        m = self._missions.get(mission_id)
        if not m:
            raise NotFoundError("nf")
        if m["status"] not in {"canceled", "paused"}:
            raise InvalidStateError("bad")
        m["status"] = "queued"

    def retry(self, mission_id: str) -> None:
        m = self._missions.get(mission_id)
        if not m:
            raise NotFoundError("nf")
        if m["status"] != "failed":
            raise InvalidStateError("bad")
        m["status"] = "queued"

    def counts_by_state(self) -> Mapping[str, int]:
        counts: Dict[str, int] = {}
        for m in self._missions.values():
            s = str(m.get("status", "unknown"))
            counts[s] = counts.get(s, 0) + 1
        return counts


# =============================
# Test helpers
# =============================

def start_server(config: ServerConfig, planner: PlannerInterface, queue: MissionQueueInterface, token: str) -> tuple[threading.Thread, int, Any]:
    os.environ["MITIGATE_AI_ADMIN_TOKEN"] = token
    httpd = create_server(config, planner=planner, queue=queue)
    t = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.25}, daemon=True)
    t.start()
    # Wait briefly for server to bind
    time.sleep(0.1)
    host, port = httpd.server_address
    return t, int(port), httpd


def stop_server(httpd: Any, thread: threading.Thread) -> None:
    try:
        httpd.shutdown()
    finally:
        httpd.server_close()
        thread.join(timeout=3)


def api_request(port: int, method: str, path: str, token: Optional[str] = None, body: Optional[Mapping[str, Any]] = None, content_type: Optional[str] = None) -> tuple[int, Dict[str, Any]]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers: Dict[str, str] = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    data_bytes = b""
    if body is not None:
        if content_type is None:
            content_type = "application/json"
        headers["Content-Type"] = content_type
        data_bytes = json.dumps(body).encode("utf-8") if content_type == "application/json" else bytes(str(body), "utf-8")
        headers["Content-Length"] = str(len(data_bytes))
    conn.request(method, path, body=data_bytes if data_bytes else None, headers=headers)
    resp = conn.getresponse()
    raw = resp.read()
    try:
        payload = json.loads(raw.decode("utf-8")) if raw else {}
    except Exception:
        payload = {}
    conn.close()
    return resp.status, payload


# =============================
# Test cases
# =============================

class TestPrivateAdminAPI(unittest.TestCase):
    def setUp(self) -> None:
        self.token = "admintoken-test-123"
        self.planner = FakePlanner()
        self.queue = FakeQueue()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.events_path = os.path.join(self.tmpdir.name, "events.jsonl")
        self.reports_dir = os.path.join(self.tmpdir.name, "reports")
        os.makedirs(self.reports_dir, exist_ok=True)
        self.heartbeat_path = os.path.join(self.tmpdir.name, "worker.heartbeat")
        # Create event file with secrets to test redaction
        with open(self.events_path, "w", encoding="utf-8") as f:
            for i in range(5):
                evt = {"i": i, "token": f"tok{i}", "detail": {"password": "p"}}
                f.write(json.dumps(evt) + "\n")
        # Create heartbeat file
        with open(self.heartbeat_path, "w", encoding="utf-8") as f:
            f.write("hb")
        os.utime(self.heartbeat_path, None)
        self.config = ServerConfig(
            host="127.0.0.1",
            port=0,
            events_path=self.events_path,
            reports_path=self.reports_dir,
            heartbeat_path=self.heartbeat_path,
            rate_limit_per_minute=100,
        )
        self.thread, self.port, self.httpd = start_server(self.config, self.planner, self.queue, self.token)

    def tearDown(self) -> None:
        stop_server(self.httpd, self.thread)
        self.tmpdir.cleanup()
        if "MITIGATE_AI_ADMIN_TOKEN" in os.environ:
            del os.environ["MITIGATE_AI_ADMIN_TOKEN"]

    # Health endpoint (no auth)
    def test_health_endpoint(self) -> None:
        status, payload = api_request(self.port, "GET", "/health")
        self.assertEqual(200, status)
        self.assertEqual("ok", payload.get("status"))
        self.assertIn("request_id", payload)

    # Authentication tests
    def test_missing_authentication(self) -> None:
        status, _ = api_request(self.port, "GET", "/v1/status")
        self.assertEqual(401, status)

    def test_invalid_authentication(self) -> None:
        status, _ = api_request(self.port, "GET", "/v1/status", token="wrong")
        self.assertEqual(401, status)

    def test_valid_authentication(self) -> None:
        status, payload = api_request(self.port, "GET", "/v1/status", token=self.token)
        self.assertEqual(200, status)
        self.assertIn("queue_counts", payload)

    def test_constant_time_token_comparison_boundary(self) -> None:
        # Wrong length vs right length wrong value should both be 401
        status1, _ = api_request(self.port, "GET", "/v1/status", token="x")
        status2, _ = api_request(self.port, "GET", "/v1/status", token=self.token + "x")
        self.assertEqual(401, status1)
        self.assertEqual(401, status2)

    def test_missing_startup_token(self) -> None:
        # New server without env token should raise SystemExit
        if "MITIGATE_AI_ADMIN_TOKEN" in os.environ:
            del os.environ["MITIGATE_AI_ADMIN_TOKEN"]
        with self.assertRaises(SystemExit):
            create_server(ServerConfig(port=0))
        # restore token for other tests
        os.environ["MITIGATE_AI_ADMIN_TOKEN"] = self.token

    # Request validation
    def test_malformed_json(self) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json", "Content-Length": "5"}
        conn.request("POST", "/v1/requests", body=b"{bad}", headers=headers)
        resp = conn.getresponse()
        self.assertEqual(400, resp.status)
        conn.close()

    def test_unsupported_content_type(self) -> None:
        status, _ = api_request(self.port, "POST", "/v1/requests", token=self.token, body={"x": 1}, content_type="text/plain")
        self.assertEqual(415, status)

    def test_oversized_request_body(self) -> None:
        # Spin up server with tiny limit
        q = FakeQueue()
        p = FakePlanner()
        cfg = ServerConfig(host="127.0.0.1", port=0, max_request_bytes=10)
        th, port, httpd = start_server(cfg, p, q, self.token)
        try:
            big = {"request_id": "r", "title": "t", "description": "d" * 100}
            status, _ = api_request(port, "POST", "/v1/requests", token=self.token, body=big)
            self.assertEqual(413, status)
        finally:
            stop_server(httpd, th)

    def test_unknown_request_fields(self) -> None:
        body = {"request_id": "abc", "title": "hello", "description": "world", "x": 1}
        status, payload = api_request(self.port, "POST", "/v1/requests", token=self.token, body=body)
        self.assertEqual(400, status)
        self.assertEqual("unknown_fields", payload.get("error", {}).get("code"))

    # Planning and enqueue
    def test_successful_planning_and_atomic_enqueue(self) -> None:
        body = {"request_id": "r1", "title": "Build", "description": "Do it", "priority": "high"}
        status, payload = api_request(self.port, "POST", "/v1/requests", token=self.token, body=body)
        self.assertEqual(202, status)
        self.assertIn("mission_ids", payload)
        self.assertEqual(2, len(payload.get("mission_ids", [])))

    def test_planner_failure_without_partial_enqueue(self) -> None:
        body = {"request_id": "r2", "title": "planner_fail", "description": "Do it"}
        status, _ = api_request(self.port, "POST", "/v1/requests", token=self.token, body=body)
        self.assertEqual(502, status)
        self.assertEqual(0, len(self.queue.list_missions()))

    def test_duplicate_request_rejection(self) -> None:
        body = {"request_id": "dup1", "title": "t", "description": "d"}
        status, _ = api_request(self.port, "POST", "/v1/requests", token=self.token, body=body)
        self.assertEqual(202, status)
        status2, _ = api_request(self.port, "POST", "/v1/requests", token=self.token, body=body)
        self.assertEqual(409, status2)

    # Missions
    def test_mission_listing_and_details(self) -> None:
        body = {"request_id": "r3", "title": "t", "description": "d"}
        api_request(self.port, "POST", "/v1/requests", token=self.token, body=body)
        status, payload = api_request(self.port, "GET", "/v1/missions", token=self.token)
        self.assertEqual(200, status)
        missions = payload.get("missions", [])
        self.assertTrue(len(missions) >= 1)
        mid = missions[0]["id"]
        s2, p2 = api_request(self.port, "GET", f"/v1/missions/{mid}", token=self.token)
        self.assertEqual(200, s2)
        self.assertEqual(mid, p2.get("mission", {}).get("id"))

    def test_unknown_mission(self) -> None:
        status, _ = api_request(self.port, "GET", "/v1/missions/does-not-exist", token=self.token)
        self.assertEqual(404, status)

    def test_cancel_resume_retry_operations(self) -> None:
        # create mission
        body = {"request_id": "r4", "title": "t", "description": "d"}
        s, p = api_request(self.port, "POST", "/v1/requests", token=self.token, body=body)
        mid = p["mission_ids"][0]
        # cancel
        s1, _ = api_request(self.port, "POST", f"/v1/missions/{mid}/cancel", token=self.token)
        self.assertEqual(200, s1)
        # resume
        s2, _ = api_request(self.port, "POST", f"/v1/missions/{mid}/resume", token=self.token)
        self.assertEqual(200, s2)
        # invalid retry (not failed)
        s3, _ = api_request(self.port, "POST", f"/v1/missions/{mid}/retry", token=self.token)
        self.assertEqual(409, s3)

    def test_invalid_state_transitions(self) -> None:
        body = {"request_id": "r5", "title": "t", "description": "d"}
        s, p = api_request(self.port, "POST", "/v1/requests", token=self.token, body=body)
        mid = p["mission_ids"][0]
        # complete mission artificially
        self.queue._missions[mid]["status"] = "completed"
        s1, _ = api_request(self.port, "POST", f"/v1/missions/{mid}/cancel", token=self.token)
        self.assertEqual(409, s1)

    def test_deterministic_status_output(self) -> None:
        s, payload = api_request(self.port, "GET", "/v1/status", token=self.token)
        self.assertEqual(200, s)
        self.assertIsInstance(payload.get("queue_counts"), dict)
        self.assertIn("worker", payload)
        self.assertIn("uptime_seconds", payload)

    def test_event_limits_and_redaction(self) -> None:
        s, payload = api_request(self.port, "GET", "/v1/events?limit=2", token=self.token)
        self.assertEqual(200, s)
        events = payload.get("events", [])
        self.assertEqual(2, len(events))
        for e in events:
            # token and password should be redacted
            self.assertEqual("[REDACTED]", e.get("token"))
            self.assertEqual("[REDACTED]", e.get("detail", {}).get("password"))

    def test_reports_latest(self) -> None:
        p1 = os.path.join(self.reports_dir, "r1.json")
        p2 = os.path.join(self.reports_dir, "r2.json")
        with open(p1, "w", encoding="utf-8") as f:
            json.dump({"a": 1, "secret": "x"}, f)
        time.sleep(0.01)
        with open(p2, "w", encoding="utf-8") as f:
            json.dump({"b": 2, "password": "p"}, f)
        s, payload = api_request(self.port, "GET", "/v1/reports/latest", token=self.token)
        self.assertEqual(200, s)
        rep = payload.get("report", {})
        self.assertEqual(2, rep.get("b"))
        self.assertEqual("[REDACTED]", rep.get("password"))

    def test_rate_limiting(self) -> None:
        # New server with harsh limit
        q = FakeQueue()
        p = FakePlanner()
        cfg = ServerConfig(host="127.0.0.1", port=0, rate_limit_per_minute=3)
        th, port, httpd = start_server(cfg, p, q, self.token)
        try:
            for _ in range(3):
                s, _ = api_request(port, "GET", "/v1/status", token=self.token)
                self.assertEqual(200, s)
            s4, _ = api_request(port, "GET", "/v1/status", token=self.token)
            self.assertEqual(429, s4)
        finally:
            stop_server(httpd, th)

    def test_localhost_default_binding(self) -> None:
        os.environ["MITIGATE_AI_ADMIN_TOKEN"] = self.token
        httpd = create_server(ServerConfig(port=0))
        host, _ = httpd.server_address
        self.assertEqual("127.0.0.1", host)
        httpd.server_close()

    def test_cli_parsing_defaults(self) -> None:
        parser = build_arg_parser()
        args = parser.parse_args([])
        self.assertEqual("127.0.0.1", args.host)
        self.assertEqual(8765, args.port)

    def test_invalid_cli_arguments(self) -> None:
        parser = build_arg_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["--port", "notint"])  # argparse should raise SystemExit

    def test_graceful_shutdown(self) -> None:
        # Start separate server and shut it down gracefully via shutdown API
        q = FakeQueue()
        p = FakePlanner()
        cfg = ServerConfig(host="127.0.0.1", port=0)
        th, port, httpd = start_server(cfg, p, q, self.token)
        try:
            s, _ = api_request(port, "GET", "/health")
            self.assertEqual(200, s)
        finally:
            stop_server(httpd, th)

    def test_unrelated_files_remain_unchanged(self) -> None:
        unrelated = os.path.join(self.tmpdir.name, "unrelated.txt")
        with open(unrelated, "w", encoding="utf-8") as f:
            f.write("keep")
        # Perform some API ops
        api_request(self.port, "GET", "/v1/status", token=self.token)
        api_request(self.port, "GET", "/v1/events?limit=1", token=self.token)
        # Check file unchanged
        with open(unrelated, "r", encoding="utf-8") as f:
            self.assertEqual("keep", f.read())


if __name__ == "__main__":
    unittest.main()
