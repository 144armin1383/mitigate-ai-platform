from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class CanvasApprovalIntegrationTests(unittest.TestCase):
    def test_approval_overlay_uses_same_origin_mitigate_api(self) -> None:
        text = (ROOT / "agent/web/canvas_approval_overlay.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("const API_BASE = '/mitigate-runtime/api'", text)
        self.assertIn("await api('/approvals')", text)
        self.assertNotIn("/requests?limit=60", text)
        self.assertIn("awaiting_approval", text)
        self.assertIn("Approve &amp; Merge", text)
        self.assertIn("Reject", text)
        self.assertIn("mitigate-reject-btn", text)
        self.assertIn("#e5484d", text)
        self.assertIn("data-approve", text)
        self.assertIn("data-reject", text)
        self.assertIn("/${decision}", text)
        self.assertIn("decision === 'approve'", text)
        self.assertNotIn("Confirm Approve", text)
        self.assertNotIn("Confirm Reject", text)
        self.assertIn("READ_TIMEOUT_MS", text)
        self.assertIn("ACTION_TIMEOUT_MS", text)
        self.assertIn("window.__MITIGATE_APPROVAL_LAST_RESULT__", text)
        self.assertIn("Server returned success but the mission is still awaiting approval", text)
        self.assertIn("window.confirm", text)
        self.assertIn("bottom:118px", text)
        self.assertNotIn("18.175.175.110", text)
        self.assertNotIn("mitigateuk.com", text)

    def test_runtime_overlay_remains_visible_and_reports_updates(self) -> None:
        text = (
            ROOT
            / "agent/integrations/agent-canvas/mitigate-runtime-overlay.js"
        ).read_text(encoding="utf-8")
        self.assertIn("MITIGATE Runtimes", text)
        self.assertIn("bottom:72px", text)
        self.assertIn("Installed:", text)
        self.assertIn("Latest stable:", text)
        self.assertIn("Update available", text)
        self.assertIn("Up to date", text)
        self.assertNotIn("18.175.175.110", text)
        self.assertNotIn("mitigateuk.com", text)

    def test_opencode_overlay_uses_fixed_zen_endpoint_and_canvas_profiles(self) -> None:
        text = (ROOT / "agent/web/canvas_llm_provider_overlay.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("https://opencode.ai/zen/v1", text)
        self.assertIn("openai/glm-5.2", text)
        self.assertIn("opencode/${id}", text)
        self.assertIn("/mitigate-llm/opencode/models", text)
        self.assertIn("/api/profiles/${encodeURIComponent(PROFILE)}", text)
        self.assertIn("/mitigate-runtime/provider/opencode", text)
        self.assertIn("runtime_configured", text)
        self.assertIn("base_url: BASE_URL", text)
        self.assertIn("include_secrets: true", text)
        self.assertIn("Save & Activate", text)
        self.assertIn("Canvas + MITIGATE Runtime", text)
        self.assertIn("Test Connection", text)
        self.assertIn("MINIMIZED_STORAGE_KEY", text)
        self.assertIn("data-minimize", text)
        self.assertIn("is-minimized", text)
        self.assertIn("Expand OpenCode Zen settings", text)
        self.assertIn("Minimize OpenCode Zen settings", text)
        self.assertNotIn("sessionStorage", text)
        self.assertNotIn("localStorage.setItem('api", text)
        self.assertNotIn("localStorage.setItem(\"api", text)
        self.assertNotIn("18.175.175.110", text)

    def test_nginx_fragment_keeps_api_private_and_host_agnostic(self) -> None:
        text = (
            ROOT / "agent/deploy/nginx/mitigate-ai-canvas-approval.conf"
        ).read_text(encoding="utf-8")
        self.assertIn("proxy_pass http://127.0.0.1:8766", text)
        self.assertIn("location ^~ /mitigate-runtime/api/", text)
        self.assertIn("mitigate-ai-panel-auth.conf", text)
        self.assertNotIn("18.175.175.110", text)
        self.assertNotIn("server_name", text)

    def test_unified_installer_installs_all_canvas_controls(self) -> None:
        text = (
            ROOT / "agent/bootstrap/install_canvas_ui_integration.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("mitigate-runtime-overlay.js", text)
        self.assertIn("mitigate-approval-overlay.js", text)
        self.assertIn("mitigate-llm-provider-overlay.js", text)
        self.assertIn("MITIGATE_RUNTIME_OVERLAY=ACTIVE", text)
        self.assertIn("MITIGATE_APPROVAL_OVERLAY=ACTIVE", text)
        self.assertIn("MITIGATE_LLM_PROVIDER_OVERLAY=ACTIVE", text)
        self.assertIn("MITIGATE_OPENCODE_ZEN_PROBE=ACTIVE", text)
        self.assertIn("MITIGATE_OPENCODE_RUNTIME_SYNC=ACTIVE", text)
        self.assertIn("/mitigate-runtime/provider/opencode", text)
        self.assertIn("provider-secrets", text)
        self.assertIn("https://opencode.ai/zen/v1/", text)
        self.assertIn('proxy_set_header Authorization "Bearer \\$http_x_mitigate_llm_key"', text)
        self.assertIn('proxy_set_header X-Mitigate-LLM-Key ""', text)
        self.assertIn("MITIGATE_STANDALONE_PANEL=REMOVED", text)
        self.assertIn("UPSTREAM_CANVAS_FILES_MODIFIED=no", text)
        self.assertNotIn("docker exec", text)
        self.assertNotIn("/home/openhands", text)

    def test_legacy_approval_installer_delegates_to_unified_installer(self) -> None:
        text = (
            ROOT / "agent/bootstrap/install_canvas_approval_integration.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("install_canvas_ui_integration.sh", text)
        self.assertNotIn("sub_filter", text)

    def test_standalone_panel_ui_is_removed_from_backend(self) -> None:
        text = (ROOT / "agent/web/panel_server.py").read_text(encoding="utf-8")
        self.assertNotIn("PANEL_HTML", text)
        self.assertNotIn("Agent Control Panel", text)
        self.assertIn("standalone_panel_removed", text)
        self.assertIn("Use the MITIGATE controls inside Agent Canvas", text)

    def test_provider_handoff_is_authenticated_and_private(self) -> None:
        text = (ROOT / "agent/web/panel_server_approval.py").read_text(encoding="utf-8")
        self.assertIn('/api/providers/opencode', text)
        self.assertIn('self._require_auth()', text)
        self.assertIn('save_provider_secret(provider="opencode"', text)
        self.assertNotIn('print(api_key)', text)


if __name__ == "__main__":
    unittest.main()
