from __future__ import annotations

import base64
import json
import unittest
from dataclasses import replace
from unittest import mock

from agent.web.panel_server import PanelConfig, PanelServer, TASK_TYPES, _request_id


class WebPanelTests(unittest.TestCase):
    def config(self) -> PanelConfig:
        return PanelConfig(
            host="127.0.0.1",
            port=8766,
            runtime_base_url="http://127.0.0.1:8765",
            project_id="mitigate-ai-platform",
            username="admin",
            password="panel-secret",
            api_token="api-secret",
        )

    def test_config_rejects_public_bind(self) -> None:
        with self.assertRaisesRegex(ValueError, "public_bind_not_allowed"):
            replace(self.config(), host="0.0.0.0").validate()

    def test_config_requires_panel_password(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing_panel_password"):
            replace(self.config(), password="").validate()

    def test_config_requires_api_token(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing_api_token"):
            replace(self.config(), api_token="").validate()

    def test_basic_auth_is_constant_time_checked(self) -> None:
        server = PanelServer(self.config())
        good = base64.b64encode(b"admin:panel-secret").decode("ascii")
        bad = base64.b64encode(b"admin:wrong").decode("ascii")
        self.assertTrue(server._authorized("Basic " + good))
        self.assertFalse(server._authorized("Basic " + bad))
        self.assertFalse(server._authorized(None))

    def test_upstream_injects_bearer_token_server_side(self) -> None:
        server = PanelServer(self.config())
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = b"{}"
        response.headers.get.return_value = "application/json"
        with mock.patch("urllib.request.urlopen", return_value=response) as opened:
            status, body, ctype = server._upstream("/v1/runtime/status")
        self.assertEqual(200, status)
        self.assertEqual(b"{}", body)
        self.assertEqual("application/json", ctype)
        request = opened.call_args.args[0]
        self.assertEqual("Bearer api-secret", request.get_header("Authorization"))

    def test_panel_task_types_include_inspection(self) -> None:
        self.assertIn("inspection", TASK_TYPES)
        self.assertIn("backend", TASK_TYPES)
        self.assertIn("wordpress", TASK_TYPES)

    def test_request_ids_are_safe_and_unique(self) -> None:
        one = _request_id()
        two = _request_id()
        self.assertNotEqual(one, two)
        self.assertRegex(one, r"^panel-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{6}$")

    def test_runtime_error_is_sanitized(self) -> None:
        server = PanelServer(self.config())
        with mock.patch("urllib.request.urlopen", side_effect=OSError("secret path /tmp/private")):
            status, body, _ctype = server._upstream("/v1/runtime/status")
        payload = json.loads(body)
        self.assertEqual(502, status)
        self.assertEqual("runtime_unavailable", payload["error"]["code"])
        self.assertNotIn("secret path", body.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
