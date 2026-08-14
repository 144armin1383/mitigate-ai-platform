from __future__ import annotations

import argparse
import re
import urllib.parse

from agent.web import panel_server as base


_SAFE_MISSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,159}$")


class ApprovalPanelServer(base.PanelServer):
    """Loopback-only Canvas API with governed manual-approval action."""

    def handler(self):
        parent = super().handler()
        outer = self

        class Handler(parent):
            def do_POST(self) -> None:
                parsed = urllib.parse.urlsplit(self.path)
                parts = [
                    urllib.parse.unquote(part)
                    for part in parsed.path.split("/")
                    if part
                ]
                if (
                    len(parts) == 4
                    and parts[0] == "api"
                    and parts[1] == "missions"
                    and parts[3] == "approve"
                ):
                    if not self._require_auth():
                        return
                    mission_id = parts[2]
                    if not _SAFE_MISSION_ID.fullmatch(mission_id):
                        self._json(
                            400,
                            {
                                "ok": False,
                                "error": {
                                    "code": "invalid_mission_id",
                                    "message": "Invalid mission id",
                                },
                            },
                        )
                        return
                    self._proxy(
                        "/v1/execution-outcomes",
                        method="POST",
                        payload={
                            "action": "approve_manual_review",
                            "mission_id": mission_id,
                            "approved_by": outer.config.username,
                        },
                    )
                    return
                super().do_POST()

        return Handler


def main() -> int:
    parser = argparse.ArgumentParser(
        description="MITIGATE loopback API for Agent Canvas overlays"
    )
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    cfg = base.build_config_from_env()
    if args.host or args.port:
        cfg = base.PanelConfig(
            host=args.host or cfg.host,
            port=args.port or cfg.port,
            runtime_base_url=cfg.runtime_base_url,
            project_id=cfg.project_id,
            username=cfg.username,
            password=cfg.password,
            api_token=cfg.api_token,
        )
    cfg.validate()
    ApprovalPanelServer(cfg).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
