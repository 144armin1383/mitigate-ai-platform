from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class CanvasApprovalIntegrationTests(unittest.TestCase):
    def test_overlay_uses_same_origin_mitigate_api(self) -> None:
        text = (ROOT / "agent/web/canvas_approval_overlay.js").read_text(encoding="utf-8")
        self.assertIn("const API_BASE = '/mitigate-runtime/api'", text)
        self.assertIn("awaiting_approval", text)
        self.assertIn("Approve &amp; Merge", text)
        self.assertIn("/approve", text)
        self.assertNotIn("18.175.175.110", text)
        self.assertNotIn("mitigateuk.com", text)

    def test_nginx_fragment_keeps_panel_private_and_host_agnostic(self) -> None:
        text = (ROOT / "agent/deploy/nginx/mitigate-ai-canvas-approval.conf").read_text(encoding="utf-8")
        self.assertIn("proxy_pass http://127.0.0.1:8766", text)
        self.assertIn("location ^~ /mitigate-runtime/api/", text)
        self.assertIn("mitigate-ai-panel-auth.conf", text)
        self.assertNotIn("18.175.175.110", text)
        self.assertNotIn("server_name", text)

    def test_installer_is_external_and_idempotent_by_marker(self) -> None:
        text = (ROOT / "agent/bootstrap/install_canvas_approval_integration.sh").read_text(encoding="utf-8")
        self.assertIn("mitigate-ai-canvas-integration.conf", text)
        self.assertIn("mitigate-approval-overlay.js", text)
        self.assertIn("CANVAS_SOURCE_MODIFIED=no", text)
        self.assertIn("CANVAS_UPDATE_SURVIVAL=external_nginx_overlay", text)
        self.assertIn("if include_line not in text", text)
        self.assertIn("if script not in text", text)
        self.assertNotIn("docker exec", text)
        self.assertNotIn("/home/openhands", text)


if __name__ == "__main__":
    unittest.main()
